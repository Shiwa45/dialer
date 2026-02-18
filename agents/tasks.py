from celery import shared_task
from agents.stats_broadcaster import broadcast_stats_refresh
from django.contrib.auth.models import User

@shared_task
def refresh_all_agent_stats():
    """
    Periodic task (e.g. every 30s) to refresh dashboard stats 
    for all active agents.
    """
    # Only refresh for agents who are logged in / have a status
    # You might adjust this filter based on your exact AgentStatus model usage
    # For now, let's refresh for anyone with an active AgentStatus
    active_user_ids = User.objects.filter(
        agent_status__isnull=False
    ).values_list('id', flat=True)

    for uid in active_user_ids:
        broadcast_stats_refresh(uid)
