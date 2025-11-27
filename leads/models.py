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
    is_active = models.BooleanField(default=True)
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags")
    # Optional: automatically queue this list's leads to a campaign
    assigned_campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lead_lists',
        help_text="If set, leads in this list will be auto-queued to the campaign."
    )
    
    # Assignment and Access
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_lead_lists')
    
    class Meta:
        verbose_name = "Lead List"
        verbose_name_plural = "Lead Lists"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name}"

class Lead(TimeStampedModel):
    """
    Individual lead/prospect information
    """
    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('callback', 'Callback Scheduled'),
        ('sale', 'Sale'),
        ('no_answer', 'No Answer'),
        ('busy', 'Busy'),
        ('not_interested', 'Not Interested'),
        ('dnc', 'Do Not Call'),
        ('invalid', 'Invalid'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    
    # Basic Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    
    # Contact Information
    phone_number = models.CharField(
        max_length=20,
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$', message="Enter a valid phone number")]
    )
    email = models.EmailField(blank=True)
    
    # Address Information (updated field names to match templates)
    address = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    company = models.CharField(max_length=200, blank=True)
    
    # Lead Management
    lead_list = models.ForeignKey(LeadList, on_delete=models.CASCADE, related_name='leads', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    
    # Call Management
    call_count = models.PositiveIntegerField(default=0)
    last_contact_date = models.DateTimeField(null=True, blank=True)
    
    # Assignment (updated field name to match templates)
    assigned_user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_leads'
    )
    
    # Additional Information
    comments = models.TextField(blank=True)
    source = models.CharField(max_length=200, blank=True, default='Manual Entry')
    
    class Meta:
        verbose_name = "Lead"
        verbose_name_plural = "Leads"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['phone_number']),
            models.Index(fields=['status']),
            models.Index(fields=['last_contact_date']),
            models.Index(fields=['assigned_user']),
        ]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.phone_number}"
    
    def get_full_name(self):
        """Get full name of the lead"""
        return f"{self.first_name} {self.last_name}".strip()
    
    def can_be_called(self):
        """Check if lead can be called based on various criteria"""
        if self.status in ['sale', 'dnc', 'invalid']:
            return False
        return True
    
    def days_since_created(self):
        """Calculate days since lead was created"""
        delta = timezone.now() - self.created_at
        return delta.days

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

class DNCEntry(TimeStampedModel):
    """
    Do Not Call entries - simplified single model
    """
    phone_number = models.CharField(
        max_length=20,
        unique=True,
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$', message="Enter a valid phone number")]
    )
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True, default="Manual Entry")
    
    class Meta:
        verbose_name = "DNC Entry"
        verbose_name_plural = "DNC Entries"
        indexes = [
            models.Index(fields=['phone_number']),
        ]
    
    def __str__(self):
        return f"{self.phone_number} - DNC"

class LeadImport(TimeStampedModel):
    """
    Track lead import jobs and their status
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lead_list = models.ForeignKey(LeadList, on_delete=models.CASCADE, related_name='imports')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # File Information
    file = models.FileField(upload_to='lead_imports/', null=True, blank=True)
    
    # Import Configuration
    skip_duplicates = models.BooleanField(default=True)
    check_dnc = models.BooleanField(default=True)
    field_mapping = models.JSONField(default=dict, blank=True)
    
    # Statistics
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    successful_imports = models.PositiveIntegerField(default=0)
    failed_imports = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    
    # Error Handling
    error_message = models.TextField(blank=True)
    
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

class LeadRecyclingRule(TimeStampedModel):
    """
    Rules for automatically recycling leads
    """
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Rule Criteria
    source_status = models.CharField(max_length=20, choices=Lead.STATUS_CHOICES)
    target_status = models.CharField(max_length=20, choices=Lead.STATUS_CHOICES)
    days_since_contact = models.PositiveIntegerField(default=7)
    max_attempts = models.PositiveIntegerField(default=3)
    
    # Settings
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Lead Recycling Rule"
        verbose_name_plural = "Lead Recycling Rules"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name}"

class LeadFilter(TimeStampedModel):
    """
    Saved lead filters for users
    """
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    filter_criteria = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Lead Filter"
        verbose_name_plural = "Lead Filters"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name}"

# apps.py
from django.apps import AppConfig

class LeadsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'leads'
    verbose_name = 'Lead Management'
    
    def ready(self):
        import leads.signals  # noqa

# __init__.py
default_app_config = 'leads.apps.LeadsConfig'
