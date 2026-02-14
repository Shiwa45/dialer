# users/tasks.py
# Celery tasks for agent monitoring

from celery import shared_task
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


@shared_task(name='users.cleanup_zombie_agents')
def cleanup_zombie_agents_task():
    """
    Celery task: find agents with stale heartbeats and mark them offline.
    Schedule every 3 minutes in CELERY_BEAT_SCHEDULE.
    """
    from users.views import cleanup_zombie_agents
    count = cleanup_zombie_agents(timeout_minutes=5)
    if count:
        logger.info(f"Zombie cleanup: marked {count} agent(s) offline")
    return {'cleaned': count}


@shared_task(name='users.close_open_timelogs')
def close_open_timelogs_task():
    """
    Celery task: close any time logs that are still open for offline agents.
    Runs every 10 minutes as safety net.
    """
    from users.models import AgentTimeLog, AgentStatus

    now = timezone.now()
    # Find open time logs for offline agents
    offline_agent_ids = AgentStatus.objects.filter(
        status='offline'
    ).values_list('user_id', flat=True)

    open_logs = AgentTimeLog.objects.filter(
        ended_at__isnull=True,
        user_id__in=offline_agent_ids,
    )
    count = 0
    for log in open_logs:
        log.ended_at = now
        log.duration_seconds = max(0, int((now - log.started_at).total_seconds()))
        log.save(update_fields=['ended_at', 'duration_seconds'])
        count += 1

    if count:
        logger.info(f"Closed {count} stale time log(s)")
    return {'closed': count}
