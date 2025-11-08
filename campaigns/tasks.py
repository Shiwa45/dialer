from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from campaigns.models import OutboundQueue, Campaign
from agents.models import AgentDialerSession
from users.models import AgentStatus
from telephony.models import Phone
from telephony.services import AsteriskService


@shared_task(name='campaigns.process_outbound_queue')
def process_outbound_queue_task(campaign_id=None, batch_size=20):
    qs = OutboundQueue.objects.filter(status='pending')
    if campaign_id:
        qs = qs.filter(campaign_id=campaign_id)
    # Prefer batching per-campaign based on dial speed presets
    campaigns = Campaign.objects.filter(id__in=qs.values_list('campaign_id', flat=True).distinct())
    total = 0
    for camp in campaigns:
        idle_agents = AgentStatus.objects.filter(status='available', user__assigned_campaigns=camp).count()
        dpa = compute_dials_per_agent(camp)
        capacity = max(1, idle_agents * dpa)
        items = qs.filter(campaign=camp).order_by('created_at')[: min(capacity, batch_size)]
        for item in items:
            process_outbound_queue_item.delay(item.id)
            total += 1
    return total


def compute_dials_per_agent(campaign: Campaign) -> int:
    preset = campaign.dial_speed
    if preset == 'slow':
        return 1
    if preset == 'normal':
        return 2
    if preset == 'fast':
        return 3
    if preset == 'very_fast':
        return 4
    # custom
    return max(1, campaign.custom_dials_per_agent or 1)


@shared_task(name='campaigns.process_outbound_queue_item')
def process_outbound_queue_item(item_id):
    item = OutboundQueue.objects.filter(id=item_id, status='pending').select_related('campaign').first()
    if not item:
        return False
    campaign = item.campaign
    # Pick an available agent assigned to this campaign
    agent_status = AgentStatus.objects.filter(status='available', user__assigned_campaigns=campaign).select_related('user').first()
    if not agent_status:
        return False
    agent = agent_status.user
    phone = Phone.objects.filter(user=agent, is_active=True).first()
    if not phone:
        return False
    service = AsteriskService(phone.asterisk_server)
    # Build customer number with dial prefix and use dialplan routing via Local/
    number_to_dial = f"{campaign.dial_prefix}{item.phone_number}" if campaign.dial_prefix else item.phone_number
    # 1) Originate customer leg via Local/ into from-campaign context so dialplan selects GSM gateway/trunk
    cres = service.originate_local_channel(
        number=number_to_dial,
        context='from-campaign',
        app='autodialer',
        callerid=f"OUT {item.phone_number}",
        variables={'CALL_TYPE': 'customer_leg'}
    )
    if not cres.get('success'):
        item.status = 'failed'
        item.attempts += 1
        item.last_tried_at = timezone.now()
        item.save()
        return False
    cust_chan = cres['channel_id']
    item.status = 'dialing'
    item.attempts += 1
    item.last_tried_at = timezone.now()
    item.save()
    # Wait for customer to answer
    if not service.wait_for_channel_up(cust_chan, timeout_sec=45).get('success'):
        service.hangup_channel(cust_chan)
        item.status = 'failed'
        item.save()
        return False
    # 2) Originate agent leg
    ares = service.originate_pjsip_channel(
        endpoint=phone.extension,
        app='autodialer',
        callerid=f"Agent {phone.extension}",
        variables={'CALL_TYPE': 'agent_leg'}
    )
    if not ares.get('success'):
        service.hangup_channel(cust_chan)
        return False
    agent_chan = ares['channel_id']
    if not service.wait_for_channel_up(agent_chan, timeout_sec=30).get('success'):
        service.hangup_channel(agent_chan)
        service.hangup_channel(cust_chan)
        return False
    # 3) Bridge both legs
    b = service.create_bridge('mixing')
    if not b.get('success'):
        service.hangup_channel(agent_chan)
        service.hangup_channel(cust_chan)
        return False
    bridge_id = b['bridge_id']
    service.add_channel_to_bridge(bridge_id, cust_chan)
    service.add_channel_to_bridge(bridge_id, agent_chan)
    # Success; leave tear-down to natural hangup
    item.status = 'answered'
    item.save()
    return True
