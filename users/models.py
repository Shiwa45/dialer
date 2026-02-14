# users/models.py
# UPDATED: Adds AgentTimeLog for time monitoring + heartbeat/wrapup fields on AgentStatus

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from core.models import TimeStampedModel
import logging

logger = logging.getLogger(__name__)


class UserProfile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=20, blank=True)
    extension = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    bio = models.TextField(blank=True)
    department = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(max_length=50, default='UTC')
    is_online = models.BooleanField(default=False)
    last_activity = models.DateTimeField(auto_now=True)
    total_calls_made = models.IntegerField(default=0)
    total_calls_answered = models.IntegerField(default=0)

    # Restored fields from previous version to satisfy forms.py
    employee_id = models.CharField(max_length=20, blank=True)
    agent_id = models.CharField(max_length=20, blank=True)
    is_active_agent = models.BooleanField(default=False)
    skill_level = models.CharField(max_length=50, default='1')
    can_make_outbound = models.BooleanField(default=True)
    can_receive_inbound = models.BooleanField(default=True)
    can_transfer_calls = models.BooleanField(default=True)
    can_conference_calls = models.BooleanField(default=True)
    shift_start = models.TimeField(null=True, blank=True)
    shift_end = models.TimeField(null=True, blank=True)
    theme_preference = models.CharField(max_length=20, default='light')

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
        ordering = ['user__username']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_role()}"

    def get_role(self):
        groups = self.user.groups.all()
        if groups:
            return groups.first().name
        return "No Role"

    def get_full_name(self):
        return self.user.get_full_name() or self.user.username

    def is_manager(self):
        return self.user.groups.filter(name='Manager').exists() or self.user.is_superuser

    def is_supervisor(self):
        return self.user.groups.filter(name__in=['Supervisor', 'Manager']).exists() or self.user.is_superuser

    def is_agent(self):
        return self.user.groups.filter(name__in=['Agent', 'Supervisor', 'Manager']).exists() or self.user.is_superuser


class UserSession(TimeStampedModel):
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
        end_time = self.logout_time or timezone.now()
        return end_time - self.login_time


class AgentStatus(TimeStampedModel):
    """
    Track real-time agent status.
    UPDATED: Adds heartbeat (zombie detection), wrapup_started_at, wrapup_call_id.
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
        null=True, blank=True,
        related_name='active_agents'
    )

    # Current call information
    current_call_id = models.CharField(max_length=50, blank=True)
    call_start_time = models.DateTimeField(null=True, blank=True)

    # ── NEW: Heartbeat for zombie session detection ──────────────────
    last_heartbeat = models.DateTimeField(
        null=True, blank=True,
        help_text='Last ping from agent browser - used for zombie detection'
    )

    # ── NEW: Wrapup state persistence ────────────────────────────────
    wrapup_started_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When agent entered wrapup status'
    )
    wrapup_call_id = models.CharField(
        max_length=50, blank=True, default='',
        help_text='Call ID pending disposition in wrapup'
    )

    class Meta:
        verbose_name = "Agent Status"
        verbose_name_plural = "Agent Statuses"

    def __str__(self):
        return f"{self.user.username} - {self.get_status_display()}"

    def is_available(self):
        return self.status == 'available'

    def needs_disposition(self):
        """Returns True if agent is in wrapup and has a call pending disposition."""
        return self.status == 'wrapup' and bool(self.wrapup_call_id or self.current_call_id)

    def set_status(self, new_status, reason='', call_id=None):
        """
        Set agent status, handle time log transitions, and manage wrapup state.
        """
        old_status = self.status
        now = timezone.now()

        # Close the previous time log entry
        self._close_time_log(ended_at=now)

        # Handle wrapup state
        if new_status == 'wrapup':
            self.wrapup_started_at = now
            if call_id:
                self.wrapup_call_id = str(call_id)
            elif self.current_call_id:
                self.wrapup_call_id = self.current_call_id
        elif old_status == 'wrapup' and new_status != 'wrapup':
            # Leaving wrapup - clear wrapup fields
            self.wrapup_started_at = None
            self.wrapup_call_id = ''

        self.status = new_status
        self.break_reason = reason if new_status in ('break', 'lunch', 'meeting', 'training') else ''
        self.save()

        # Open a new time log entry for new status
        self._open_time_log(status=new_status, started_at=now)

        # Broadcast via WebSocket
        self._broadcast_status_change(new_status)

        logger.info(f"Agent {self.user.username}: {old_status} → {new_status}")

    def _open_time_log(self, status, started_at):
        """Create an open-ended AgentTimeLog entry for the new status."""
        try:
            AgentTimeLog.objects.create(
                user=self.user,
                status=status,
                started_at=started_at,
                ended_at=None,
                duration_seconds=0,
                date=started_at.date(),
                campaign=self.current_campaign,
            )
        except Exception as e:
            logger.warning(f"Could not create time log: {e}")

    def _close_time_log(self, ended_at):
        """Close the most recent open time log entry."""
        try:
            open_log = AgentTimeLog.objects.filter(
                user=self.user,
                ended_at__isnull=True,
            ).order_by('-started_at').first()
            if open_log:
                open_log.ended_at = ended_at
                open_log.duration_seconds = max(
                    0, int((ended_at - open_log.started_at).total_seconds())
                )
                open_log.save(update_fields=['ended_at', 'duration_seconds'])
        except Exception as e:
            logger.warning(f"Could not close time log: {e}")

    def update_heartbeat(self):
        """Update the heartbeat timestamp (called from heartbeat API)."""
        self.last_heartbeat = timezone.now()
        self.save(update_fields=['last_heartbeat'])

    def is_zombie(self, timeout_minutes=5):
        """Returns True if agent hasn't sent a heartbeat within timeout_minutes."""
        if self.status == 'offline':
            return False
        if self.last_heartbeat is None:
            # Grace period: 10 min after status_changed_at
            cutoff = timezone.now() - timezone.timedelta(minutes=10)
            return self.status_changed_at < cutoff
        cutoff = timezone.now() - timezone.timedelta(minutes=timeout_minutes)
        return self.last_heartbeat < cutoff

    def _broadcast_status_change(self, new_status):
        """Broadcast status update to WebSocket group."""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"agent_{self.user.id}",
                    {
                        'type': 'call_event',
                        'data': {
                            'type': 'status_changed',
                            'status': new_status,
                            'display': self.get_status_display(),
                        }
                    }
                )
        except Exception as e:
            logger.debug(f"WS broadcast skipped: {e}")


class AgentTimeLog(models.Model):
    """
    Records every agent status interval for time monitoring / reporting.
    Admin can query: total call time, idle time, wrapup time, break time per agent per day.
    """
    STATUS_CHOICES = [
        ('offline', 'Offline'),
        ('available', 'Available'),
        ('busy', 'Busy/On Call'),
        ('wrapup', 'Wrap-up'),
        ('break', 'Break'),
        ('lunch', 'Lunch'),
        ('training', 'Training'),
        ('meeting', 'Meeting'),
        ('system_issues', 'System Issues'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='time_logs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, db_index=True)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    date = models.DateField(db_index=True)
    notes = models.CharField(max_length=200, blank=True, default='')

    call_log = models.ForeignKey(
        'calls.CallLog',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='time_logs'
    )
    campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='agent_time_logs'
    )

    class Meta:
        verbose_name = "Agent Time Log"
        verbose_name_plural = "Agent Time Logs"
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', 'date'], name='users_timelog_user_date_idx'),
            models.Index(fields=['user', 'status', 'date'], name='users_timelog_usr_stat_dt_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} [{self.status}] {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def duration_formatted(self):
        secs = self.duration_seconds
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        if h:
            return f"{h}h {m:02d}m {s:02d}s"
        return f"{m:02d}m {s:02d}s"

    @classmethod
    def get_daily_summary(cls, user, date):
        """Returns dict of {status: total_seconds} for an agent on a given date."""
        from django.db.models import Sum
        rows = (
            cls.objects
            .filter(user=user, date=date)
            .values('status')
            .annotate(total=Sum('duration_seconds'))
        )
        return {r['status']: r['total'] for r in rows}
