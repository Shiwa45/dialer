# calls/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils import timezone
from core.models import TimeStampedModel
import uuid

class CallLog(TimeStampedModel):
    """
    Comprehensive call logging for all calls
    """
    CALL_TYPES = [
        ('outbound', 'Outbound'),
        ('inbound', 'Inbound'),
        ('internal', 'Internal'),
        ('conference', 'Conference'),
        ('transfer', 'Transfer'),
    ]
    
    CALL_STATUS = [
        ('initiated', 'Initiated'),
        ('ringing', 'Ringing'),
        ('answered', 'Answered'),
        ('busy', 'Busy'),
        ('no_answer', 'No Answer'),
        ('failed', 'Failed'),
        ('hangup', 'Hangup'),
        ('transferred', 'Transferred'),
        ('conference', 'Conference'),
    ]
    
    # Unique Identifiers
    call_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    uniqueid = models.CharField(max_length=100, blank=True)  # Asterisk unique ID
    linkedid = models.CharField(max_length=100, blank=True)  # Asterisk linked ID
    
    # Call Classification
    call_type = models.CharField(max_length=20, choices=CALL_TYPES)
    call_status = models.CharField(max_length=20, choices=CALL_STATUS, default='initiated')
    
    # Participants
    caller_id = models.CharField(max_length=100, blank=True)
    called_number = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message="Enter a valid phone number"
            )
        ]
    )
    agent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_calls'
    )
    
    # Campaign and Lead Association
    campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaign_calls'
    )
    lead = models.ForeignKey(
        'leads.Lead',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lead_calls'
    )
    
    # Timing
    start_time = models.DateTimeField()
    answer_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    # Duration (in seconds)
    total_duration = models.PositiveIntegerField(default=0)
    talk_duration = models.PositiveIntegerField(default=0)
    wait_duration = models.PositiveIntegerField(default=0)
    
    # Technical Details
    asterisk_server = models.ForeignKey(
        'telephony.AsteriskServer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    channel = models.CharField(max_length=200, blank=True)
    destination_channel = models.CharField(max_length=200, blank=True)
    
    # Call Quality
    hangup_cause = models.PositiveIntegerField(null=True, blank=True)
    hangup_cause_text = models.CharField(max_length=100, blank=True)
    
    # Disposition
    disposition = models.ForeignKey(
        'campaigns.Disposition',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='disposition_calls'
    )
    disposition_notes = models.TextField(blank=True)
    
    # Recording
    is_recorded = models.BooleanField(default=False)
    recording_filename = models.CharField(max_length=500, blank=True)
    
    # Cost and Billing
    cost = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    carrier = models.ForeignKey(
        'telephony.Carrier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = "Call Log"
        verbose_name_plural = "Call Logs"
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['call_id']),
            models.Index(fields=['called_number']),
            models.Index(fields=['agent', 'start_time']),
            models.Index(fields=['campaign', 'start_time']),
            models.Index(fields=['start_time']),
        ]
    
    def __str__(self):
        return f"Call {self.call_id} - {self.called_number}"
    
    def duration_formatted(self):
        """Return formatted duration as MM:SS"""
        if self.total_duration:
            minutes, seconds = divmod(self.total_duration, 60)
            return f"{minutes:02d}:{seconds:02d}"
        return "00:00"
    
    def was_answered(self):
        """Check if call was answered"""
        return self.call_status == 'answered' and self.answer_time is not None

class CallEvent(TimeStampedModel):
    """
    Detailed call events and state changes
    """
    EVENT_TYPES = [
        ('newchannel', 'New Channel'),
        ('newstate', 'New State'),
        ('dial', 'Dial'),
        ('answer', 'Answer'),
        ('hangup', 'Hangup'),
        ('bridge', 'Bridge'),
        ('unbridge', 'Unbridge'),
        ('transfer', 'Transfer'),
        ('hold', 'Hold'),
        ('unhold', 'Unhold'),
        ('dtmf', 'DTMF'),
        ('varset', 'Variable Set'),
    ]
    
    call_log = models.ForeignKey(CallLog, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    event_time = models.DateTimeField()
    
    # Event Details
    channel = models.CharField(max_length=200, blank=True)
    uniqueid = models.CharField(max_length=100, blank=True)
    event_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        verbose_name = "Call Event"
        verbose_name_plural = "Call Events"
        ordering = ['event_time']
    
    def __str__(self):
        return f"{self.call_log.call_id} - {self.get_event_type_display()}"

class AgentSession(TimeStampedModel):
    """
    Agent work sessions and time tracking
    """
    SESSION_STATUS = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('ended', 'Ended'),
    ]
    
    PAUSE_REASONS = [
        ('break', 'Break'),
        ('lunch', 'Lunch'),
        ('training', 'Training'),
        ('meeting', 'Meeting'),
        ('technical', 'Technical Issues'),
        ('personal', 'Personal'),
        ('admin', 'Administrative'),
    ]
    
    # Basic Information
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agent_sessions')
    session_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    
    # Session Timing
    login_time = models.DateTimeField()
    logout_time = models.DateTimeField(null=True, blank=True)
    total_duration = models.PositiveIntegerField(default=0, help_text="Total session duration in seconds")
    
    # Status Tracking
    status = models.CharField(max_length=20, choices=SESSION_STATUS, default='active')
    current_campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # Performance Metrics
    calls_handled = models.PositiveIntegerField(default=0)
    talk_time = models.PositiveIntegerField(default=0, help_text="Total talk time in seconds")
    idle_time = models.PositiveIntegerField(default=0, help_text="Total idle time in seconds")
    pause_time = models.PositiveIntegerField(default=0, help_text="Total pause time in seconds")
    
    # System Information
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Agent Session"
        verbose_name_plural = "Agent Sessions"
        ordering = ['-login_time']
    
    def __str__(self):
        return f"{self.agent.username} - {self.login_time}"
    
    def session_duration(self):
        """Calculate session duration"""
        end_time = self.logout_time or timezone.now()
        return (end_time - self.login_time).total_seconds()

class AgentPause(TimeStampedModel):
    """
    Agent pause/break tracking
    """
    agent_session = models.ForeignKey(AgentSession, on_delete=models.CASCADE, related_name='pauses')
    pause_reason = models.CharField(max_length=20, choices=AgentSession.PAUSE_REASONS)
    pause_start = models.DateTimeField()
    pause_end = models.DateTimeField(null=True, blank=True)
    duration = models.PositiveIntegerField(default=0, help_text="Pause duration in seconds")
    notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Agent Pause"
        verbose_name_plural = "Agent Pauses"
        ordering = ['-pause_start']
    
    def __str__(self):
        return f"{self.agent_session.agent.username} - {self.get_pause_reason_display()}"
    
    def is_active(self):
        """Check if pause is currently active"""
        return self.pause_end is None

class Transfer(TimeStampedModel):
    """
    Call transfer tracking
    """
    TRANSFER_TYPES = [
        ('warm', 'Warm Transfer'),
        ('cold', 'Cold Transfer'),
        ('conference', 'Conference Transfer'),
    ]
    
    # Basic Information
    original_call = models.ForeignKey(
        CallLog,
        on_delete=models.CASCADE,
        related_name='outbound_transfers'
    )
    new_call = models.ForeignKey(
        CallLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inbound_transfers'
    )
    
    # Transfer Details
    transfer_type = models.CharField(max_length=20, choices=TRANSFER_TYPES)
    from_agent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='transfers_made'
    )
    to_agent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transfers_received'
    )
    to_number = models.CharField(max_length=20, blank=True)
    
    # Timing
    transfer_time = models.DateTimeField()
    completed = models.BooleanField(default=False)
    
    # Notes
    reason = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Transfer"
        verbose_name_plural = "Transfers"
        ordering = ['-transfer_time']
    
    def __str__(self):
        return f"Transfer {self.original_call.call_id} to {self.to_number or self.to_agent}"

class Conference(TimeStampedModel):
    """
    Conference call management
    """
    # Basic Information
    conference_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    name = models.CharField(max_length=200, blank=True)
    
    # Timing
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration = models.PositiveIntegerField(default=0, help_text="Conference duration in seconds")
    
    # Management
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='conferences_created'
    )
    
    # Participants
    participants = models.ManyToManyField(
        CallLog,
        through='ConferenceParticipant',
        related_name='conferences'
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Conference"
        verbose_name_plural = "Conferences"
        ordering = ['-start_time']
    
    def __str__(self):
        return f"Conference {self.conference_id}"

class ConferenceParticipant(TimeStampedModel):
    """
    Conference participants tracking
    """
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE)
    call_log = models.ForeignKey(CallLog, on_delete=models.CASCADE)
    
    # Participation Details
    joined_at = models.DateTimeField()
    left_at = models.DateTimeField(null=True, blank=True)
    is_moderator = models.BooleanField(default=False)
    is_muted = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['conference', 'call_log']
        verbose_name = "Conference Participant"
        verbose_name_plural = "Conference Participants"
    
    def __str__(self):
        return f"{self.conference.conference_id} - {self.call_log.called_number}"

class CallQuality(TimeStampedModel):
    """
    Call quality metrics and monitoring
    """
    call_log = models.OneToOneField(CallLog, on_delete=models.CASCADE, related_name='quality_metrics')
    
    # Audio Quality Metrics
    packet_loss = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    jitter = models.PositiveIntegerField(null=True, blank=True, help_text="Jitter in milliseconds")
    latency = models.PositiveIntegerField(null=True, blank=True, help_text="Latency in milliseconds")
    
    # Signal Quality
    signal_level = models.IntegerField(null=True, blank=True)
    noise_level = models.IntegerField(null=True, blank=True)
    
    # Codec Information
    codec_used = models.CharField(max_length=20, blank=True)
    bandwidth_used = models.PositiveIntegerField(null=True, blank=True, help_text="Bandwidth in kbps")
    
    # Quality Score (1-5)
    overall_quality = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=[
            (1, 'Poor'),
            (2, 'Fair'),
            (3, 'Good'),
            (4, 'Very Good'),
            (5, 'Excellent'),
        ]
    )
    
    class Meta:
        verbose_name = "Call Quality"
        verbose_name_plural = "Call Quality Metrics"
    
    def __str__(self):
        return f"Quality for {self.call_log.call_id}"

class CallNote(TimeStampedModel):
    """
    Notes added to specific calls
    """
    call_log = models.ForeignKey(CallLog, on_delete=models.CASCADE, related_name='notes')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    note = models.TextField()
    is_important = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Call Note"
        verbose_name_plural = "Call Notes"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Note for call {self.call_log.call_id}"

class CallRecordingRequest(TimeStampedModel):
    """
    Requests for call recordings (for compliance/security)
    """
    REQUEST_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('denied', 'Denied'),
        ('fulfilled', 'Fulfilled'),
    ]
    
    call_log = models.ForeignKey(CallLog, on_delete=models.CASCADE, related_name='recording_requests')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recording_requests_made')
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recording_requests_approved'
    )
    
    # Request Details
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=REQUEST_STATUS, default='pending')
    
    # Approval Details
    approval_date = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True)
    
    # Fulfillment
    fulfilled_date = models.DateTimeField(null=True, blank=True)
    download_link = models.URLField(blank=True)
    expires_on = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Call Recording Request"
        verbose_name_plural = "Call Recording Requests"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Recording request for {self.call_log.call_id}"

# calls/apps.py
from django.apps import AppConfig

class CallsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calls'
    verbose_name = 'Call Management'

# calls/__init__.py
default_app_config = 'calls.apps.CallsConfig'