from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from campaigns.models import OutboundQueue, Campaign
from agents.models import AgentDialerSession
from users.models import AgentStatus
from telephony.models import Phone
from telephony.services import AsteriskService
from telephony.routing import build_call_variables, build_dial_number, select_carrier_for_campaign
from django.utils import timezone
import json

try:
    import redis
except ImportError:
    redis = None

HOPPER_SIZE = 500  # default if campaign-specific value not set


def get_redis():
    """
    Return redis client or None if unavailable.
    """
    if not redis:
        return None
    try:
        return redis.Redis(host='127.0.0.1', port=6379, db=0)
    except Exception:
        return None


def hopper_key(campaign_id):
    return f"hopper:{campaign_id}"


@shared_task(name='campaigns.process_outbound_queue')
def process_outbound_queue_task(campaign_id=None, batch_size=20):
    # Recycle eligible items before selecting new ones
    try:
        recycle_queue_items()
    except Exception:
        pass
    try:
        reset_stuck_wrapup()
    except Exception:
        pass
    try:
        reset_stuck_busy()
    except Exception:
        pass
    qs = OutboundQueue.objects.filter(status='pending')
    if campaign_id:
        qs = qs.filter(campaign_id=campaign_id)
    # Prefer batching per-campaign based on dial speed presets
    campaigns = Campaign.objects.filter(id__in=qs.values_list('campaign_id', flat=True).distinct())
    total = 0
    for camp in campaigns:
        # Fill hopper from DB into Redis
        try:
            fill_hopper(camp)
        except Exception:
            pass
        idle_agents = AgentStatus.objects.filter(status='available', user__assigned_campaigns=camp).count()
        if idle_agents == 0:
            # No available agents; skip this campaign for now
            continue
        dpa = compute_dials_per_agent(camp)
        capacity = idle_agents * dpa
        if capacity < 1:
            continue
        assigned = 0
        for _ in range(min(capacity, batch_size)):
            # If no available agents now, stop
            agent_status = AgentStatus.objects.filter(status='available', user__assigned_campaigns=camp).select_related('user').first()
            if not agent_status:
                break
            item_id = pop_hopper_item(camp)
            if not item_id:
                break
            # Double-check the queue row is still pending before dialing
            if not OutboundQueue.objects.filter(id=item_id, status='pending').exists():
                continue
            # Try to reserve the agent atomically
            reserved = AgentStatus.objects.filter(pk=agent_status.pk, status='available').update(
                status='busy',
                current_call_id=str(item_id),
                call_start_time=timezone.now(),
                status_changed_at=timezone.now(),
                current_campaign=camp,
            )
            if not reserved:
                # Agent was grabbed by another task, push item back and stop this iteration
                push_hopper_item(camp, item_id)
                continue
            process_outbound_queue_item.delay(item_id, agent_status.user_id)
            assigned += 1
        total += assigned
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


def recycle_queue_items():
    """
    Simple recycler: mark completed/failed items back to pending based on disposition rules.
    Only recycle items that have a disposition code configured to recycle and were last tried > 5 minutes ago.
    """
    from django.utils import timezone
    cutoff = timezone.now() - timezone.timedelta(minutes=5)
    # Example: recycle only specific dispositions; adjust as needed
    recycle_codes = ['no_answer', 'busy']
    recycled = 0
    qs = OutboundQueue.objects.filter(
        status='completed',
        disposition__in=recycle_codes,
        last_tried_at__lte=cutoff,
    )[:500]
    recycled = qs.update(status='pending', attempts=models.F('attempts') + 1, last_tried_at=timezone.now())
    return recycled


def reset_stuck_wrapup():
    """
    Agents left in wrapup past campaign timeout are reset to available.
    Uses campaign.wrapup_timeout when current_campaign is set; otherwise 5 minutes.
    """
    now = timezone.now()
    # Default fallback 5 minutes
    default_cutoff = now - timezone.timedelta(minutes=5)
    # Agents without current_campaign
    AgentStatus.objects.filter(
        status='wrapup',
        current_campaign__isnull=True,
        status_changed_at__lte=default_cutoff
    ).update(
        status='available',
        current_call_id='',
        call_start_time=None,
        status_changed_at=now
    )
    # With campaign-specific timeout
    for camp in Campaign.objects.all():
        cutoff = now - timezone.timedelta(seconds=camp.wrapup_timeout or 300)
        AgentStatus.objects.filter(
            status='wrapup',
            current_campaign=camp,
            status_changed_at__lte=cutoff
        ).update(
            status='available',
            current_call_id='',
            call_start_time=None,
            status_changed_at=now
        )


def reset_stuck_busy(max_minutes=10):
    """
    Agents stuck in busy without an active call are reset to available after timeout.
    """
    now = timezone.now()
    cutoff = now - timezone.timedelta(minutes=max_minutes)
    AgentStatus.objects.filter(
        status='busy',
        current_call_id='',
        status_changed_at__lte=cutoff
    ).update(
        status='available',
        status_changed_at=now
    )


def fill_hopper(campaign: Campaign):
    """
    Ensure Redis hopper has items for this campaign.
    """
    r = get_redis()
    if not r:
        return 0
    key = hopper_key(campaign.id)
    target_size = getattr(campaign, 'hopper_size', HOPPER_SIZE) or HOPPER_SIZE
    try:
        current = r.llen(key)
        if current >= target_size:
            return 0
        needed = target_size - current
        ids = list(
            OutboundQueue.objects.filter(campaign=campaign, status='pending')
            .order_by('created_at')
            .values_list('id', flat=True)[:needed]
        )
        if ids:
            r.rpush(key, *ids)
        return len(ids)
    except Exception:
        return 0


def pop_hopper_item(campaign: Campaign):
    r = get_redis()
    if not r:
        return None
    try:
        val = r.lpop(hopper_key(campaign.id))
        if val is None:
            return None
        try:
            return int(val)
        except Exception:
            return None
    except Exception:
        return None


def push_hopper_item(campaign: Campaign, item_id: int):
    r = get_redis()
    if not r:
        return
    try:
        r.lpush(hopper_key(campaign.id), item_id)
    except Exception:
        return


@shared_task(name='campaigns.process_outbound_queue_item')
def process_outbound_queue_item(item_id, agent_id):
    item = OutboundQueue.objects.filter(id=item_id, status='pending').select_related('campaign').first()
    if not item:
        return False
    campaign = item.campaign
    agent_status = AgentStatus.objects.filter(user_id=agent_id).select_related('user').first()
    if not agent_status:
        return False
    agent = agent_status.user
    # Ensure agent is marked busy for this call
    AgentStatus.objects.filter(pk=agent_status.pk).update(
        status='busy',
        current_call_id=str(item.id),
        call_start_time=timezone.now(),
        status_changed_at=timezone.now(),
        current_campaign=campaign,
    )
    phone = Phone.objects.filter(user=agent, is_active=True).first()
    if not phone:
        AgentStatus.objects.filter(user=agent).update(status='available', current_call_id='', call_start_time=None, current_campaign=None)
        return False
    carrier = select_carrier_for_campaign(campaign)
    target_server = carrier.asterisk_server if carrier else phone.asterisk_server
    service = AsteriskService(target_server)
    # Build customer number with prefixes and use dialplan routing via Local/
    number_to_dial = build_dial_number(item.phone_number, campaign=campaign, carrier=carrier)
    # 1) Originate customer leg via Local/ into from-campaign context so dialplan selects GSM gateway/trunk
    customer_vars = build_call_variables(
        call_type='customer_leg',
        campaign=campaign,
        queue_item=item,
        agent=agent,
        carrier=carrier,
    )
    cres = service.originate_local_channel(
        number=number_to_dial,
        context='from-campaign',
        app='autodialer',
        callerid=f"OUT {item.phone_number}",
        variables=customer_vars,
    )
    if not cres.get('success'):
        item.status = 'failed'
        item.attempts += 1
        item.last_tried_at = timezone.now()
        item.save()
        AgentStatus.objects.filter(user=agent).update(status='available', current_call_id='', call_start_time=None, current_campaign=None)
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
        AgentStatus.objects.filter(user=agent).update(status='available', current_call_id='', call_start_time=None, current_campaign=None)
        return False
    # 2) Originate agent leg
    agent_vars = build_call_variables(
        call_type='agent_leg',
        campaign=campaign,
        queue_item=item,
        agent=agent,
        carrier=carrier,
    )
    ares = service.originate_pjsip_channel(
        endpoint=phone.extension,
        app='autodialer',
        callerid=f"Agent {phone.extension}",
        variables=agent_vars,
    )
    if not ares.get('success'):
        service.hangup_channel(cust_chan)
        AgentStatus.objects.filter(user=agent).update(status='available', current_call_id='', call_start_time=None, current_campaign=None)
        return False
    agent_chan = ares['channel_id']
    if not service.wait_for_channel_up(agent_chan, timeout_sec=30).get('success'):
        service.hangup_channel(agent_chan)
        service.hangup_channel(cust_chan)
        AgentStatus.objects.filter(user=agent).update(status='available', current_call_id='', call_start_time=None, current_campaign=None)
        return False
    # 3) Bridge both legs
    b = service.create_bridge('mixing')
    if not b.get('success'):
        service.hangup_channel(agent_chan)
        service.hangup_channel(cust_chan)
        AgentStatus.objects.filter(user=agent).update(status='available', current_call_id='', call_start_time=None)
        return False
    bridge_id = b['bridge_id']
    service.add_channel_to_bridge(bridge_id, cust_chan)
    service.add_channel_to_bridge(bridge_id, agent_chan)
    # Persist bridge/channel info for hangup control
    AgentDialerSession.objects.update_or_create(
        agent=agent,
        campaign=campaign,
        defaults={
            'agent_channel_id': agent_chan,
            'agent_bridge_id': bridge_id,
            'asterisk_server': target_server,
            'status': 'ready',
        },
    )
    # Success; leave tear-down to natural hangup
    item.status = 'answered'
    item.save()
    return True
