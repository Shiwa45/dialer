# reports/realtime_views.py
# UPDATED: Adds status_changed_at_ms (Unix ms) for accurate frontend timers,
#          login_time_secs / login_at_ms for per-agent login tracking,
#          and detailed time_breakdown for the admin report page.

import json
import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from core.decorators import supervisor_required

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(secs):
    """Format seconds → HH:MM:SS."""
    secs = int(secs or 0)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _to_ms(dt):
    """Convert aware datetime → Unix milliseconds (int), or None."""
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


def _batch_status_start(agent_ids, today):
    """
    Return {user_id: started_at_datetime} for the most recent OPEN
    AgentTimeLog per agent today.

    KEY: started_at is written ONCE when status changes and is NEVER modified,
    unlike status_changed_at (auto_now=True) which resets on every .save()
    including heartbeats, call-ID updates, etc.

    This is the only reliable source of truth for "when did status start".
    """
    from users.models import AgentTimeLog
    if not agent_ids:
        return {}
    rows = (
        AgentTimeLog.objects
        .filter(user_id__in=agent_ids, date=today, ended_at__isnull=True)
        .order_by('user_id', '-started_at')
        .values('user_id', 'started_at')
    )
    result = {}
    for row in rows:
        uid = row['user_id']
        if uid not in result:          # first = latest (ordered -started_at)
            result[uid] = row['started_at']
    return result


def _login_info_for_agents(agent_ids, today):
    """
    BATCHED: Return {user_id: {login_at_ms, total_logged_in_secs}} for all
    agents using 2 queries total (closed + open logs), not N per-agent queries.
    """
    from users.models import AgentTimeLog

    now = timezone.now()
    if not agent_ids:
        return {}

    result = {uid: {'login_at_ms': None, 'total_logged_in_secs': 0}
              for uid in agent_ids}

    # Closed logs
    closed = (
        AgentTimeLog.objects
        .filter(user_id__in=agent_ids, date=today, ended_at__isnull=False)
        .exclude(status='offline')
        .order_by('user_id', 'started_at')
        .values('user_id', 'started_at', 'duration_seconds')
    )
    for row in closed:
        uid = row['user_id']
        if result[uid]['login_at_ms'] is None:
            result[uid]['login_at_ms'] = _to_ms(row['started_at'])
        result[uid]['total_logged_in_secs'] += int(row['duration_seconds'] or 0)

    # Open log — count elapsed time up to now
    open_logs = (
        AgentTimeLog.objects
        .filter(user_id__in=agent_ids, date=today, ended_at__isnull=True)
        .exclude(status='offline')
        .order_by('user_id', 'started_at')
        .values('user_id', 'started_at')
    )
    for row in open_logs:
        uid = row['user_id']
        if result[uid]['login_at_ms'] is None:
            result[uid]['login_at_ms'] = _to_ms(row['started_at'])
        result[uid]['total_logged_in_secs'] += max(
            0, int((now - row['started_at']).total_seconds())
        )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@supervisor_required
def realtime_dashboard(request):
    """Render the real-time monitoring dashboard."""
    from campaigns.models import Campaign

    campaigns = Campaign.objects.filter(status='active').order_by('name')
    context = {
        'campaigns': campaigns,
        'page_title': 'Real-time Monitor',
    }
    return render(request, 'reports/realtime_dashboard.html', context)


@login_required
@supervisor_required
def realtime_agents_api(request):
    """
    Return live agent data for the realtime monitor.

    Key fields added vs old version:
      status_changed_at_ms  — Unix ms timestamp when current status started.
                              Frontend uses this to seed timers: elapsed = now - status_changed_at_ms
      login_at_ms           — Unix ms of first login today (for login timer)
      login_time_secs       — Total seconds logged in today
      time_breakdown        — Dict of {status: seconds} today for the tooltip
    """
    from users.models import AgentStatus
    from calls.models import CallLog
    from campaigns.models import CampaignAgent

    try:
        campaign_id = request.GET.get('campaign_id')
        now         = timezone.now()
        today       = now.date()

        agents_query = AgentStatus.objects.select_related(
            'user', 'current_campaign'
        ).exclude(status='offline')

        if campaign_id and campaign_id != 'all':
            try:
                cid = int(campaign_id)
                agent_ids = CampaignAgent.objects.filter(
                    campaign_id=cid, is_active=True
                ).values_list('user_id', flat=True)
                agents_query = agents_query.filter(user_id__in=agent_ids)
            except (ValueError, TypeError):
                pass

        agents_list = list(agents_query)
        agent_ids   = [a.user_id for a in agents_list]

        # Batch DB lookups — no per-agent loops
        status_start_map = _batch_status_start(agent_ids, today)  # RELIABLE timing
        login_info       = _login_info_for_agents(agent_ids, today)

        # Batch breakdown (closed logs only — open added per-agent below)
        from users.models import AgentTimeLog
        breakdown_qs = (
            AgentTimeLog.objects
            .filter(user_id__in=agent_ids, date=today, ended_at__isnull=False)
            .values('user_id', 'status')
            .annotate(total=Sum('duration_seconds'))
        )
        breakdown_map = {}
        for row in breakdown_qs:
            uid = row['user_id']
            if uid not in breakdown_map:
                breakdown_map[uid] = {}
            breakdown_map[uid][row['status']] = int(row['total'] or 0)

        agents_data = []
        for agent in agents_list:
            uid = agent.user_id

            # ── RELIABLE timing: AgentTimeLog.started_at (open log) ────────
            # status_changed_at has auto_now=True — resets on EVERY .save()
            # (heartbeats, call-ID writes, etc.) → wrong timer value.
            # AgentTimeLog.started_at is written once, never changed.
            open_started = status_start_map.get(uid)
            if open_started:
                status_changed_at_ms = _to_ms(open_started)
                status_time_secs     = max(0, int((now - open_started).total_seconds()))
            elif agent.status_changed_at:
                # Fallback only if no open log exists
                status_changed_at_ms = _to_ms(agent.status_changed_at)
                status_time_secs     = max(0, int((now - agent.status_changed_at).total_seconds()))
            else:
                status_changed_at_ms = None
                status_time_secs     = 0

            li = login_info.get(uid, {})

            # ── Talk time ──────────────────────────────────────────────────
            call_start_ms = None
            talk_time_secs = 0
            if agent.status == 'busy' and hasattr(agent, 'call_start_time') and agent.call_start_time:
                call_start_ms  = _to_ms(agent.call_start_time)
                talk_time_secs = int((now - agent.call_start_time).total_seconds())

            # ── Current call info ──────────────────────────────────────────
            current_call = None
            cid_str = agent.current_call_id or agent.wrapup_call_id
            if cid_str:
                try:
                    call = CallLog.objects.filter(id=int(cid_str)).first()
                    if call:
                        lead_name = None
                        if call.lead:
                            lead_name = (
                                f"{call.lead.first_name or ''} {call.lead.last_name or ''}".strip()
                                or call.lead.phone_number
                            )
                        current_call = {
                            'id'       : call.id,
                            'number'   : call.called_number,
                            'lead_name': lead_name,
                            'duration' : talk_time_secs,
                        }
                except Exception:
                    pass

            # ── Zombie detection ───────────────────────────────────────────
            is_zombie = False
            if hasattr(agent, 'is_zombie'):
                is_zombie = agent.is_zombie(timeout_minutes=5)

            agents_data.append({
                # Identity
                'id'       : uid,
                'username' : agent.user.username,
                'name'     : agent.user.get_full_name() or agent.user.username,

                # Status
                'status'        : agent.status,
                'status_display': agent.get_status_display(),

                # ── KEY FIX: use these in the frontend to seed timers ──────
                'status_changed_at_ms' : status_changed_at_ms,   # Unix ms
                'status_time_secs'     : status_time_secs,        # pre-calculated
                'status_time_formatted': _fmt(status_time_secs),  # HH:MM:SS

                # Login
                'login_at_ms'          : li.get('login_at_ms'),   # Unix ms
                'login_time_secs'      : li.get('total_logged_in_secs', 0),
                'login_time_formatted' : _fmt(li.get('total_logged_in_secs', 0)),

                # Campaign
                'campaign'   : agent.current_campaign.name if agent.current_campaign else None,
                'campaign_id': agent.current_campaign.id   if agent.current_campaign else None,

                # Call
                'current_call'  : current_call,
                'call_start_ms' : call_start_ms,

                # Today's breakdown (for tooltip / report)
                'time_breakdown': breakdown_map.get(uid, {}),

                # Extension
                'extension': getattr(
                    getattr(agent.user, 'userprofile', None), 'extension', None
                ) or getattr(
                    getattr(agent.user, 'phone', None), 'extension', None
                ),

                # Health
                'is_zombie'        : is_zombie,
                'last_heartbeat_ms': _to_ms(
                    getattr(agent, 'last_heartbeat', None)
                ),
                'needs_disposition': (
                    agent.needs_disposition()
                    if hasattr(agent, 'needs_disposition') else False
                ),
            })

        # Sort: busy → available → wrapup → others
        order = {'busy': 0, 'available': 1, 'wrapup': 2, 'break': 3, 'lunch': 4}
        agents_data.sort(key=lambda x: (order.get(x['status'], 9), x['name']))

        # Server timestamp so frontend can compute clock skew
        return JsonResponse({
            'success'       : True,
            'agents'        : agents_data,
            'server_time_ms': int(now.timestamp() * 1000),
            'timestamp'     : now.isoformat(),
        })

    except Exception as e:
        logger.exception('Error in realtime_agents_api')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@supervisor_required
def realtime_campaign_stats_api(request):
    """Campaign statistics — unchanged from original, kept for compatibility."""
    from calls.models import CallLog
    from campaigns.models import Campaign

    try:
        today = timezone.now().date()
        now   = timezone.now()
        campaign_id = request.GET.get('campaign_id')

        qs = CallLog.objects.filter(start_time__date=today)
        if campaign_id and campaign_id != 'all':
            try:
                qs = qs.filter(campaign_id=int(campaign_id))
            except (ValueError, TypeError):
                pass

        stats = qs.aggregate(
            total    = Count('id'),
            answered = Count('id', filter=Q(answer_time__isnull=False)),
            sales    = Count('id', filter=Q(disposition__is_sale=True)),
            dropped  = Count('id', filter=Q(call_status='no-answer')),
        )

        total    = stats['total'] or 1
        answered = stats['answered'] or 0
        sales    = stats['sales']    or 0
        dropped  = stats['dropped']  or 0

        # Calls per hour since midnight
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        hours_elapsed = max((now - midnight).total_seconds() / 3600, 0.1)
        cph = round((stats['total'] or 0) / hours_elapsed, 1)

        # Avg talk duration
        from django.db.models import Avg
        avg_dur = qs.filter(answer_time__isnull=False).aggregate(
            avg=Avg('talk_duration')
        )['avg'] or 0

        # Calls trend (last 8 hours)
        trend = []
        for h in range(8, -1, -1):
            hour_start = now - timedelta(hours=h)
            hour_end   = now - timedelta(hours=h - 1) if h > 0 else now
            cnt = qs.filter(start_time__range=(hour_start, hour_end)).count()
            trend.append({'hour': hour_start.strftime('%H:00'), 'count': cnt})

        return JsonResponse({
            'success'             : True,
            'total_calls'         : stats['total'] or 0,
            'answered_calls'      : answered,
            'dropped_calls'       : dropped,
            'sales'               : sales,
            'calls_per_hour'      : cph,
            'avg_duration'        : int(avg_dur),
            'avg_duration_formatted': _fmt(avg_dur),
            'contact_rate'        : round(answered / total * 100, 1),
            'conversion_rate'     : round(sales    / max(answered, 1) * 100, 1),
            'drop_rate'           : round(dropped  / total * 100, 1),
            'calls_trend'         : trend,
            'server_time_ms'      : int(now.timestamp() * 1000),
        })
    except Exception as e:
        logger.exception('Error in realtime_campaign_stats_api')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@supervisor_required
def realtime_call_queue_api(request):
    """Call queue stats — unchanged."""
    try:
        from campaigns.models import OutboundQueue
        from django.db.models import Count, Q
        campaign_id = request.GET.get('campaign_id')

        qs = OutboundQueue.objects.all()
        if campaign_id and campaign_id != 'all':
            try:
                qs = qs.filter(campaign_id=int(campaign_id))
            except (ValueError, TypeError):
                pass

        stats = qs.aggregate(
            total   = Count('id'),
            pending = Count('id', filter=Q(status='new')),
            dialing = Count('id', filter=Q(status='dialing')),
        )
        return JsonResponse({'success': True, **stats})
    except Exception as e:
        logger.exception('Error in realtime_call_queue_api')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# Broadcast helpers (called from agents/views_simple.py on status change)
# ─────────────────────────────────────────────────────────────────────────────

def broadcast_agent_update(agent_id, status, campaign_id=None):
    """Broadcast agent status update to all realtime report subscribers via WebSocket."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        data = {
            'agent_id'   : agent_id,
            'status'     : status,
            'campaign_id': campaign_id,
            'timestamp'  : timezone.now().isoformat(),
            'changed_at_ms': int(timezone.now().timestamp() * 1000),
        }

        async_to_sync(channel_layer.group_send)(
            'realtime_report_all',
            {'type': 'agent_update', 'data': data}
        )
        if campaign_id:
            async_to_sync(channel_layer.group_send)(
                f'realtime_report_{campaign_id}',
                {'type': 'agent_update', 'data': data}
            )
    except Exception as e:
        logger.warning(f'broadcast_agent_update failed: {e}')


def broadcast_call_event(call_data, campaign_id=None):
    """Broadcast call event to realtime report subscribers."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        async_to_sync(channel_layer.group_send)(
            'realtime_report_all',
            {'type': 'call_update', 'data': call_data}
        )
    except Exception as e:
        logger.warning(f'broadcast_call_event failed: {e}')
