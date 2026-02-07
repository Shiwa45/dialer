"""
Phase 4 Quality Models

Django models for call quality scoring and monitoring.
Add these models to your calls/models.py file.
"""

from django.db import models
from django.conf import settings


class CallQualityScore(models.Model):
    """
    Detailed quality scoring for calls
    
    Phase 4.2: Stores individual score components and review status
    """
    call = models.OneToOneField(
        'CallLog',
        on_delete=models.CASCADE,
        related_name='quality_details'
    )
    
    # Individual scores (0-100)
    duration_score = models.FloatField(
        default=0,
        help_text="Score based on call duration"
    )
    hold_score = models.FloatField(
        default=0,
        help_text="Score based on hold time"
    )
    disposition_score = models.FloatField(
        default=0,
        help_text="Score based on disposition outcome"
    )
    resolution_score = models.FloatField(
        default=0,
        help_text="Score based on first call resolution"
    )
    
    # Total calculated score
    total_score = models.FloatField(
        default=0,
        help_text="Weighted average of all scores"
    )
    
    # Score category
    CATEGORY_CHOICES = [
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('average', 'Average'),
        ('poor', 'Poor'),
        ('critical', 'Critical'),
    ]
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='average'
    )
    
    # Flagging for review
    flagged_for_review = models.BooleanField(
        default=False,
        help_text="Call flagged for supervisor review"
    )
    flag_reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reason for flagging"
    )
    
    # Supervisor review fields
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_calls'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(
        blank=True,
        help_text="Supervisor notes from review"
    )
    review_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Manual score override by supervisor"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Call Quality Score'
        verbose_name_plural = 'Call Quality Scores'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Quality Score for Call #{self.call_id}: {self.total_score}"
    
    def get_final_score(self):
        """Return review score if available, otherwise total score"""
        if self.review_score is not None:
            return self.review_score
        return self.total_score


class SupervisorMonitorLog(models.Model):
    """
    Log of supervisor monitoring sessions
    
    Phase 4.2: Tracks when supervisors listen/whisper/barge on calls
    """
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='monitoring_sessions'
    )
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='monitored_sessions'
    )
    call = models.ForeignKey(
        'CallLog',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='monitor_logs'
    )
    
    # Monitoring mode
    MODE_CHOICES = [
        ('listen', 'Listen Only'),
        ('whisper', 'Whisper'),
        ('barge', 'Barge'),
        ('coach', 'Coach'),
    ]
    mode = models.CharField(
        max_length=20,
        choices=MODE_CHOICES
    )
    
    # Session timing
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    duration = models.IntegerField(
        null=True,
        blank=True,
        help_text="Duration in seconds"
    )
    
    # Notes
    notes = models.TextField(
        blank=True,
        help_text="Supervisor notes from monitoring session"
    )
    
    class Meta:
        verbose_name = 'Monitor Log'
        verbose_name_plural = 'Monitor Logs'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.supervisor.username} monitored {self.agent.username} ({self.mode})"
    
    def save(self, *args, **kwargs):
        # Calculate duration if ended
        if self.ended_at and self.started_at:
            self.duration = int((self.ended_at - self.started_at).total_seconds())
        super().save(*args, **kwargs)


# ============================================================================
# CallLog Model Extensions
# ============================================================================

"""
Add these fields to your existing CallLog model in calls/models.py:

class CallLog(models.Model):
    # ... existing fields ...
    
    # Phase 4.1: AMD fields
    amd_result = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=[
            ('human', 'Human'),
            ('machine', 'Machine'),
            ('unsure', 'Unsure'),
            ('fax', 'Fax'),
            ('sit', 'SIT Tone'),
            ('hangup', 'Hangup'),
        ],
        help_text="AMD detection result"
    )
    amd_action = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Action taken based on AMD"
    )
    
    # Phase 4.2: Quality fields
    quality_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Automated quality score (0-100)"
    )
    hold_duration = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total hold time in seconds"
    )
    ring_duration = models.IntegerField(
        null=True,
        blank=True,
        help_text="Ring time before answer (seconds)"
    )
    
    # Channel tracking for monitoring
    agent_channel = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Asterisk channel ID for agent leg"
    )

Then run:
    python manage.py makemigrations calls
    python manage.py migrate
"""
