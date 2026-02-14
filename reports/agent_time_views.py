# reports/agent_time_views.py
# UPDATED: Login time tracking, per-session detail, summary per agent per day,
#          and live status with accurate status_changed_at_ms for realtime timers.

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Sum, Count, Q, Min, Max
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from core.decorators import supervisor_required
import csv
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(secs):
    """Seconds → HH:MM:SS string."""
    secs = int(secs or 0)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _to_ms(dt):
    """Aware datetime → Unix milliseconds or None."""
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


# ─────────────────────────────────────────────────────────────────────────────
# Admin report page
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@supervisor_required
def agent_time_report_page(request):
    """Render the agent time monitoring report page."""
    from django.contrib.auth.models import User
    agents = User.objects.filter(
        groups__name__in=['Agent', 'Supervisor']
    ).order_by('username').distinct()

    context = {
        'agents'  : agents,
        'today'   : timezone.now().date().isoformat(),
    }
    return render(request, 'reports/agent_time_report.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Main time breakdown API
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@supervisor_required
def agent_time_report_api(request):
    """
    JSON API for per-agent per-day time breakdown.

    Query params:
        agent_id   — optional, filter by single agent
        date_from  — YYYY-MM-DD (default: today)
        date_to    — YYYY-MM-DD (default: today)
        export     — 'csv' to download

    Response includes per-row:
        login_time    — total logged-in time (available+busy+wrapup+break+lunch+training+meeting)
        login_first   — ISO datetime of first login today
        login_last    — ISO datetime of last seen activity today
        available, busy, wrapup, break, offline  — HH:MM:SS formatted
        + _secs variants for sorting
    """
    from users.models import AgentTimeLog
    from datetime import date

    date_from_str = request.GET.get('date_from', timezone.now().date().isoformat())
    date_to_str   = request.GET.get('date_to',   timezone.now().date().isoformat())
    agent_id      = request.GET.get('agent_id')
    export_csv    = request.GET.get('export') == 'csv'

    try:
        date_from = date.fromisoformat(date_from_str)
        date_to   = date.fromisoformat(date_to_str)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid date. Use YYYY-MM-DD'}, status=400)

    qs = AgentTimeLog.objects.filter(date__range=(date_from, date_to))
    if agent_id:
        qs = qs.filter(user_id=agent_id)

    # ── For open (currently running) logs, add elapsed seconds up to now ──
    now = timezone.now()

    agg = (
        qs
        .values('user__id', 'user__username', 'user__first_name', 'user__last_name', 'date')
        .annotate(
            available_secs = Sum('duration_seconds', filter=Q(status='available')),
            busy_secs      = Sum('duration_seconds', filter=Q(status='busy')),
            wrapup_secs    = Sum('duration_seconds', filter=Q(status='wrapup')),
            break_secs     = Sum('duration_seconds', filter=Q(status__in=['break','lunch','training','meeting'])),
            lunch_secs     = Sum('duration_seconds', filter=Q(status='lunch')),
            training_secs  = Sum('duration_seconds', filter=Q(status='training')),
            meeting_secs   = Sum('duration_seconds', filter=Q(status='meeting')),
            offline_secs   = Sum('duration_seconds', filter=Q(status='offline')),
            first_activity = Min('started_at'),   # login time = first non-offline activity
            last_activity  = Max('ended_at'),     # last seen
        )
        .order_by('user__username', 'date')
    )

    # Also count open (in-progress) log seconds for agents currently active
    # Query open logs (ended_at=None) in the date range
    open_logs = (
        AgentTimeLog.objects.filter(
            date__range=(date_from, date_to),
            ended_at__isnull=True,
        )
    )
    if agent_id:
        open_logs = open_logs.filter(user_id=agent_id)

    # Build dict: (user_id, date, status) → extra_secs
    open_extra = {}
    for log in open_logs.exclude(status='offline'):
        key = (log.user_id, log.date, log.status)
        extra = int((now - log.started_at).total_seconds())
        open_extra[key] = open_extra.get(key, 0) + extra

    # Also first_login per (user_id, date)
    open_first = {}
    for log in open_logs:
        k = (log.user_id, log.date)
        if k not in open_first or log.started_at < open_first[k]:
            open_first[k] = log.started_at

    LOGGED_IN_STATUSES = {'available', 'busy', 'wrapup', 'break', 'lunch', 'training', 'meeting'}

    rows = []
    for r in agg:
        uid  = r['user__id']
        d    = r['date']

        avail = r['available_secs'] or 0
        busy  = r['busy_secs']      or 0
        wrap  = r['wrapup_secs']    or 0
        brk   = r['break_secs']     or 0
        off   = r['offline_secs']   or 0

        # Add open-log extras
        avail += open_extra.get((uid, d, 'available'), 0)
        busy  += open_extra.get((uid, d, 'busy'),      0)
        wrap  += open_extra.get((uid, d, 'wrapup'),    0)
        for s in ('break', 'lunch', 'training', 'meeting'):
            brk += open_extra.get((uid, d, s), 0)

        total_login = avail + busy + wrap + brk  # offline excluded

        # First login: Min(started_at for non-offline)
        first_login_qs = (
            AgentTimeLog.objects
            .filter(user_id=uid, date=d)
            .exclude(status='offline')
            .order_by('started_at')
            .values_list('started_at', flat=True)
            .first()
        )
        first_login = first_login_qs or open_first.get((uid, d))

        rows.append({
            'agent_id'       : uid,
            'agent'          : r['user__username'],
            'agent_name'     : f"{r['user__first_name']} {r['user__last_name']}".strip()
                               or r['user__username'],
            'date'           : str(d),

            # ── Formatted ──
            'login_time'     : _fmt(total_login),
            'available'      : _fmt(avail),
            'busy'           : _fmt(busy),
            'wrapup'         : _fmt(wrap),
            'break'          : _fmt(brk),
            'offline'        : _fmt(off),

            # ── Raw seconds (for sorting) ──
            'login_time_secs': total_login,
            'available_secs' : avail,
            'busy_secs'      : busy,
            'wrapup_secs'    : wrap,
            'break_secs'     : brk,
            'offline_secs'   : off,

            # ── Login timestamp ──
            'login_first'    : first_login.isoformat() if first_login else None,
            'login_first_str': first_login.strftime('%H:%M:%S') if first_login else '—',
        })

    # ── CSV export ──────────────────────────────────────────────────────────
    if export_csv:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="agent_time_{date_from}_{date_to}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow([
            'Date', 'Agent', 'Login At', 'Total Login Time',
            'Available', 'On Call', 'Wrap-up', 'Break/Away', 'Offline',
        ])
        for r in rows:
            writer.writerow([
                r['date'], r['agent_name'], r['login_first_str'],
                r['login_time'], r['available'], r['busy'],
                r['wrapup'], r['break'], r['offline'],
            ])
        return response

    return JsonResponse({'success': True, 'data': rows, 'count': len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# Live agent status (used by the admin live status widget)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@supervisor_required
def agent_realtime_status(request):
    """
    Current live status of all agents.
    Returns status_changed_at_ms so frontend can seed accurate timers.
    """
    from users.models import AgentStatus
    from calls.models import CallLog

    agents_qs = AgentStatus.objects.select_related(
        'user', 'current_campaign'
    ).exclude(user__is_superuser=True).order_by('user__username')

    now   = timezone.now()
    today = now.date()
    data  = []

    for ag in agents_qs:
        status_time_secs = 0
        if ag.status_changed_at:
            status_time_secs = int((now - ag.status_changed_at).total_seconds())

        # Login time today
        from users.models import AgentTimeLog
        today_logs = (
            AgentTimeLog.objects
            .filter(user_id=ag.user_id, date=today)
            .exclude(status='offline')
        )
        login_secs = 0
        login_at   = None
        for log in today_logs.order_by('started_at'):
            if login_at is None:
                login_at = log.started_at
            if log.ended_at:
                login_secs += log.duration_seconds or 0
            else:
                login_secs += int((now - log.started_at).total_seconds())

        # Current call
        current_call = None
        cid_str = getattr(ag, 'wrapup_call_id', None) or ag.current_call_id
        if cid_str:
            try:
                cl = CallLog.objects.filter(id=int(cid_str)).first()
                if cl:
                    current_call = {
                        'id'      : cl.id,
                        'number'  : cl.called_number,
                        'duration': cl.talk_duration,
                        'disposed': cl.disposition_id is not None,
                    }
            except Exception:
                pass

        # Zombie
        is_zombie = False
        if hasattr(ag, 'is_zombie') and ag.status != 'offline':
            is_zombie = ag.is_zombie(timeout_minutes=5)

        data.append({
            'agent_id'             : ag.user.id,
            'agent'                : ag.user.username,
            'agent_name'           : ag.user.get_full_name() or ag.user.username,
            'status'               : ag.status,
            'status_display'       : ag.get_status_display(),
            'status_time_secs'     : status_time_secs,
            'status_time_formatted': _fmt(status_time_secs),
            'status_changed_at_ms' : _to_ms(ag.status_changed_at),
            'login_time_secs'      : login_secs,
            'login_time_formatted' : _fmt(login_secs),
            'login_at_ms'          : _to_ms(login_at),
            'campaign'             : ag.current_campaign.name if ag.current_campaign else None,
            'last_heartbeat'       : ag.last_heartbeat.isoformat() if hasattr(ag, 'last_heartbeat') and ag.last_heartbeat else None,
            'last_heartbeat_ms'    : _to_ms(getattr(ag, 'last_heartbeat', None)),
            'is_zombie'            : is_zombie,
            'current_call'         : current_call,
            'needs_disposition'    : ag.needs_disposition() if hasattr(ag, 'needs_disposition') else False,
        })

    return JsonResponse({
        'success'       : True,
        'agents'        : data,
        'count'         : len(data),
        'server_time_ms': int(now.timestamp() * 1000),
    })
