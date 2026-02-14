# monitoring.py — Supervisor monitoring dashboard payload builder.
#
# ROOT FIX: AgentStatus.status_changed_at has auto_now=True which resets it
# on EVERY .save() call — heartbeats, call-ID writes, wrapup state updates,
# etc.  This made timer durations wrong after any of those saves.
#
# THE FIX: Use AgentTimeLog.started_at from the currently open log.
# started_at is written ONCE when the agent's status changes and is NEVER
# modified afterward.  Both the agent panel and the admin monitor read from
# this same DB field, so they always show identical, refresh-proof times.
#
# PERFORMANCE: all AgentTimeLog lookups are batched — 2 queries regardless
# of how many agents are online, instead of N per-agent queries.

from django.db.models import Count, Q
from django.utils import timezone

from campaigns.models import Campaign, OutboundQueue
from calls.models import CallLog
from agents.models import AgentDialerSession
from users.models import AgentStatus


def _to_ms(dt):
    """Aware datetime → Unix milliseconds (int), or None."""
    return int(dt.timestamp() * 1000) if dt else None


def _fmt(secs):
    """Format seconds → M:SS or H:MM:SS."""
    secs = max(0, int(secs or 0))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _batch_status_start(agent_ids, today):
    """
    Return {user_id: started_at_datetime} for the most recent OPEN
    AgentTimeLog entry per agent today.

    This is the reliable 'status started at' timestamp because:
    - It is written ONCE when the status changes (_open_time_log)
    - It is NEVER updated by heartbeats, call-ID writes, or any other
      .save() on AgentStatus
    - Both agent panel and admin monitor read the same DB row → always agree
    """
    from users.models import AgentTimeLog

    if not agent_ids:
        return {}

    rows = (
        AgentTimeLog.objects
        .filter(user_id__in=agent_ids, date=today, ended_at__isnull=True)
        .order_by('user_id', '-started_at')        # latest open log first
        .values('user_id', 'started_at')
    )
    result = {}
    for row in rows:
        uid = row['user_id']
        if uid not in result:                       # keep only the latest per agent
            result[uid] = row['started_at']
    return result


def _batch_login_info(agent_ids, today, now):
    """
    Return {user_id: {login_at_ms, login_secs}} using 2 DB queries total.

    login_at_ms  = Unix ms of the earliest non-offline AgentTimeLog today
    login_secs   = sum of all closed + open non-offline log durations today
    """
    from users.models import AgentTimeLog

    if not agent_ids:
        return {}

    result = {uid: {'login_at_ms': None, 'login_secs': 0} for uid in agent_ids}

    # Closed logs — sum duration_seconds
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
        result[uid]['login_secs'] += int(row['duration_seconds'] or 0)

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
        result[uid]['login_secs'] += max(
            0, int((now - row['started_at']).total_seconds())
        )

    return result


def build_monitor_payload():
    """
    Build the full payload for the supervisor monitoring dashboard.

    Each agent entry now includes accurate timer fields:

        status_changed_at_ms — Unix ms of when current status STARTED.
                               Source: AgentTimeLog.started_at (open log).
                               Frontend usage:
                                   skew = server_time_ms - Date.now()
                                   elapsed = (Date.now() + skew) - status_changed_at_ms

        status_time_secs     — pre-computed elapsed seconds (initial render)
        login_at_ms          — Unix ms of first login today
        login_time_secs      — total seconds logged in today
        server_time_ms       — current server time (for clock-skew correction)

    These same fields are returned by realtime_agents_api and agent_status_info
    so agent panel and admin monitor always show identical times.
    """
    now   = timezone.now()
    today = now.date()

    # ── All non-offline agents ──────────────────────────────────────────────
    agents_list = list(
        AgentStatus.objects
        .select_related('user', 'current_campaign')
        .exclude(status='offline')
    )
    agent_ids = [a.user_id for a in agents_list]

    # ── Batch DB lookups (no per-agent loops) ───────────────────────────────
    status_start_map = _batch_status_start(agent_ids, today)
    login_map        = _batch_login_info(agent_ids, today, now)

    # ── Build agent_data ────────────────────────────────────────────────────
    agent_data = []
    for ag in agents_list:
        uid  = ag.user_id
        user = ag.user

        # Reliable status start time
        open_started = status_start_map.get(uid)
        if open_started:
            status_changed_at_ms = _to_ms(open_started)
            status_time_secs     = max(0, int((now - open_started).total_seconds()))
        elif ag.status_changed_at:
            # Fallback — should not normally happen
            status_changed_at_ms = _to_ms(ag.status_changed_at)
            status_time_secs     = max(0, int((now - ag.status_changed_at).total_seconds()))
        else:
            status_changed_at_ms = None
            status_time_secs     = 0

        li = login_map.get(uid, {})

        # Current call info
        call_id      = ag.current_call_id or ''
        call_number  = None
        call_lead    = None
        if call_id:
            try:
                call = (CallLog.objects
                        .filter(id=int(call_id))
                        .select_related('lead')
                        .only('called_number', 'lead')
                        .first())
                if call:
                    call_number = call.called_number
                    if call.lead:
                        call_lead = (
                            f"{call.lead.first_name or ''} {call.lead.last_name or ''}".strip()
                            or call.lead.phone_number
                        )
            except Exception:
                pass

        campaign_name = '-'
        if ag.current_campaign:
            campaign_name = ag.current_campaign.name

        agent_data.append({
            'id'          : uid,
            'name'        : user.get_full_name() or user.username,
            'username'    : user.username,
            'status'      : ag.status,
            'status_display': ag.get_status_display(),
            'campaign'    : campaign_name,
            'call_id'     : call_id,
            'call_number' : call_number,
            'call_lead'   : call_lead,

            # ── Accurate timer fields (use these in the frontend) ──────────
            'status_changed_at_ms': status_changed_at_ms,
            'status_time_secs'    : status_time_secs,
            'login_at_ms'         : li.get('login_at_ms'),
            'login_time_secs'     : li.get('login_secs', 0),
            'server_time_ms'      : int(now.timestamp() * 1000),

            # Legacy field — kept for backward compat
            'duration': status_time_secs,

            # Call start ms for ticking call timer (if on a call)
            'call_start_ms': (
                _to_ms(ag.call_start_time)
                if ag.status == 'busy' and ag.call_start_time else None
            ),
        })

    # ── Queue stats per campaign ────────────────────────────────────────────
    campaigns  = Campaign.objects.filter(status='active')
    queue_data = []
    for c in campaigns:
        q_stats = OutboundQueue.objects.filter(campaign=c).aggregate(
            pending  =Count('id', filter=Q(status='new')),
            dialing  =Count('id', filter=Q(status='dialing')),
            connected=Count('id', filter=Q(status='answered')),
        )
        queue_data.append({
            'id'       : c.id,
            'name'     : c.name,
            'pending'  : q_stats['pending'],
            'dialing'  : q_stats['dialing'],
            'connected': q_stats['connected'],
        })

    # ── Today's call stats ──────────────────────────────────────────────────
    daily_stats = CallLog.objects.filter(start_time__date=today).aggregate(
        total   =Count('id'),
        answered=Count('id', filter=Q(call_status='answered')),
        sales   =Count('id', filter=Q(disposition__is_sale=True)),
    )

    return {
        'agents'        : agent_data,
        'queues'        : queue_data,
        'server_time_ms': int(now.timestamp() * 1000),
        'stats'         : {
            'total_calls'  : daily_stats['total'],
            'answered'     : daily_stats['answered'],
            'sales'        : daily_stats['sales'],
            'active_agents': len(agent_data),
        },
    }
