# campaigns/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from core.models import TimeStampedModel
import uuid

def generate_uuid():
    return str(uuid.uuid4())

class Campaign(TimeStampedModel):
    """
    Main campaign model for outbound/inbound campaigns
    """
    CAMPAIGN_TYPES = [
        ('outbound', 'Outbound'),
        ('inbound', 'Inbound'),
        ('blended', 'Blended'),
    ]
    
    DIAL_METHODS = [
        ('manual', 'Manual'),
        ('preview', 'Preview'),
        ('progressive', 'Progressive'), 
        ('predictive', 'Predictive'),
        ('auto', 'Auto'),
    ]
    
    STATUS_CHOICES = [
        ('inactive', 'Inactive'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    campaign_id = models.CharField(max_length=50, unique=True, default=generate_uuid, editable=False)
    
    # Campaign Type and Method
    campaign_type = models.CharField(max_length=20, choices=CAMPAIGN_TYPES, default='outbound')
    dial_method = models.CharField(max_length=20, choices=DIAL_METHODS, default='preview')
    
    # Status and Control
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inactive')
    is_active = models.BooleanField(default=False)
    
    # Timezone choices
    TIMEZONE_CHOICES = [
        ('UTC', 'UTC (Coordinated Universal Time)'),
        ('America/New_York', 'Eastern Time (ET)'),
        ('America/Chicago', 'Central Time (CT)'),
        ('America/Denver', 'Mountain Time (MT)'),
        ('America/Los_Angeles', 'Pacific Time (PT)'),
        ('America/Phoenix', 'Arizona Time (MST)'),
        ('America/Anchorage', 'Alaska Time (AKST)'),
        ('Pacific/Honolulu', 'Hawaii Time (HST)'),
        ('Asia/Kolkata', 'India Standard Time (IST)'),
        ('Europe/London', 'Greenwich Mean Time (GMT)'),
        ('Europe/Paris', 'Central European Time (CET)'),
        ('Asia/Tokyo', 'Japan Standard Time (JST)'),
        ('Asia/Shanghai', 'China Standard Time (CST)'),
        ('Australia/Sydney', 'Australian Eastern Time (AEST)'),
    ]
    
    # Scheduling
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    daily_start_time = models.TimeField(default='09:00:00')
    daily_end_time = models.TimeField(default='17:00:00')
    timezone = models.CharField(max_length=50, choices=TIMEZONE_CHOICES, default='UTC')
    
    # Call Settings
    max_attempts = models.PositiveIntegerField(default=3)
    call_timeout = models.PositiveIntegerField(default=30, help_text="Timeout in seconds")
    retry_delay = models.PositiveIntegerField(default=3600, help_text="Delay between retries in seconds")
    
    # Dialing Parameters
    dial_ratio = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)
    dial_level = models.DecimalField(
        max_digits=4, 
        decimal_places=2, 
        default=1.0,
        help_text="Predictive dial multiplier: calls per available agent (e.g., 1.5 = 1.5 calls per agent)"
    )
    max_lines = models.PositiveIntegerField(default=10)
    abandon_rate = models.DecimalField(max_digits=5, decimal_places=2, default=3.0)
    hopper_size = models.PositiveIntegerField(
        default=500,
        help_text="Max leads to keep in the hopper/cache for this campaign"
    )
    hopper_level = models.PositiveIntegerField(
        default=100,
        help_text="Target number of leads to maintain in hopper (refills when below this)"
    )
    dial_timeout = models.PositiveIntegerField(
        default=30,
        help_text="Seconds to wait for call answer before considering failed"
    )
    local_call_time = models.BooleanField(
        default=True,
        help_text="Respect lead timezone for calling hours"
    )
    wrapup_timeout = models.PositiveIntegerField(
        default=120,
        help_text="Seconds an agent can remain in wrap-up before auto-available"
    )
    
    # Recording and Monitoring
    enable_recording = models.BooleanField(default=True)
    recording_delay = models.PositiveIntegerField(default=0, help_text="Recording delay in seconds")
    monitor_agents = models.BooleanField(default=False)
    
    # Lead Management
    lead_order = models.CharField(
        max_length=20,
        choices=[
            ('down', 'Down (Sequential)'),
            ('up', 'Up (Reverse)'),
            ('random', 'Random'),
            ('oldest_first', 'Oldest First'),
            ('newest_first', 'Newest First'),
        ],
        default='down'
    )
    
    # DNC and Compliance
    use_internal_dnc = models.BooleanField(default=True)
    use_campaign_dnc = models.BooleanField(default=False)
    amd_enabled = models.BooleanField(default=False, help_text="Answering Machine Detection")
    
    # Dialing speed presets (UI-level); maps to effective dials per agent
    DIAL_SPEED = [
        ('slow', 'Slow'),
        ('normal', 'Normal'),
        ('fast', 'Fast'),
        ('very_fast', 'Very Fast'),
        ('custom', 'Custom'),
    ]
    # Predictive dialer settings (Phase 4.1)
    dial_mode = models.CharField(
        max_length=20,
        choices=[
            ('predictive', 'Predictive'),
            ('progressive', 'Progressive'),
            ('power', 'Power'),
            ('preview', 'Preview'),
        ],
        default='predictive'
    )
    target_abandon_rate = models.FloatField(default=3.0)
    max_dial_ratio = models.FloatField(default=3.0)
    avg_talk_time = models.IntegerField(default=180)
    wrapup_time = models.IntegerField(default=30)
    
    # AMD settings
    amd_enabled = models.BooleanField(default=False)
    amd_action = models.CharField(
        max_length=20,
        choices=[
            ('hangup', 'Hangup'),
            ('voicemail', 'Drop Voicemail'),
            ('transfer', 'Transfer'),
        ],
        default='hangup'
    )
    voicemail_file = models.FileField(
        upload_to='voicemail/',
        blank=True,
        null=True
    )

    # ROI tracking (Phase 4.3)
    cost_per_minute = models.DecimalField(
        max_digits=6, decimal_places=4, default=0.03
    )
    revenue_per_sale = models.DecimalField(
        max_digits=10, decimal_places=2, default=100
    )
    agent_hourly_cost = models.DecimalField(
        max_digits=6, decimal_places=2, default=15
    )

    dial_speed = models.CharField(max_length=20, choices=DIAL_SPEED, default='normal')
    custom_dials_per_agent = models.PositiveIntegerField(default=1, help_text="Used when dial_speed=custom")
    
    # Preferred outbound carrier (optional, syncs dial_prefix on save)
    outbound_carrier = models.ForeignKey(
        'telephony.Carrier', on_delete=models.SET_NULL, null=True, blank=True, related_name='preferred_campaigns'
    )
    # Outbound routing
    dial_prefix = models.CharField(
        max_length=20,
        blank=True,
        help_text="Optional prefix to prepend to dialed numbers"
    )
    # Advanced: multiple trunks with weights
    
    # Assignment
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_campaigns')
    assigned_users = models.ManyToManyField(User, through='CampaignAgent', related_name='assigned_campaigns')
    
    # Statistics (updated in real-time)
    total_leads = models.PositiveIntegerField(default=0)
    leads_called = models.PositiveIntegerField(default=0)
    leads_remaining = models.PositiveIntegerField(default=0)
    calls_today = models.PositiveIntegerField(default=0)
    
    class Meta:
        verbose_name = "Campaign"
        verbose_name_plural = "Campaigns"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_campaign_type_display()})"
    
    def start_campaign(self):
        """Start the campaign"""
        self.status = 'active'
        self.is_active = True
        self.save()
    
    def stop_campaign(self):
        """Stop the campaign"""
        self.status = 'inactive'
        self.is_active = False
        self.save()
    
    def pause_campaign(self):
        """Pause the campaign"""
        self.status = 'paused'
        self.save()

    def save(self, *args, **kwargs):
        # Auto-sync campaign dial_prefix from selected outbound_carrier if present
        try:
            if getattr(self, 'outbound_carrier', None) and self.outbound_carrier and self.outbound_carrier.dial_prefix:
                self.dial_prefix = self.outbound_carrier.dial_prefix
        except Exception:
            pass
        super().save(*args, **kwargs)

class CampaignAgent(TimeStampedModel):
    """
    Through model for Campaign-User relationship with additional fields
    """
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Agent Assignment Details
    assigned_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    max_calls_per_day = models.PositiveIntegerField(null=True, blank=True)
    priority = models.PositiveIntegerField(default=1)
    
    # Performance tracking
    calls_made = models.PositiveIntegerField(default=0)
    calls_answered = models.PositiveIntegerField(default=0)
    sales_made = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ['campaign', 'user']
        verbose_name = "Campaign Agent"
        verbose_name_plural = "Campaign Agents"
    
    def save(self, *args, **kwargs):
        """
        PHASE 1.4 FIX: When activating an agent assignment,
        automatically deactivate all other assignments for this user.
        """
        if self.is_active:
            # Deactivate all other campaign assignments for this user
            CampaignAgent.objects.filter(
                user=self.user,
                is_active=True
            ).exclude(pk=self.pk).update(is_active=False)
            
            # Also update the user's current campaign in AgentStatus
            try:
                from users.models import AgentStatus
                AgentStatus.objects.filter(user=self.user).update(
                    current_campaign=self.campaign
                )
            except Exception:
                pass
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.campaign.name}"

class Disposition(TimeStampedModel):
    """
    Call dispositions/outcomes
    """
    DISPOSITION_CATEGORIES = [
        ('sale', 'Sale'),
        ('callback', 'Callback'),
        ('no_answer', 'No Answer'),
        ('busy', 'Busy'),
        ('not_interested', 'Not Interested'),
        ('dnc', 'Do Not Call'),
        ('wrong_number', 'Wrong Number'),
        ('answering_machine', 'Answering Machine'),
        ('other', 'Other'),
    ]
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    category = models.CharField(max_length=20, choices=DISPOSITION_CATEGORIES)
    description = models.TextField(blank=True)
    
    # Behavior Settings
    is_sale = models.BooleanField(default=False)
    requires_callback = models.BooleanField(default=False)
    callback_delay = models.PositiveIntegerField(default=3600, help_text="Callback delay in seconds")
    removes_from_campaign = models.BooleanField(default=False)
    adds_to_dnc = models.BooleanField(default=False)
    
    # Display Settings
    color = models.CharField(max_length=7, default="#6c757d", help_text="Hex color code")
    hotkey = models.CharField(max_length=1, blank=True, help_text="Single character hotkey")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        verbose_name = "Disposition"
        verbose_name_plural = "Dispositions"
        ordering = ['sort_order', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"

class CampaignDisposition(TimeStampedModel):
    """
    Link dispositions to specific campaigns
    """
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='dispositions')
    disposition = models.ForeignKey(Disposition, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ['campaign', 'disposition']
        ordering = ['sort_order']
    
    def __str__(self):
        return f"{self.campaign.name} - {self.disposition.name}"

class Script(TimeStampedModel):
    """
    Call scripts for campaigns
    """
    SCRIPT_TYPES = [
        ('opening', 'Opening Script'),
        ('main', 'Main Script'),
        ('objection', 'Objection Handling'),
        ('closing', 'Closing Script'),
        ('callback', 'Callback Script'),
    ]
    
    name = models.CharField(max_length=200)
    script_type = models.CharField(max_length=20, choices=SCRIPT_TYPES, default='main')
    content = models.TextField()
    is_active = models.BooleanField(default=True)
    
    # Assignment
    campaigns = models.ManyToManyField(Campaign, related_name='scripts', blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Script"
        verbose_name_plural = "Scripts"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_script_type_display()})"

class CampaignStats(TimeStampedModel):
    """
    Daily campaign statistics
    """
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='daily_stats')
    date = models.DateField()
    
    # Call Statistics
    calls_made = models.PositiveIntegerField(default=0)
    calls_answered = models.PositiveIntegerField(default=0)
    calls_dropped = models.PositiveIntegerField(default=0)
    drop_count = models.PositiveIntegerField(
        default=0,
        help_text="Calls answered by customer but no agent available (compliance metric)"
    )
    
    # Lead Statistics
    leads_processed = models.PositiveIntegerField(default=0)
    leads_dispositioned = models.PositiveIntegerField(default=0)
    
    # Time Statistics
    total_talk_time = models.PositiveIntegerField(default=0, help_text="Total talk time in seconds")
    total_wait_time = models.PositiveIntegerField(default=0, help_text="Total wait time in seconds")
    
    # Performance Metrics
    contact_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    conversion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    average_call_duration = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ['campaign', 'date']
        verbose_name = "Campaign Statistics"
        verbose_name_plural = "Campaign Statistics"
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.campaign.name} - {self.date}"

class CampaignHours(TimeStampedModel):
    """
    Campaign operating hours by day of week
    """
    DAYS_OF_WEEK = [
        (0, 'Monday'),
        (1, 'Tuesday'), 
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='operating_hours')
    day_of_week = models.PositiveSmallIntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['campaign', 'day_of_week']
        verbose_name = "Campaign Hours"
        verbose_name_plural = "Campaign Hours"
        ordering = ['day_of_week']
    
    def __str__(self):
        return f"{self.campaign.name} - {self.get_day_of_week_display()}"


class CampaignCarrier(TimeStampedModel):
    """
    Through model for Campaign ↔ Carrier (trunk) with weight and round-robin tracking
    """
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='campaign_carriers')
    carrier = models.ForeignKey('telephony.Carrier', on_delete=models.CASCADE, related_name='carrier_campaigns')
    weight = models.PositiveIntegerField(default=1)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('campaign', 'carrier')
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.campaign.name} ↔ {self.carrier.name} (w={self.weight})"


class OutboundQueue(TimeStampedModel):
    """
    Queue for autodial numbers per campaign
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('dialing', 'Dialing'),
        ('answered', 'Answered'),
        ('failed', 'Failed'),
        ('completed', 'Completed'),
    ]
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='outbound_queue')
    lead = models.ForeignKey('leads.Lead', on_delete=models.SET_NULL, null=True, blank=True)
    phone_number = models.CharField(max_length=32)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    attempts = models.PositiveIntegerField(default=0)
    last_tried_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['status', 'last_tried_at'])
        ]
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.campaign.name} - {self.phone_number} ({self.status})"


class DialerHopper(TimeStampedModel):
    """
    Vicidial-style hopper for predictive/progressive dialing
    Holds eligible leads ready to be dialed
    """
    HOPPER_STATUS = [
        ('new', 'New'),
        ('locked', 'Locked'),
        ('dialing', 'Dialing'),
        ('completed', 'Completed'),
        ('dropped', 'Dropped'),
        ('failed', 'Failed'),
    ]
    
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='hopper_entries')
    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, related_name='hopper_entries')
    phone_number = models.CharField(max_length=32)
    
    # Priority: 1-99, higher = dialed sooner
    priority = models.PositiveIntegerField(default=50, validators=[MinValueValidator(1), MaxValueValidator(99)])
    
    status = models.CharField(max_length=20, choices=HOPPER_STATUS, default='new')
    hopper_entry_time = models.DateTimeField(auto_now_add=True)
    
    # Tracking
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='locked_hopper_entries')
    locked_at = models.DateTimeField(null=True, blank=True)
    dialed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Call tracking
    channel_id = models.CharField(max_length=100, blank=True)
    call_log = models.ForeignKey('calls.CallLog', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['campaign', 'status', '-priority']),
            models.Index(fields=['status', 'hopper_entry_time']),
            models.Index(fields=['campaign', 'lead']),
        ]
        ordering = ['-priority', 'hopper_entry_time']
        verbose_name = "Dialer Hopper Entry"
        verbose_name_plural = "Dialer Hopper Entries"
    
    def __str__(self):
        return f"{self.campaign.name} - {self.phone_number} (P:{self.priority}, {self.status})"
    
    def lock_for_dialing(self, user=None):
        """Lock this hopper entry for dialing"""
        self.status = 'locked'
        self.locked_by = user
        self.locked_at = timezone.now()
        self.save(update_fields=['status', 'locked_by', 'locked_at', 'updated_at'])
    
    def mark_dialing(self, channel_id):
        """Mark as currently dialing"""
        self.status = 'dialing'
        self.channel_id = channel_id
        self.dialed_at = timezone.now()
        self.save(update_fields=['status', 'channel_id', 'dialed_at', 'updated_at'])
    
    def mark_completed(self, call_log=None):
        """Mark as successfully completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if call_log:
            self.call_log = call_log
        self.save(update_fields=['status', 'completed_at', 'call_log', 'updated_at'])
    
    def mark_dropped(self):
        """Mark as dropped (answered but no agent available)"""
        self.status = 'dropped'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])
    
    def mark_failed(self):
        """Mark as failed"""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

# campaigns/apps.py
from django.apps import AppConfig

class CampaignsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'campaigns'
    verbose_name = 'Campaign Management'

# campaigns/__init__.py
default_app_config = 'campaigns.apps.CampaignsConfig'
