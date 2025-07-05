# campaigns/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from core.models import TimeStampedModel
import uuid

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
    campaign_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    
    # Campaign Type and Method
    campaign_type = models.CharField(max_length=20, choices=CAMPAIGN_TYPES, default='outbound')
    dial_method = models.CharField(max_length=20, choices=DIAL_METHODS, default='preview')
    
    # Status and Control
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inactive')
    is_active = models.BooleanField(default=False)
    
    # Scheduling
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    daily_start_time = models.TimeField(default='09:00:00')
    daily_end_time = models.TimeField(default='17:00:00')
    timezone = models.CharField(max_length=50, default='UTC')
    
    # Call Settings
    max_attempts = models.PositiveIntegerField(default=3)
    call_timeout = models.PositiveIntegerField(default=30, help_text="Timeout in seconds")
    retry_delay = models.PositiveIntegerField(default=3600, help_text="Delay between retries in seconds")
    
    # Dialing Parameters
    dial_ratio = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)
    max_lines = models.PositiveIntegerField(default=10)
    abandon_rate = models.DecimalField(max_digits=5, decimal_places=2, default=3.0)
    
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

# campaigns/apps.py
from django.apps import AppConfig

class CampaignsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'campaigns'
    verbose_name = 'Campaign Management'

# campaigns/__init__.py
default_app_config = 'campaigns.apps.CampaignsConfig'