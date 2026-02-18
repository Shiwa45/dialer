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

    @property
    def total_leads(self):
        """Total number of leads in this list"""
        return self.leads.count()
    
    @property
    def new_leads(self):
        """Leads that haven't been contacted"""
        return self.leads.filter(status='new').count()
    
    @property
    def contacted_leads(self):
        """Leads that have been contacted at least once"""
        return self.leads.exclude(status='new').exclude(status='dnc').count()
    
    @property
    def used_leads(self):
        """Leads that have been called at least once"""
        return self.leads.filter(call_count__gt=0).count()
    
    @property
    def remaining_leads(self):
        """Leads that are still available for calling"""
        return self.leads.filter(
            status__in=['new', 'callback', 'no_answer', 'busy']
        ).count()
    
    @property
    def dnc_leads(self):
        """Leads marked as Do Not Call"""
        return self.leads.filter(status='dnc').count()
    
    @property
    def sale_leads(self):
        """Leads that resulted in a sale"""
        return self.leads.filter(status='sale').count()
    
    @property
    def progress_percentage(self):
        """Percentage of leads that have been used"""
        total = self.total_leads
        if total == 0:
            return 0
        return round((self.used_leads / total) * 100, 1)
    
    @property
    def completion_percentage(self):
        """Percentage of leads with final disposition (sale, dnc, not_interested)"""
        total = self.total_leads
        if total == 0:
            return 0
        completed = self.leads.filter(
            status__in=['sale', 'dnc', 'not_interested']
        ).count()
        return round((completed / total) * 100, 1)
    
    def get_status_breakdown(self):
        """Get count of leads by status"""
        return self.leads.values('status').annotate(
            count=models.Count('id')
        ).order_by('status')
    
    def get_progress_stats(self):
        """Get comprehensive progress statistics"""
        total = self.total_leads
        
        status_counts = {
            item['status']: item['count'] 
            for item in self.get_status_breakdown()
        }
        
        return {
            'total_leads': total,
            'new_leads': status_counts.get('new', 0),
            'contacted_leads': self.contacted_leads,
            'used_leads': self.used_leads,
            'remaining_leads': self.remaining_leads,
            'sale_leads': status_counts.get('sale', 0),
            'callback_leads': status_counts.get('callback', 0),
            'dnc_leads': status_counts.get('dnc', 0),
            'no_answer_leads': status_counts.get('no_answer', 0),
            'busy_leads': status_counts.get('busy', 0),
            'not_interested_leads': status_counts.get('not_interested', 0),
            'progress_percentage': self.progress_percentage,
            'completion_percentage': self.completion_percentage,
            'status_breakdown': status_counts
        }

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
        ('failed', 'Failed'),
        ('dropped', 'Dropped'),
        ('congestion', 'Congestion'),
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
    
    # Phase 2: Enhanced tracking fields
    last_dial_attempt = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Timestamp of last dial attempt (successful or not)'
    )
    dial_result = models.CharField(
        max_length=50,
        blank=True,
        default='',
        db_index=True,
        help_text='Result of last dial attempt (answered, no_answer, busy, failed, etc.)'
    )
    dial_attempts = models.PositiveIntegerField(
        default=0,
        help_text='Total number of dial attempts (includes failed attempts)'
    )
    answered_count = models.PositiveIntegerField(
        default=0,
        help_text='Number of times call was answered'
    )
    last_status_change = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When status was last changed'
    )
    
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

class LeadRecycleRule(TimeStampedModel):
    """
    Rules for automatically recycling leads based on status
    PHASE 2.4: Lead recycling configuration
    """
    RECYCLE_STATUSES = [
        ('no_answer', 'No Answer'),
        ('busy', 'Busy'),
        ('voicemail', 'Voicemail'),
        ('callback', 'Callback'),
        ('not_interested', 'Not Interested'),
    ]
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Which campaign does this rule apply to (null = all campaigns)
    campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='recycle_rules',
        help_text="Leave blank to apply to all campaigns"
    )
    
    # Which lead list does this rule apply to (null = all lists)
    lead_list = models.ForeignKey(
        'leads.LeadList',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='recycle_rules',
        help_text="Leave blank to apply to all lists"
    )
    
    # Source status - leads with this status will be recycled
    source_status = models.CharField(
        max_length=20,
        choices=RECYCLE_STATUSES,
        help_text="Recycle leads with this status"
    )
    
    # Target status - leads will be changed to this status after recycle
    target_status = models.CharField(
        max_length=20,
        default='new',
        help_text="Status to set after recycling"
    )
    
    # Timing configuration
    recycle_after_hours = models.PositiveIntegerField(
        default=24,
        help_text="Hours after last contact before recycling"
    )
    
    # Attempt limits
    max_attempts = models.PositiveIntegerField(
        default=5,
        help_text="Maximum call attempts before lead is excluded"
    )
    
    min_attempts = models.PositiveIntegerField(
        default=1,
        help_text="Minimum call attempts before eligible for recycle"
    )
    
    # Priority adjustment
    priority_adjustment = models.IntegerField(
        default=0,
        help_text="Adjust lead priority on recycle (+/- value)"
    )
    
    # Scheduling
    active_days = models.CharField(
        max_length=50,
        default='1,2,3,4,5',  # Monday to Friday
        help_text="Days of week when rule is active (1=Mon, 7=Sun)"
    )
    
    active_start_hour = models.PositiveIntegerField(
        default=9,
        help_text="Hour of day when rule becomes active (0-23)"
    )
    
    active_end_hour = models.PositiveIntegerField(
        default=17,
        help_text="Hour of day when rule stops being active (0-23)"
    )
    
    # Control
    is_active = models.BooleanField(default=True)
    
    # Statistics
    last_run = models.DateTimeField(null=True, blank=True)
    total_recycled = models.PositiveIntegerField(default=0)
    
    class Meta:
        verbose_name = "Lead Recycle Rule"
        verbose_name_plural = "Lead Recycle Rules"
        ordering = ['name']
    
    def __str__(self):
        campaign_name = self.campaign.name if self.campaign else "All Campaigns"
        return f"{self.name} ({self.source_status} -> {self.target_status}) - {campaign_name}"
    
    def is_currently_active(self):
        """Check if rule is active at current time"""
        if not self.is_active:
            return False
        
        now = timezone.now()
        
        # Check day of week
        current_day = str(now.isoweekday())  # 1=Monday, 7=Sunday
        active_days = self.active_days.split(',')
        if current_day not in active_days:
            return False
        
        # Check hour
        current_hour = now.hour
        if current_hour < self.active_start_hour or current_hour >= self.active_end_hour:
            return False
        
        return True
    
    def get_eligible_leads(self):
        """
        Get leads eligible for recycling under this rule
        """
        # Avoid circular import
        from leads.models import Lead
        
        cutoff_time = timezone.now() - timezone.timedelta(hours=self.recycle_after_hours)
        
        queryset = Lead.objects.filter(
            status=self.source_status,
            call_count__gte=self.min_attempts,
            call_count__lt=self.max_attempts
        )
        
        # Filter by last contact time
        queryset = queryset.filter(
            models.Q(last_contact_date__lte=cutoff_time) |
            models.Q(last_contact_date__isnull=True)
        )
        
        # Filter by campaign if specified
        if self.campaign:
            queryset = queryset.filter(
                lead_list__assigned_campaign=self.campaign
            )
        
        # Filter by lead list if specified
        if self.lead_list:
            queryset = queryset.filter(lead_list=self.lead_list)
        
        return queryset


class LeadRecycleLog(TimeStampedModel):
    """
    Log of lead recycling actions
    """
    rule = models.ForeignKey(
        LeadRecycleRule,
        on_delete=models.SET_NULL,
        null=True,
        related_name='logs'
    )
    
    lead = models.ForeignKey(
        'leads.Lead',
        on_delete=models.CASCADE,
        related_name='recycle_logs'
    )
    
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    old_call_count = models.PositiveIntegerField(default=0)
    
    recycled_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Lead Recycle Log"
        verbose_name_plural = "Lead Recycle Logs"
        ordering = ['-recycled_at']
    
    def __str__(self):
        return f"Lead {self.lead_id}: {self.old_status} -> {self.new_status}"

