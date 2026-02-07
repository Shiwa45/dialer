"""
Phase 4 Campaign Model Extensions

Additional fields for Campaign model to support:
- Predictive dialing configuration
- AMD settings
- ROI tracking

Add these fields to your existing Campaign model in campaigns/models.py
"""

from django.db import models


# ============================================================================
# Campaign Model Extensions
# ============================================================================

"""
Add these fields to your existing Campaign model:

class Campaign(models.Model):
    # ... existing fields ...
    
    # ========================================
    # Phase 4.1: Dial Mode Settings
    # ========================================
    
    DIAL_MODE_CHOICES = [
        ('predictive', 'Predictive'),
        ('progressive', 'Progressive'),
        ('power', 'Power'),
        ('preview', 'Preview'),
    ]
    dial_mode = models.CharField(
        max_length=20,
        choices=DIAL_MODE_CHOICES,
        default='predictive',
        help_text="Dialing algorithm mode"
    )
    
    # Predictive dialer parameters
    target_abandon_rate = models.FloatField(
        default=3.0,
        help_text="Target maximum abandon rate percentage"
    )
    max_abandon_rate = models.FloatField(
        default=5.0,
        help_text="Hard limit abandon rate percentage"
    )
    min_dial_ratio = models.FloatField(
        default=1.0,
        help_text="Minimum calls per available agent"
    )
    max_dial_ratio = models.FloatField(
        default=3.0,
        help_text="Maximum calls per available agent"
    )
    
    # Timing estimates (for predictions)
    avg_talk_time = models.IntegerField(
        default=180,
        help_text="Average talk time in seconds"
    )
    wrapup_time = models.IntegerField(
        default=30,
        help_text="Default wrapup time in seconds"
    )
    
    # ========================================
    # Phase 4.1: AMD Settings
    # ========================================
    
    amd_enabled = models.BooleanField(
        default=False,
        help_text="Enable Answering Machine Detection"
    )
    
    AMD_ACTION_CHOICES = [
        ('hangup', 'Hangup'),
        ('voicemail', 'Drop Voicemail'),
        ('transfer', 'Transfer to Extension'),
    ]
    amd_action = models.CharField(
        max_length=20,
        choices=AMD_ACTION_CHOICES,
        default='hangup',
        help_text="Action when answering machine detected"
    )
    
    voicemail_file = models.FileField(
        upload_to='voicemail/',
        blank=True,
        null=True,
        help_text="Pre-recorded voicemail message to drop"
    )
    
    amd_transfer_extension = models.CharField(
        max_length=20,
        blank=True,
        help_text="Extension to transfer AMD calls to"
    )
    
    # ========================================
    # Phase 4.3: ROI Tracking
    # ========================================
    
    cost_per_minute = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=0.03,
        help_text="Telecom cost per minute"
    )
    
    revenue_per_sale = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=100.00,
        help_text="Average revenue per sale"
    )
    
    agent_hourly_cost = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=15.00,
        help_text="Average agent hourly cost"
    )


Then run:
    python manage.py makemigrations campaigns
    python manage.py migrate
"""


# ============================================================================
# Example Model Implementation
# ============================================================================

class CampaignDialerSettings(models.Model):
    """
    Alternative: Separate model for dialer settings
    
    Use this if you prefer not to modify the Campaign model directly.
    Link to Campaign via OneToOne relationship.
    """
    campaign = models.OneToOneField(
        'Campaign',
        on_delete=models.CASCADE,
        related_name='dialer_settings'
    )
    
    # Dial mode
    DIAL_MODE_CHOICES = [
        ('predictive', 'Predictive'),
        ('progressive', 'Progressive'),
        ('power', 'Power'),
        ('preview', 'Preview'),
    ]
    dial_mode = models.CharField(
        max_length=20,
        choices=DIAL_MODE_CHOICES,
        default='predictive'
    )
    
    # Predictive parameters
    target_abandon_rate = models.FloatField(default=3.0)
    max_abandon_rate = models.FloatField(default=5.0)
    min_dial_ratio = models.FloatField(default=1.0)
    max_dial_ratio = models.FloatField(default=3.0)
    safety_factor = models.FloatField(default=0.85)
    
    # Timing
    avg_talk_time = models.IntegerField(default=180)
    wrapup_time = models.IntegerField(default=30)
    
    # AMD
    amd_enabled = models.BooleanField(default=False)
    AMD_ACTION_CHOICES = [
        ('hangup', 'Hangup'),
        ('voicemail', 'Drop Voicemail'),
        ('transfer', 'Transfer'),
    ]
    amd_action = models.CharField(
        max_length=20,
        choices=AMD_ACTION_CHOICES,
        default='hangup'
    )
    voicemail_file = models.FileField(
        upload_to='voicemail/',
        blank=True,
        null=True
    )
    amd_transfer_extension = models.CharField(max_length=20, blank=True)
    
    # ROI
    cost_per_minute = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=0.03
    )
    revenue_per_sale = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=100.00
    )
    agent_hourly_cost = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=15.00
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Campaign Dialer Settings'
        verbose_name_plural = 'Campaign Dialer Settings'
    
    def __str__(self):
        return f"Dialer Settings for {self.campaign.name}"


# ============================================================================
# Celery Tasks for Predictive Dialing
# ============================================================================

"""
Add this task to campaigns/tasks.py:

from celery import shared_task
from campaigns.predictive_dialer import DialerManager
import logging

logger = logging.getLogger(__name__)

@shared_task
def predictive_dial():
    '''
    Main predictive dialing task
    
    Runs every second to dial calls based on predictive algorithm.
    For each active campaign in predictive mode, calculates optimal
    dial ratio and initiates appropriate number of calls.
    '''
    from campaigns.models import Campaign
    
    total_dialed = 0
    
    # Get all active predictive campaigns
    campaigns = Campaign.objects.filter(
        status='active',
        dial_mode='predictive'
    )
    
    for campaign in campaigns:
        try:
            dialed = DialerManager.dial_for_campaign(campaign.id)
            total_dialed += dialed
            
            if dialed > 0:
                logger.debug(f"Campaign {campaign.id}: Dialed {dialed} calls")
                
        except Exception as e:
            logger.error(f"Error dialing for campaign {campaign.id}: {e}")
    
    return {'dialed': total_dialed, 'campaigns': len(campaigns)}


@shared_task
def update_dialer_metrics():
    '''
    Update dialer metrics for monitoring
    
    Runs every 5 seconds to refresh cached metrics.
    '''
    from campaigns.models import Campaign
    from campaigns.predictive_dialer import DialerManager
    
    for campaign in Campaign.objects.filter(status='active'):
        try:
            dialer = DialerManager.get_dialer(campaign.id)
            dialer.get_metrics(force_refresh=True)
        except Exception as e:
            logger.error(f"Error updating metrics for campaign {campaign.id}: {e}")


# Add to CELERY_BEAT_SCHEDULE in settings.py:

CELERY_BEAT_SCHEDULE = {
    # ... existing tasks ...
    
    # Phase 4.1: Predictive dialing (every second)
    'predictive-dial': {
        'task': 'campaigns.tasks.predictive_dial',
        'schedule': 1.0,
    },
    
    # Phase 4.1: Update dialer metrics (every 5 seconds)
    'update-dialer-metrics': {
        'task': 'campaigns.tasks.update_dialer_metrics',
        'schedule': 5.0,
    },
}
"""
