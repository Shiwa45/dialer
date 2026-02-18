"""
agents/views_admin_history.py  –  Phase 6: Admin Agent Call History
===================================================================

Full per-agent call timeline for managers/supervisors.

Endpoints:
    GET  /agents/admin/history/              – agent selector
    GET  /agents/admin/history/<agent_id>/   – timeline for one agent
    GET  /agents/admin/history/<agent_id>/export/  – CSV download
    GET  /agents/api/admin/history/<agent_id>/     – JSON (AJAX pagination)
"""

import csv
import logging
from datetime import timedelta

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone

from calls.models import CallLog
from campaigns.models import Campaign, Disposition

logger = logging.getLogger(__name__)


def _is_supervisor(user):
    try:
        return user.is_staff or user.profile.is_manager() or user.profile.is_supervisor()
    except Exception:
        return user.is_staff


# ────────────────────────────────────────────────────────────────────
# 1. Agent selector (index)
# ────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(_is_supervisor)
def agent_history_index(request):
    """List all agents with today's summary stats."""
    today = timezone.now().date()

    agents = (
        User.objects.filter(profile__role='agent', is_active=True)
        .select_related('profile', 'agent_status')
        .order_by('first_name', 'last_name')
    )

    agent_summaries = []
    for agent in agents:
        qs = CallLog.objects.filter(agent=agent, start_time__date=today)
        total    = qs.count()
        answered = qs.filter(call_status='answered').count()
        talk_sec = qs.aggregate(t=Sum('talk_duration'))['t'] or 0

        try:
            status = agent.agent_status.status
        except Exception:
            status = 'offline'

        agent_summaries.append({
            'agent':        agent,
            'status':       status,
            'total_calls':  total,
            'answered':     answered,
            'contact_rate': round((answered / total * 100) if total else 0, 1),
            'talk_time':    _fmt_sec(int(talk_sec)),
        })

    return render(request, 'agents/admin/agent_history_index.html', {
        'agent_summaries': agent_summaries,
        'today':           today,
    })


# ────────────────────────────────────────────────────────────────────
# 2. Single-agent timeline
# ────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(_is_supervisor)
def agent_history_detail(request, agent_id):
    """Full call timeline for one agent with filters."""
    agent = get_object_or_404(User, id=agent_id)

    # ── Filter params ──
    date_from     = request.GET.get('date_from') or (timezone.now().date() - timedelta(days=7)).isoformat()
    date_to       = request.GET.get('date_to')   or timezone.now().date().isoformat()
    campaign_id   = request.GET.get('campaign')
    disposition_id = request.GET.get('disposition')
    call_status   = request.GET.get('status')
    search_phone  = request.GET.get('phone', '').strip()
    per_page      = int(request.GET.get('per_page', 25))

    qs = (
        CallLog.objects
        .filter(agent=agent, start_time__date__gte=date_from, start_time__date__lte=date_to)
        .select_related('lead', 'campaign', 'disposition')
        .order_by('-start_time')
    )

    if campaign_id:
        qs = qs.filter(campaign_id=campaign_id)
    if disposition_id:
        qs = qs.filter(disposition_id=disposition_id)
    if call_status:
        qs = qs.filter(call_status=call_status)
    if search_phone:
        qs = qs.filter(
            Q(called_number__icontains=search_phone) |
            Q(lead__phone_number__icontains=search_phone)
        )

    # ── Summary stats for the filtered range ──
    summary = qs.aggregate(
        total=Count('id'),
        answered=Count('id', filter=Q(call_status='answered')),
        total_talk=Sum('talk_duration'),
        avg_talk=Avg('talk_duration'),
    )
    total    = summary['total'] or 0
    answered = summary['answered'] or 0
    summary['contact_rate'] = round((answered / total * 100) if total else 0, 1)
    summary['talk_fmt']     = _fmt_sec(int(summary['total_talk'] or 0))
    summary['avg_talk_fmt'] = _fmt_sec(int(summary['avg_talk']   or 0))

    # ── Disposition breakdown ──
    disp_breakdown = (
        qs.filter(disposition__isnull=False)
        .values('disposition__name', 'disposition__category')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    # ── Paginate ──
    paginator = Paginator(qs, per_page)
    page_obj  = paginator.get_page(request.GET.get('page', 1))

    # ── Filter dropdowns ──
    campaigns    = Campaign.objects.filter(status__in=['active', 'paused']).order_by('name')
    dispositions = Disposition.objects.filter(is_active=True).order_by('name')

    return render(request, 'agents/admin/agent_history_detail.html', {
        'agent':          agent,
        'page_obj':       page_obj,
        'summary':        summary,
        'disp_breakdown': disp_breakdown,
        'campaigns':      campaigns,
        'dispositions':   dispositions,
        # Filter values (for form repopulation)
        'f_date_from':    date_from,
        'f_date_to':      date_to,
        'f_campaign':     campaign_id,
        'f_disposition':  disposition_id,
        'f_status':       call_status,
        'f_phone':        search_phone,
        'per_page':       per_page,
    })


# ────────────────────────────────────────────────────────────────────
# 3. JSON API (AJAX, for infinite scroll / modal)
# ────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(_is_supervisor)
@require_http_methods(['GET'])
def agent_history_api(request, agent_id):
    """Return paginated call log as JSON."""
    agent = get_object_or_404(User, id=agent_id)

    date_from    = request.GET.get('date_from') or (timezone.now().date() - timedelta(days=7)).isoformat()
    date_to      = request.GET.get('date_to')   or timezone.now().date().isoformat()
    campaign_id  = request.GET.get('campaign')
    call_status  = request.GET.get('status')
    page         = int(request.GET.get('page', 1))
    per_page     = int(request.GET.get('per_page', 25))

    qs = (
        CallLog.objects
        .filter(agent=agent, start_time__date__gte=date_from, start_time__date__lte=date_to)
        .select_related('lead', 'campaign', 'disposition')
        .order_by('-start_time')
    )
    if campaign_id:
        qs = qs.filter(campaign_id=campaign_id)
    if call_status:
        qs = qs.filter(call_status=call_status)

    paginator = Paginator(qs, per_page)
    page_obj  = paginator.get_page(page)

    calls = []
    for c in page_obj:
        calls.append({
            'id':          c.id,
            'start_time':  c.start_time.isoformat() if c.start_time else None,
            'duration':    c.talk_duration or 0,
            'number':      c.called_number or '',
            'lead':        f'{c.lead.first_name} {c.lead.last_name}' if c.lead else '',
            'campaign':    c.campaign.name if c.campaign else '',
            'status':      c.call_status or '',
            'disposition': c.disposition.name if c.disposition else '',
            'recording':   bool(c.recording_filename),
        })

    return JsonResponse({
        'success':    True,
        'calls':      calls,
        'total':      paginator.count,
        'page':       page,
        'num_pages':  paginator.num_pages,
        'has_next':   page_obj.has_next(),
    })


# ────────────────────────────────────────────────────────────────────
# 4. CSV export
# ────────────────────────────────────────────────────────────────────

class _Echo:
    """Minimal write-compatible object for StreamingHttpResponse."""
    def write(self, value):
        return value


@login_required
@user_passes_test(_is_supervisor)
def agent_history_export(request, agent_id):
    """Stream a CSV of the agent's call history."""
    agent = get_object_or_404(User, id=agent_id)

    date_from = request.GET.get('date_from') or (timezone.now().date() - timedelta(days=30)).isoformat()
    date_to   = request.GET.get('date_to')   or timezone.now().date().isoformat()

    qs = (
        CallLog.objects
        .filter(agent=agent, start_time__date__gte=date_from, start_time__date__lte=date_to)
        .select_related('lead', 'campaign', 'disposition')
        .order_by('-start_time')
    )

    HEADERS = [
        'Call ID', 'Start Time', 'Duration (s)', 'Phone Number',
        'Lead Name', 'Campaign', 'Status', 'Disposition', 'Has Recording',
    ]

    def rows():
        yield HEADERS
        for c in qs.iterator(chunk_size=500):
            yield [
                c.id,
                c.start_time.strftime('%Y-%m-%d %H:%M:%S') if c.start_time else '',
                c.talk_duration or 0,
                c.called_number or '',
                f'{c.lead.first_name} {c.lead.last_name}' if c.lead else '',
                c.campaign.name if c.campaign else '',
                c.call_status or '',
                c.disposition.name if c.disposition else '',
                'Yes' if c.recording_filename else 'No',
            ]

    pseudo_buffer = _Echo()
    writer        = csv.writer(pseudo_buffer)
    response = StreamingHttpResponse(
        (writer.writerow(row) for row in rows()),
        content_type='text/csv',
    )
    filename = f'agent_{agent.username}_calls_{date_from}_{date_to}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _fmt_sec(s: int) -> str:
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f'{h}h {m:02d}m {sec:02d}s'
    return f'{m}m {sec:02d}s'
