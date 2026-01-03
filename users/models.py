# users/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils import timezone
from core.models import TimeStampedModel

class UserProfile(TimeStampedModel):
    """
    Extended user profile with autodialer-specific fields
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Personal Information
    employee_id = models.CharField(max_length=20, unique=True, blank=True)
    phone_number = models.CharField(
        max_length=15,
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$', message="Enter a valid phone number")]
    )
    extension = models.CharField(max_length=10, blank=True)
    department = models.CharField(max_length=100, blank=True)
    
    # Agent Specific Fields
    agent_id = models.CharField(max_length=20, unique=True, blank=True)
    skill_level = models.CharField(
        max_length=20,
        choices=[
            ('beginner', 'Beginner'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced'),
            ('expert', 'Expert')
        ],
        default='beginner'
    )
    
    # Permissions and Settings
    can_make_outbound = models.BooleanField(default=True)
    can_receive_inbound = models.BooleanField(default=True)
    can_transfer_calls = models.BooleanField(default=True)
    can_conference_calls = models.BooleanField(default=False)
    
    # Work Schedule
    shift_start = models.TimeField(null=True, blank=True)
    shift_end = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=50, default='UTC')
    
    # Avatar and UI Preferences
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    theme_preference = models.CharField(
        max_length=10,
        choices=[('light', 'Light'), ('dark', 'Dark')],
        default='light'
    )
    
    # Status and Activity
    is_active_agent = models.BooleanField(default=False)
    last_activity = models.DateTimeField(auto_now=True)
    total_calls_made = models.IntegerField(default=0)
    total_calls_answered = models.IntegerField(default=0)
    
    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
        ordering = ['user__username']
    
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_role()}"
    
    def get_role(self):
        """Get user's primary role"""
        groups = self.user.groups.all()
        if groups:
            return groups.first().name
        return "No Role"
    
    def get_full_name(self):
        """Get user's full name or username"""
        return self.user.get_full_name() or self.user.username
    
    def is_manager(self):
        """Check if user is a manager"""
        return self.user.groups.filter(name='Manager').exists() or self.user.is_superuser
    
    def is_supervisor(self):
        """Check if user is a supervisor or manager"""
        return self.user.groups.filter(name__in=['Supervisor', 'Manager']).exists() or self.user.is_superuser
    
    def is_agent(self):
        """Check if user is an agent (any role)"""
        return self.user.groups.filter(name__in=['Agent', 'Supervisor', 'Manager']).exists() or self.user.is_superuser

class UserSession(TimeStampedModel):
    """
    Track user login sessions and activity
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    login_time = models.DateTimeField(auto_now_add=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_activity = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "User Session"
        verbose_name_plural = "User Sessions"
        ordering = ['-login_time']
    
    def __str__(self):
        return f"{self.user.username} - {self.login_time}"
    
    def duration(self):
        """Get session duration"""
        end_time = self.logout_time or timezone.now()
        return end_time - self.login_time

class AgentStatus(TimeStampedModel):
    """
    Track real-time agent status
    """
    STATUS_CHOICES = [
        ('offline', 'Offline'),
        ('available', 'Available'),
        ('busy', 'Busy'),
        ('wrapup', 'Wrap-up'),
        ('break', 'Break'),
        ('lunch', 'Lunch'),
        ('training', 'Training'),
        ('meeting', 'Meeting'),
        ('system_issues', 'System Issues'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='agent_status')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
    status_changed_at = models.DateTimeField(auto_now=True)
    break_reason = models.CharField(max_length=100, blank=True)
    current_campaign = models.ForeignKey(
        'campaigns.Campaign', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='active_agents'
    )
    
    # Current call information
    current_call_id = models.CharField(max_length=50, blank=True)
    call_start_time = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Agent Status"
        verbose_name_plural = "Agent Statuses"
    
    def __str__(self):
        return f"{self.user.username} - {self.get_status_display()}"
    
    def is_available(self):
        """Check if agent is available for calls"""
        return self.status == 'available'
    
    def set_status(self, status, reason=''):
        """Set agent status with timestamp"""
        self.status = status
        self.break_reason = reason if status == 'break' else ''
        self.status_changed_at = timezone.now()
        self.save()
