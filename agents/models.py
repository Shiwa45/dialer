# agents/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils import timezone
from core.models import TimeStampedModel
import uuid


class AgentQueue(TimeStampedModel):
    """
    Agent queue assignment and management
    """
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agent_queues')
    campaign = models.ForeignKey('campaigns.Campaign', on_delete=models.CASCADE, related_name='agent_assignments')
    
    # Queue Settings
    is_active = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=1, help_text="Lower number = higher priority")
    max_concurrent_calls = models.PositiveIntegerField(default=1)
    
    # Performance Settings
    wrap_up_time = models.PositiveIntegerField(default=30, help_text="Wrap-up time in seconds")
    auto_answer = models.BooleanField(default=False)
    receive_inbound = models.BooleanField(default=True)
    make_outbound = models.BooleanField(default=True)
    
    # Assignment Details
    assigned_date = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='assigned_agent_queues'
    )
    
    class Meta:
        unique_together = ['agent', 'campaign']
        verbose_name = "Agent Queue"
        verbose_name_plural = "Agent Queues"
        ordering = ['priority', 'assigned_date']
    
    def __str__(self):
        return f"{self.agent.username} - {self.campaign.name}"


class AgentScript(TimeStampedModel):
    """
    Call scripts for agents
    """
    SCRIPT_TYPES = [
        ('opening', 'Opening Script'),
        ('product', 'Product Presentation'),
        ('objection', 'Objection Handling'),
        ('closing', 'Closing Script'),
        ('callback', 'Callback Script'),
        ('transfer', 'Transfer Script'),
        ('general', 'General Script'),
    ]
    
    name = models.CharField(max_length=200)
    script_type = models.CharField(max_length=20, choices=SCRIPT_TYPES)
    content = models.TextField(help_text="Script content with variables like {first_name}, {company}")
    
    # Assignment
    campaign = models.ForeignKey(
        'campaigns.Campaign', 
        on_delete=models.CASCADE, 
        related_name='agent_scripts',
        null=True,
        blank=True
    )
    is_global = models.BooleanField(default=False, help_text="Available to all campaigns")
    
    # Settings
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=1)
    auto_display = models.BooleanField(default=False, help_text="Auto-display when call connects")
    
    # Management
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Agent Script"
        verbose_name_plural = "Agent Scripts"
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.get_script_type_display()})"


class AgentHotkey(TimeStampedModel):
    """
    Agent hotkey configurations
    """
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hotkeys')
    
    # Hotkey Configuration
    key_combination = models.CharField(max_length=20, help_text="e.g., Ctrl+1, Alt+S")
    action_type = models.CharField(
        max_length=20,
        choices=[
            ('disposition', 'Set Disposition'),
            ('transfer', 'Transfer Call'),
            ('script', 'Display Script'),
            ('pause', 'Pause/Resume'),
            ('hangup', 'Hangup Call'),
            ('mute', 'Mute/Unmute'),
            ('hold', 'Hold/Unhold'),
            ('record', 'Start/Stop Recording'),
        ]
    )
    
    # Action Details
    disposition = models.ForeignKey(
        'campaigns.Disposition', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    transfer_number = models.CharField(max_length=20, blank=True)
    script = models.ForeignKey(AgentScript, on_delete=models.CASCADE, null=True, blank=True)
    
    # Settings
    is_active = models.BooleanField(default=True)
    description = models.CharField(max_length=200, blank=True)
    
    class Meta:
        unique_together = ['agent', 'key_combination']
        verbose_name = "Agent Hotkey"
        verbose_name_plural = "Agent Hotkeys"
        ordering = ['key_combination']
    
    def __str__(self):
        return f"{self.agent.username} - {self.key_combination} ({self.get_action_type_display()})"


class AgentBreakCode(TimeStampedModel):
    """
    Predefined break/pause codes for agents
    """
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Settings
    is_paid = models.BooleanField(default=True, help_text="Is this a paid break?")
    max_duration = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        help_text="Maximum duration in minutes (null = unlimited)"
    )
    requires_approval = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Display
    display_order = models.PositiveIntegerField(default=1)
    color_code = models.CharField(max_length=7, default='#6c757d', help_text="Hex color code")
    
    class Meta:
        verbose_name = "Agent Break Code"
        verbose_name_plural = "Agent Break Codes"
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class AgentSkill(TimeStampedModel):
    """
    Agent skills and proficiency levels
    """
    PROFICIENCY_LEVELS = [
        (1, 'Beginner'),
        (2, 'Novice'),
        (3, 'Intermediate'),
        (4, 'Advanced'),
        (5, 'Expert'),
    ]
    
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='skills')
    skill_name = models.CharField(max_length=100)
    proficiency_level = models.PositiveSmallIntegerField(choices=PROFICIENCY_LEVELS, default=1)
    
    # Certification
    certified = models.BooleanField(default=False)
    certification_date = models.DateField(null=True, blank=True)
    certification_expires = models.DateField(null=True, blank=True)
    
    # Assignment
    can_train_others = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Management
    verified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='verified_skills'
    )
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['agent', 'skill_name']
        verbose_name = "Agent Skill"
        verbose_name_plural = "Agent Skills"
        ordering = ['skill_name', '-proficiency_level']
    
    def __str__(self):
        return f"{self.agent.username} - {self.skill_name} (Level {self.proficiency_level})"


class AgentPerformanceGoal(TimeStampedModel):
    """
    Agent performance goals and targets
    """
    GOAL_TYPES = [
        ('calls_per_hour', 'Calls Per Hour'),
        ('contact_rate', 'Contact Rate %'),
        ('conversion_rate', 'Conversion Rate %'),
        ('talk_time', 'Average Talk Time'),
        ('sales_per_day', 'Sales Per Day'),
        ('revenue_per_day', 'Revenue Per Day'),
        ('quality_score', 'Quality Score'),
    ]
    
    PERIOD_TYPES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]
    
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='performance_goals')
    goal_type = models.CharField(max_length=20, choices=GOAL_TYPES)
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPES)
    
    # Goal Details
    target_value = models.DecimalField(max_digits=10, decimal_places=2)
    current_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Time Period
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Status
    is_active = models.BooleanField(default=True)
    achieved = models.BooleanField(default=False)
    achievement_date = models.DateField(null=True, blank=True)
    
    # Management
    set_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='set_performance_goals'
    )
    notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Agent Performance Goal"
        verbose_name_plural = "Agent Performance Goals"
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.agent.username} - {self.get_goal_type_display()} ({self.target_value})"
    
    def progress_percentage(self):
        """Calculate progress percentage"""
        if self.target_value == 0:
            return 0
        return min(100, (self.current_value / self.target_value) * 100)


class AgentNote(TimeStampedModel):
    """
    Internal notes about agents
    """
    NOTE_TYPES = [
        ('performance', 'Performance'),
        ('training', 'Training'),
        ('disciplinary', 'Disciplinary'),
        ('recognition', 'Recognition'),
        ('general', 'General'),
        ('schedule', 'Schedule'),
        ('technical', 'Technical'),
    ]
    
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agent_notes')
    note_type = models.CharField(max_length=20, choices=NOTE_TYPES)
    subject = models.CharField(max_length=200)
    content = models.TextField()
    
    # Visibility and Access
    is_private = models.BooleanField(default=False, help_text="Only visible to managers")
    is_important = models.BooleanField(default=False)
    
    # Management
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_agent_notes')
    
    class Meta:
        verbose_name = "Agent Note"
        verbose_name_plural = "Agent Notes"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.agent.username} - {self.subject}"


class AgentWebRTCSession(TimeStampedModel):
    """
    WebRTC phone session management for agents
    """
    SESSION_STATUS = [
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('disconnected', 'Disconnected'),
        ('failed', 'Failed'),
        ('timeout', 'Timeout'),
    ]
    
    agent = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='webrtc_session'
    )
    session_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    
    # Connection Details
    status = models.CharField(max_length=20, choices=SESSION_STATUS, default='connecting')
    sip_extension = models.CharField(max_length=20, blank=True)
    asterisk_server = models.ForeignKey(
        'telephony.AsteriskServer',
        on_delete=models.SET_NULL,
        null=True
    )
    
    # WebRTC Details
    ice_servers = models.JSONField(default=list, blank=True)
    local_description = models.JSONField(default=dict, blank=True)
    remote_description = models.JSONField(default=dict, blank=True)
    
    # Connection Timing
    connect_time = models.DateTimeField(null=True, blank=True)
    disconnect_time = models.DateTimeField(null=True, blank=True)
    last_ping = models.DateTimeField(auto_now=True)
    
    # Quality Metrics
    packet_loss = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    jitter = models.PositiveIntegerField(default=0, help_text="Jitter in milliseconds")
    latency = models.PositiveIntegerField(default=0, help_text="Latency in milliseconds")
    
    # Network Information
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    browser_info = models.JSONField(default=dict, blank=True)
    
    class Meta:
        verbose_name = "Agent WebRTC Session"
        verbose_name_plural = "Agent WebRTC Sessions"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.agent.username} - {self.get_status_display()}"
    
    def is_active(self):
        """Check if session is currently active"""
        return self.status == 'connected' and self.disconnect_time is None
    
    def connection_duration(self):
        """Get connection duration in seconds"""
        if not self.connect_time:
            return 0
        end_time = self.disconnect_time or timezone.now()
        return (end_time - self.connect_time).total_seconds()


class AgentCallbackTask(TimeStampedModel):
    """
    Callback tasks assigned to agents
    """
    TASK_STATUS = [
        ('pending', 'Pending'),
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('missed', 'Missed'),
    ]
    
    PRIORITY_LEVELS = [
        (1, 'Low'),
        (2, 'Normal'),
        (3, 'High'),
        (4, 'Urgent'),
    ]
    
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='callback_tasks')
    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, related_name='callback_tasks')
    campaign = models.ForeignKey('campaigns.Campaign', on_delete=models.CASCADE)
    
    # Task Details
    scheduled_time = models.DateTimeField()
    notes = models.TextField(blank=True)
    priority = models.PositiveSmallIntegerField(choices=PRIORITY_LEVELS, default=2)
    
    # Status and Completion
    status = models.CharField(max_length=20, choices=TASK_STATUS, default='pending')
    completed_time = models.DateTimeField(null=True, blank=True)
    completion_notes = models.TextField(blank=True)
    
    # Call Information
    call_log = models.ForeignKey(
        'calls.CallLog',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='callback_task'
    )
    
    # Management
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_callback_tasks'
    )
    
    class Meta:
        verbose_name = "Agent Callback Task"
        verbose_name_plural = "Agent Callback Tasks"
        ordering = ['scheduled_time', '-priority']
    
    def __str__(self):
        return f"{self.agent.username} - {self.lead} callback at {self.scheduled_time}"
    
    def is_overdue(self):
        """Check if callback is overdue"""
        return self.status in ['pending', 'scheduled'] and self.scheduled_time < timezone.now()
    
    def time_until_callback(self):
        """Get time until callback in seconds"""
        if self.scheduled_time <= timezone.now():
            return 0
        return (self.scheduled_time - timezone.now()).total_seconds()


class AgentDialerSession(TimeStampedModel):
    """
    Persistent agent leg + bridge for autodial login
    """
    STATUS_CHOICES = [
        ('connecting', 'Connecting'),
        ('ready', 'Ready'),
        ('offline', 'Offline'),
        ('error', 'Error'),
    ]

    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dialer_sessions')
    campaign = models.ForeignKey('campaigns.Campaign', on_delete=models.CASCADE)
    asterisk_server = models.ForeignKey('telephony.AsteriskServer', on_delete=models.CASCADE)

    agent_extension = models.CharField(max_length=20)
    agent_channel_id = models.CharField(max_length=100, blank=True)
    agent_bridge_id = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='connecting')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Agent Dialer Session'
        verbose_name_plural = 'Agent Dialer Sessions'

    def __str__(self):
        return f"{self.agent.username} - {self.campaign.name} ({self.status})"
