# leads/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils import timezone
from core.models import TimeStampedModel
import uuid

class LeadList(TimeStampedModel):
    """
    Lead lists to organize and group leads
    """
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    list_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    
    # Assignment and Access
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_lead_lists')
    is_active = models.BooleanField(default=True)
    
    # Import Information
    source_file = models.CharField(max_length=500, blank=True)
    import_date = models.DateTimeField(null=True, blank=True)
    
    # Statistics
    total_leads = models.PositiveIntegerField(default=0)
    active_leads = models.PositiveIntegerField(default=0)
    called_leads = models.PositiveIntegerField(default=0)
    
    class Meta:
        verbose_name = "Lead List"
        verbose_name_plural = "Lead Lists"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.total_leads} leads)"

class Lead(TimeStampedModel):
    """
    Individual lead/prospect information
    """
    STATUS_CHOICES = [
        ('new', 'New'),
        ('called', 'Called'),
        ('callback', 'Callback Scheduled'),
        ('interested', 'Interested'),
        ('not_interested', 'Not Interested'),
        ('sale', 'Sale'),
        ('dnc', 'Do Not Call'),
        ('invalid', 'Invalid'),
    ]
    
    # Basic Information
    lead_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    
    # Name Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    title = models.CharField(max_length=50, blank=True)
    
    # Contact Information
    phone_number = models.CharField(
        max_length=20,
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$', message="Enter a valid phone number")]
    )
    alt_phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    
    # Address Information
    address1 = models.CharField(max_length=200, blank=True)
    address2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default='US')
    
    # Lead Management
    lead_list = models.ForeignKey(LeadList, on_delete=models.CASCADE, related_name='leads')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    priority = models.PositiveIntegerField(default=1)
    
    # Call Management
    call_count = models.PositiveIntegerField(default=0)
    last_called = models.DateTimeField(null=True, blank=True)
    next_call_time = models.DateTimeField(null=True, blank=True)
    
    # Assignment
    assigned_agent = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_leads'
    )
    assigned_campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaign_leads'
    )
    
    # Time Management
    best_time_to_call = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(max_length=50, default='UTC')
    
    # Additional Information
    comments = models.TextField(blank=True)
    source = models.CharField(max_length=200, blank=True)
    
    # Custom Fields (JSON for flexibility)
    custom_fields = models.JSONField(default=dict, blank=True)
    
    # Flags
    is_dnc = models.BooleanField(default=False)
    is_callback = models.BooleanField(default=False)
    is_priority = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Lead"
        verbose_name_plural = "Leads"
        ordering = ['priority', 'last_called']
        indexes = [
            models.Index(fields=['phone_number']),
            models.Index(fields=['status']),
            models.Index(fields=['last_called']),
            models.Index(fields=['assigned_agent']),
        ]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.phone_number}"
    
    def get_full_name(self):
        """Get full name of the lead"""
        return f"{self.first_name} {self.last_name}".strip()
    
    def can_be_called(self):
        """Check if lead can be called based on various criteria"""
        if self.is_dnc:
            return False
        if self.status in ['sale', 'dnc', 'invalid']:
            return False
        if self.next_call_time and self.next_call_time > timezone.now():
            return False
        return True

class LeadNote(TimeStampedModel):
    """
    Notes/comments added to leads
    """
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='notes')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    note = models.TextField()
    is_important = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Lead Note"
        verbose_name_plural = "Lead Notes"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Note for {self.lead.get_full_name()} by {self.user.username}"

class LeadHistory(TimeStampedModel):
    """
    Track lead status changes and activities
    """
    ACTION_TYPES = [
        ('created', 'Lead Created'),
        ('called', 'Call Made'),
        ('status_change', 'Status Changed'),
        ('assigned', 'Agent Assigned'),
        ('note_added', 'Note Added'),
        ('imported', 'Lead Imported'),
        ('callback_scheduled', 'Callback Scheduled'),
    ]
    
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='history')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    description = models.TextField()
    
    # Track changes
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Lead History"
        verbose_name_plural = "Lead Histories"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.lead.get_full_name()} - {self.get_action_type_display()}"

class DNCList(TimeStampedModel):
    """
    Do Not Call list management
    """
    DNC_TYPES = [
        ('internal', 'Internal DNC'),
        ('campaign', 'Campaign Specific'),
        ('federal', 'Federal DNC'),
        ('state', 'State DNC'),
        ('custom', 'Custom List'),
    ]
    
    name = models.CharField(max_length=200)
    dnc_type = models.CharField(max_length=20, choices=DNC_TYPES, default='internal')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    # Management
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "DNC List"
        verbose_name_plural = "DNC Lists"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_dnc_type_display()})"

class DNCEntry(TimeStampedModel):
    """
    Individual DNC entries
    """
    dnc_list = models.ForeignKey(DNCList, on_delete=models.CASCADE, related_name='entries')
    phone_number = models.CharField(
        max_length=20,
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$', message="Enter a valid phone number")]
    )
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    
    class Meta:
        unique_together = ['dnc_list', 'phone_number']
        verbose_name = "DNC Entry"
        verbose_name_plural = "DNC Entries"
        indexes = [
            models.Index(fields=['phone_number']),
        ]
    
    def __str__(self):
        return f"{self.phone_number} in {self.dnc_list.name}"
    
    def is_active(self):
        """Check if DNC entry is still active"""
        if not self.dnc_list.is_active:
            return False
        if self.expires_on and self.expires_on < timezone.now().date():
            return False
        return True

class LeadImport(TimeStampedModel):
    """
    Track lead import jobs and their status
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # File Information
    file_name = models.CharField(max_length=500)
    file_path = models.CharField(max_length=1000)
    file_size = models.PositiveIntegerField(default=0)
    
    # Import Configuration
    lead_list = models.ForeignKey(LeadList, on_delete=models.CASCADE, related_name='imports')
    skip_duplicates = models.BooleanField(default=True)
    update_existing = models.BooleanField(default=False)
    
    # Field Mapping (JSON)
    field_mapping = models.JSONField(default=dict)
    
    # Statistics
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    imported_leads = models.PositiveIntegerField(default=0)
    skipped_leads = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    
    # Management
    started_by = models.ForeignKey(User, on_delete=models.CASCADE)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Error Handling
    error_log = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Lead Import"
        verbose_name_plural = "Lead Imports"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.get_status_display()}"
    
    def progress_percentage(self):
        """Calculate import progress percentage"""
        if self.total_rows == 0:
            return 0
        return round((self.processed_rows / self.total_rows) * 100, 2)

class CallbackSchedule(TimeStampedModel):
    """
    Scheduled callbacks for leads
    """
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='callbacks')
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='scheduled_callbacks')
    campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.CASCADE,
        related_name='scheduled_callbacks'
    )
    
    # Scheduling
    scheduled_time = models.DateTimeField()
    timezone = models.CharField(max_length=50, default='UTC')
    
    # Status
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Notes
    notes = models.TextField(blank=True)
    reminder_sent = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Callback Schedule"
        verbose_name_plural = "Callback Schedules"
        ordering = ['scheduled_time']
        indexes = [
            models.Index(fields=['scheduled_time']),
            models.Index(fields=['agent', 'is_completed']),
        ]
    
    def __str__(self):
        return f"Callback for {self.lead.get_full_name()} at {self.scheduled_time}"
    
    def is_overdue(self):
        """Check if callback is overdue"""
        return not self.is_completed and self.scheduled_time < timezone.now()

# leads/apps.py
from django.apps import AppConfig

class LeadsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'leads'
    verbose_name = 'Lead Management'

# leads/__init__.py
default_app_config = 'leads.apps.LeadsConfig'