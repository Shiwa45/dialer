# ================================
# settings/models.py

from django.db import models
from django.contrib.auth.models import User
from core.models import TimeStampedModel

class SystemConfiguration(TimeStampedModel):
    """
    System-wide configuration beyond basic settings
    """
    CONFIG_CATEGORIES = [
        ('general', 'General'),
        ('telephony', 'Telephony'),
        ('campaigns', 'Campaigns'),
        ('leads', 'Leads'),
        ('agents', 'Agents'),
        ('security', 'Security'),
        ('email', 'Email'),
        ('notifications', 'Notifications'),
    ]
    
    category = models.CharField(max_length=20, choices=CONFIG_CATEGORIES)
    name = models.CharField(max_length=100)
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    default_value = models.TextField(blank=True)
    description = models.TextField(blank=True)
    
    # Data Type and Validation
    data_type = models.CharField(
        max_length=20,
        choices=[
            ('string', 'String'),
            ('integer', 'Integer'),
            ('float', 'Float'),
            ('boolean', 'Boolean'),
            ('json', 'JSON'),
            ('email', 'Email'),
            ('url', 'URL'),
            ('password', 'Password'),
        ],
        default='string'
    )
    validation_rules = models.JSONField(default=dict, blank=True)
    
    # Management
    is_system = models.BooleanField(default=False, help_text="System settings cannot be deleted")
    requires_restart = models.BooleanField(default=False)
    is_sensitive = models.BooleanField(default=False, help_text="Sensitive data (passwords, etc.)")
    last_modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name = "System Configuration"
        verbose_name_plural = "System Configurations"
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.get_category_display()} - {self.name}"

class EmailTemplate(TimeStampedModel):
    """
    Email templates for notifications and reports
    """
    TEMPLATE_TYPES = [
        ('welcome', 'Welcome Email'),
        ('password_reset', 'Password Reset'),
        ('report_delivery', 'Report Delivery'),  # Longest value
        ('alert', 'System Alert'),
        ('callback_reminder', 'Callback Reminder'),
        ('campaign_notification', 'Campaign Notification'),
        ('custom', 'Custom Template'),
    ]
    
    name = models.CharField(max_length=200)
    template_type = models.CharField(max_length=22, choices=TEMPLATE_TYPES)  # Updated max_length
    subject = models.CharField(max_length=200)
    body_text = models.TextField(help_text="Plain text version")
    body_html = models.TextField(blank=True, help_text="HTML version")
    
    # Template Variables
    available_variables = models.JSONField(
        default=list,
        help_text="Available template variables"
    )
    
    # Management
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name = "Email Template"
        verbose_name_plural = "Email Templates"
        ordering = ['template_type', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"

class NotificationRule(TimeStampedModel):
    """
    Rules for system notifications and alerts
    """
    TRIGGER_TYPES = [
        ('campaign_start', 'Campaign Started'),
        ('campaign_stop', 'Campaign Stopped'),
        ('high_abandon_rate', 'High Abandon Rate'),
        ('agent_login', 'Agent Login'),
        ('agent_logout', 'Agent Logout'),
        ('system_error', 'System Error'),
        ('low_lead_count', 'Low Lead Count'),
        ('callback_due', 'Callback Due'),
        ('recording_failure', 'Recording Failure'),
    ]
    
    NOTIFICATION_METHODS = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('in_app', 'In-App Notification'),
        ('webhook', 'Webhook'),
    ]
    
    name = models.CharField(max_length=200)
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_TYPES)
    description = models.TextField(blank=True)
    
    # Conditions
    conditions = models.JSONField(default=dict, help_text="Trigger conditions")
    
    # Notification Settings
    notification_method = models.CharField(max_length=20, choices=NOTIFICATION_METHODS)
    recipients = models.JSONField(default=list, help_text="List of recipients")
    message_template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # Control
    is_active = models.BooleanField(default=True)
    cooldown_period = models.PositiveIntegerField(
        default=300,
        help_text="Cooldown period in seconds to prevent spam"
    )
    max_notifications_per_hour = models.PositiveIntegerField(default=10)
    
    # Management
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    last_triggered = models.DateTimeField(null=True, blank=True)
    trigger_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        verbose_name = "Notification Rule"
        verbose_name_plural = "Notification Rules"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} - {self.get_trigger_type_display()}"

class AuditLog(TimeStampedModel):
    """
    System audit logging for compliance and security
    """
    ACTION_TYPES = [
        ('login', 'User Login'),
        ('logout', 'User Logout'),
        ('create', 'Record Created'),
        ('update', 'Record Updated'),
        ('delete', 'Record Deleted'),
        ('view', 'Record Viewed'),
        ('export', 'Data Exported'),
        ('import', 'Data Imported'),
        ('config_change', 'Configuration Changed'),
        ('permission_change', 'Permission Changed'),
    ]
    
    # User and Action
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    description = models.TextField()
    
    # Object Information
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=100, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    
    # Change Details
    changes = models.JSONField(default=dict, blank=True, help_text="Before/after values")
    
    # Context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    session_key = models.CharField(max_length=40, blank=True)
    
    # Additional Data
    extra_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['action_type', 'created_at']),
            models.Index(fields=['object_type', 'object_id']),
        ]
    
    def __str__(self):
        user_str = self.user.username if self.user else 'System'
        return f"{user_str} - {self.get_action_type_display()}"

class Backup(TimeStampedModel):
    """
    System backup tracking
    """
    BACKUP_TYPES = [
        ('full', 'Full Backup'),
        ('incremental', 'Incremental Backup'),
        ('database', 'Database Only'),
        ('files', 'Files Only'),
        ('configuration', 'Configuration Only'),
    ]
    
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    name = models.CharField(max_length=200)
    backup_type = models.CharField(max_length=20, choices=BACKUP_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    
    # Timing
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # File Information
    file_path = models.CharField(max_length=1000, blank=True)
    file_size = models.PositiveIntegerField(default=0, help_text="File size in bytes")
    compression_ratio = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Verification
    checksum = models.CharField(max_length=64, blank=True)
    is_verified = models.BooleanField(default=False)
    
    # Management
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    retention_days = models.PositiveIntegerField(default=30)
    notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Backup"
        verbose_name_plural = "Backups"
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.name} - {self.started_at.date()}"

