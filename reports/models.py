# ================================
# reports/models.py

from django.db import models
from django.contrib.auth.models import User
from core.models import TimeStampedModel
import uuid

class Report(TimeStampedModel):
    """
    Custom report definitions
    """
    REPORT_TYPES = [
        ('campaign', 'Campaign Report'),
        ('agent', 'Agent Report'),
        ('call', 'Call Report'),
        ('lead', 'Lead Report'),
        ('summary', 'Summary Report'),
        ('custom', 'Custom Report'),
    ]
    
    OUTPUT_FORMATS = [
        ('web', 'Web View'),
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    report_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    
    # Report Configuration
    query_definition = models.JSONField(default=dict, help_text="Report query and filters")
    columns = models.JSONField(default=list, help_text="Report columns configuration")
    grouping = models.JSONField(default=dict, blank=True, help_text="Grouping and aggregation")
    sorting = models.JSONField(default=list, blank=True, help_text="Sorting configuration")
    
    # Formatting
    output_format = models.CharField(max_length=20, choices=OUTPUT_FORMATS, default='web')
    page_size = models.PositiveIntegerField(default=50)
    show_totals = models.BooleanField(default=True)
    
    # Access Control
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_reports')
    is_public = models.BooleanField(default=False)
    shared_with = models.ManyToManyField(User, blank=True, related_name='shared_reports')
    
    # Status
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Report"
        verbose_name_plural = "Reports"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_report_type_display()})"

class ReportSchedule(TimeStampedModel):
    """
    Scheduled report generation and delivery
    """
    FREQUENCY_CHOICES = [
        ('once', 'One Time'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200)
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='schedules')
    
    # Scheduling
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField()
    last_run = models.DateTimeField(null=True, blank=True)
    
    # Delivery
    email_recipients = models.JSONField(default=list, help_text="List of email addresses")
    include_attachment = models.BooleanField(default=True)
    email_subject = models.CharField(max_length=200, blank=True)
    email_body = models.TextField(blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Report Schedule"
        verbose_name_plural = "Report Schedules"
        ordering = ['next_run']
    
    def __str__(self):
        return f"{self.name} - {self.get_frequency_display()}"

class ReportExecution(TimeStampedModel):
    """
    Track report execution history
    """
    EXECUTION_STATUS = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='executions')
    report_schedule = models.ForeignKey(
        ReportSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executions'
    )
    
    # Execution Details
    started_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=EXECUTION_STATUS, default='running')
    
    # Results
    total_records = models.PositiveIntegerField(default=0)
    file_path = models.CharField(max_length=1000, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    
    # Error Handling
    error_message = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Report Execution"
        verbose_name_plural = "Report Executions"
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.report.name} - {self.started_at}"

class Dashboard(TimeStampedModel):
    """
    Custom dashboards with widgets
    """
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    dashboard_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    
    # Layout Configuration
    layout = models.JSONField(default=dict, help_text="Dashboard layout configuration")
    widgets = models.JSONField(default=list, help_text="Widget configurations")
    
    # Access Control
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_dashboards')
    is_public = models.BooleanField(default=False)
    shared_with = models.ManyToManyField(User, blank=True, related_name='shared_dashboards')
    
    # Settings
    auto_refresh = models.BooleanField(default=True)
    refresh_interval = models.PositiveIntegerField(default=30, help_text="Refresh interval in seconds")
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Dashboard"
        verbose_name_plural = "Dashboards"
        ordering = ['name']
    
    def __str__(self):
        return self.name

