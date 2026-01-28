from django.db.models import Count, Q
from django.utils import timezone

from campaigns.models import Campaign, OutboundQueue
from calls.models import CallLog
from agents.models import AgentDialerSession
from users.models import AgentStatus


def build_monitor_payload():
    sessions = AgentDialerSession.objects.filter(
        status__in=['ready', 'incall']
    ).select_related('agent', 'campaign').order_by('-last_state_change')
    agents = AgentStatus.objects.select_related('user', 'current_campaign')
    agent_data = []
    seen_agent_ids = set()
    for session in sessions:
        agent = session.agent
        if agent.id in seen_agent_ids:
            continue
        seen_agent_ids.add(agent.id)
        agent_status = agents.filter(user_id=agent.id).first()
        status_changed_at = (
            agent_status.status_changed_at if agent_status and agent_status.status_changed_at
            else session.last_state_change
        )
        campaign_name = '-'
        if agent_status and agent_status.current_campaign:
            campaign_name = agent_status.current_campaign.name
        elif session.campaign:
            campaign_name = session.campaign.name
        agent_data.append({
            'id': agent.id,
            'name': agent.username,
            'status': agent_status.status if agent_status else 'available',
            'campaign': campaign_name,
            'call_id': agent_status.current_call_id if agent_status else '',
            'duration': int((timezone.now() - status_changed_at).total_seconds()) if status_changed_at else 0,
        })

    campaigns = Campaign.objects.filter(status='active')
    queue_data = []
    for c in campaigns:
        q_stats = OutboundQueue.objects.filter(campaign=c).aggregate(
            pending=Count('id', filter=Q(status='new')),
            dialing=Count('id', filter=Q(status='dialing')),
            connected=Count('id', filter=Q(status='answered')),
        )
        queue_data.append({
            'id': c.id,
            'name': c.name,
            'pending': q_stats['pending'],
            'dialing': q_stats['dialing'],
            'connected': q_stats['connected'],
        })

    today = timezone.now().date()
    daily_stats = CallLog.objects.filter(start_time__date=today).aggregate(
        total=Count('id'),
        answered=Count('id', filter=Q(call_status='answered')),
        sales=Count('id', filter=Q(disposition__is_sale=True))
    )

    return {
        'agents': agent_data,
        'queues': queue_data,
        'stats': {
            'total_calls': daily_stats['total'],
            'answered': daily_stats['answered'],
            'sales': daily_stats['sales'],
            'active_agents': len(agent_data),
        },
    }
