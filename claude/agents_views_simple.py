"""
Agent Views (Simple Dashboard) - WebRTC Rebuild v3

FIXES in v3:
- ICE servers passed as json_script (no escapejs mangling)
- CampaignDisposition through-table query (not Disposition.campaign)
- Proper fallback when ice_host has invalid JSON
"""

import json
import logging
import html as html_mod
from datetime import timedelta

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import timezone
from django.db.models import Q, Sum
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from agents.decorators import agent_required
from agents.models import AgentDialerSession, AgentCallbackTask
from agents.telephony_service import AgentTelephonyService
from calls.models import CallLog
from campaigns.models import Campaign, CampaignDisposition, OutboundQueue
from leads.models import Lead
from users.models import AgentStatus
from telephony.models import Phone, AsteriskServer
from telephony.services import AsteriskService

logger = logging.getLogger(__name__)


# ==========================================================================
# ICE SERVER CONFIG BUILDER (bulletproof)
# ==========================================================================

def _build_ice_servers(phone):
    """
    Parse phone.ice_host into a clean list of RTCIceServer objects.
    Handles: JSON array, JSON object, comma-separated URLs, or empty.
    Always includes a default STUN server.
    Returns a Python list like [{"urls": "stun:..."}, {"urls": "turn:...", ...}]
    """
    DEFAULT_STUN = {"urls": "stun:stun.l.google.com:19302"}
    result = []

    raw = (getattr(phone, 'ice_host', '') or '').strip()
    # Unescape any HTML entities from admin forms
    raw = html_mod.unescape(raw)

    if raw:
        # Try JSON parse first
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and item.get('urls'):
                        result.append(item)
                    elif isinstance(item, str):
                        result.append({"urls": item})
            elif isinstance(parsed, dict) and parsed.get('urls'):
                result.append(parsed)
        except (json.JSONDecodeError, TypeError):
            # Not JSON — treat as comma-separated STUN/TURN URLs
            for url in raw.split(','):
                url = url.strip()
                if url:
                    result.append({"urls": url})

    # Ensure we always have at least one STUN
    has_stun = any(
        'stun:' in str(s.get('urls', ''))
        for s in result
    )
    if not has_stun:
        result.insert(0, DEFAULT_STUN)

    return result


def _build_webrtc_config(phone, agent):
    """Build complete WebRTC config dict for template context."""
    if not phone or not phone.asterisk_server:
        return {}
    server = phone.asterisk_server
    domain = server.server_ip
    ice_servers = _build_ice_servers(phone)

    return {
        'ws_server': f'wss://{domain}:8089/ws',
        'sip_uri': f'sip:{phone.extension}@{domain}',
        'extension': phone.extension,
        'password': getattr(phone, 'sip_password', None) or phone.secret,
        'domain': domain,
        'display_name': agent.get_full_name() or agent.username,
        'stun_servers': ['stun:stun.l.google.com:19302'],
        # This will be passed via json_script tag — no escapejs needed
        'ice_servers': ice_servers,
        'codecs': (phone.codec or 'ulaw,alaw').split(','),
        'debug': False,
    }


def _get_agent_phone(agent):
    phone = Phone.objects.filter(user=agent, is_active=True).first()
    if not phone:
        try:
            ext = (agent.profile.extension or '').strip()
            if ext:
                phone = Phone.objects.filter(extension=ext, is_active=True).first()
        except Exception:
            pass
    return phone


# ==========================================================================
# DASHBOARD CONTEXT
# ==========================================================================

def _get_dashboard_context(request, agent, agent_status, phone):
    assigned_campaigns = Campaign.objects.filter(assigned_users=agent, status='active')
    current_campaign = agent_status.current_campaign
    if not current_campaign and assigned_campaigns.exists():
        current_campaign = assigned_campaigns.first()

    phone_info = {
        'extension': phone.extension if phone else None,
        'is_active': phone.is_active if phone else False,
        'webrtc_enabled': getattr(phone, 'webrtc_enabled', False) if phone else False,
        'registered': False
    }
    if phone:
        try:
            svc = AgentTelephonyService(agent)
            phone_info['registered'] = svc.is_extension_registered()
        except Exception as e:
            logger.warning(f"Registration check failed for {agent.username}: {e}")

    today = timezone.now().date()
    today_calls = CallLog.objects.filter(agent=agent, start_time__date=today)
    today_stats = {
        'total_calls': today_calls.count(),
        'answered_calls': today_calls.filter(call_status='answered').count(),
        'talk_time': today_calls.aggregate(Sum('talk_duration'))['talk_duration__sum'] or 0,
    }

    pending_callbacks = AgentCallbackTask.objects.filter(
        agent=agent, status__in=['pending', 'scheduled'],
        scheduled_time__lte=timezone.now() + timedelta(hours=2)
    ).order_by('scheduled_time')[:5]

    # FIX: use CampaignDisposition through-table, not Disposition.campaign
    available_dispositions = []
    if current_campaign:
        camp_disps = CampaignDisposition.objects.filter(
            campaign=current_campaign, is_active=True
        ).select_related('disposition').order_by('sort_order')
        available_dispositions = [
            {'id': cd.disposition.id, 'name': cd.disposition.name,
             'category': cd.disposition.category,
             'is_sale': cd.disposition.is_sale,
             'is_callback': cd.disposition.requires_callback}
            for cd in camp_disps if cd.disposition.is_active
        ]

    webrtc_config = {}
    if phone and phone.webrtc_enabled:
        webrtc_config = _build_webrtc_config(phone, agent)

    script_content = ''
    if current_campaign:
        try:
            from agents.models import AgentScript
            script = AgentScript.objects.filter(
                Q(campaign=current_campaign) | Q(is_global=True), is_active=True
            ).order_by('display_order').first()
            if script:
                script_content = script.content
        except Exception:
            pass

    return {
        'user': agent, 'agent': agent, 'agent_status': agent_status,
        'assigned_campaigns': assigned_campaigns,
        'current_campaign': current_campaign,
        'today_stats': today_stats,
        'pending_callbacks': pending_callbacks,
        'available_dispositions': available_dispositions,
        'phone_info': phone_info,
        'webrtc_config': webrtc_config,
        'script_content': script_content,
        'call_status_url': '/agents/api/call-status/',
        'lead_info_url': '/agents/api/lead-info/',
        'disposition_url': '/agents/api/set-disposition/',
        'manual_dial_url': '/agents/api/manual-dial/',
        'hangup_url': '/agents/api/hangup/',
        'transfer_call_url': '/agents/api/transfer/',
    }


# ==========================================================================
# DASHBOARD VIEW
# ==========================================================================

@login_required
@agent_required
def simple_dashboard(request):
    agent = request.user
    agent_status, _ = AgentStatus.objects.get_or_create(user=agent)
    phone = _get_agent_phone(agent)
    context = _get_dashboard_context(request, agent, agent_status, phone)

    if phone and getattr(phone, 'webrtc_enabled', False):
        return render(request, 'agents/webrtc_dashboard.html', context)

    return render(request, 'agents/simple_dashboard.html', context)


# ==========================================================================
# API ENDPOINTS (unchanged from v2, included for completeness)
# ==========================================================================

@login_required
@agent_required
@require_POST
def update_status(request):
    agent = request.user
    new_status = request.POST.get('status', '').strip().lower()
    if not new_status:
        return JsonResponse({'success': False, 'error': 'Status is required'})
    status_map = {
        'available': 'available', 'ready': 'available', 'break': 'break',
        'lunch': 'lunch', 'meeting': 'meeting', 'training': 'training',
        'offline': 'offline', 'busy': 'busy', 'wrapup': 'wrapup'
    }
    mapped = status_map.get(new_status, new_status)
    try:
        agent_status, _ = AgentStatus.objects.get_or_create(user=agent)
        agent_status.set_status(mapped)
        return JsonResponse({'success': True, 'status': mapped, 'display': agent_status.get_status_display()})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@agent_required
@require_POST
def set_disposition(request):
    agent = request.user
    call_id = request.POST.get('call_id')
    disposition_id = request.POST.get('disposition_id') or request.POST.get('disposition')
    notes = request.POST.get('notes', '')

    if not call_id:
        return JsonResponse({'success': False, 'error': 'Call ID required'})
    if not disposition_id:
        return JsonResponse({'success': False, 'error': 'Disposition required'})

    try:
        call_log = CallLog.objects.filter(id=int(call_id), agent=agent).first()
        if not call_log:
            return JsonResponse({'success': False, 'error': 'Call not found'})

        from campaigns.models import Disposition
        try:
            disposition = Disposition.objects.get(id=int(disposition_id))
            call_log.disposition = disposition.name
        except (Disposition.DoesNotExist, ValueError):
            call_log.disposition = str(disposition_id)

        call_log.agent_notes = notes
        call_log.save()

        if call_log.lead:
            call_log.lead.last_call_time = timezone.now()
            call_log.lead.save(update_fields=['last_call_time'])

        agent_status = getattr(agent, 'agent_status', None)
        if agent_status:
            agent_status.current_call_id = None
            agent_status.set_status('available')

        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'agent_{agent.id}', {'type': 'call_cleared', 'call_id': call_id}
            )
        except Exception:
            pass

        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Disposition error: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@agent_required
@require_POST
def hangup_call(request):
    agent = request.user
    call_id = request.POST.get('call_id')
    try:
        svc = AgentTelephonyService(agent)
        if svc.agent_phone and svc.asterisk_server:
            try:
                AsteriskService(svc.asterisk_server).hangup_channel(svc.agent_phone.extension)
            except Exception:
                pass
        if call_id:
            try:
                cl = CallLog.objects.filter(id=int(call_id), agent=agent).first()
                if cl and cl.call_status not in ('completed', 'failed'):
                    cl.call_status = 'completed'
                    cl.end_time = timezone.now()
                    if cl.answer_time:
                        cl.talk_duration = int((cl.end_time - cl.answer_time).total_seconds())
                    cl.save()
            except (ValueError, TypeError):
                pass
        agent_status = getattr(agent, 'agent_status', None)
        if agent_status:
            agent_status.current_call_id = None
            agent_status.save(update_fields=['current_call_id'])
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@agent_required
@require_http_methods(["GET"])
def get_lead_info(request):
    lead_id = request.GET.get('lead_id')
    call_id = request.GET.get('call_id')
    try:
        lead = None
        if lead_id:
            lead = Lead.objects.filter(id=int(lead_id)).first()
        elif call_id:
            cl = CallLog.objects.filter(id=int(call_id)).first()
            if cl:
                lead = cl.lead
        if not lead:
            return JsonResponse({'success': False, 'error': 'Lead not found'})
        history = CallLog.objects.filter(lead=lead).order_by('-start_time')[:10]
        return JsonResponse({
            'success': True,
            'lead': {
                'id': lead.id, 'first_name': lead.first_name,
                'last_name': lead.last_name, 'phone_number': lead.phone_number,
                'email': getattr(lead, 'email', ''), 'company': getattr(lead, 'company', ''),
                'city': getattr(lead, 'city', ''), 'state': getattr(lead, 'state', ''),
                'status': lead.status,
            },
            'call_history': [
                {'id': c.id, 'date': c.start_time.strftime('%Y-%m-%d %H:%M'),
                 'status': c.call_status, 'duration': c.talk_duration or 0,
                 'disposition': c.disposition or ''}
                for c in history
            ]
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@agent_required
@require_http_methods(["GET"])
def get_call_status(request):
    agent = request.user
    try:
        agent_status = getattr(agent, 'agent_status', None)
        current_call = None
        if agent_status and agent_status.current_call_id:
            try:
                cl = CallLog.objects.filter(id=int(agent_status.current_call_id)).first()
                if cl:
                    dur = int((timezone.now() - cl.answer_time).total_seconds()) if cl.answer_time else 0
                    current_call = {'id': cl.id, 'number': cl.called_number,
                                    'status': cl.call_status, 'duration': dur, 'lead_id': cl.lead_id}
            except (TypeError, ValueError):
                pass
        return JsonResponse({
            'success': True,
            'status': agent_status.status if agent_status else 'offline',
            'current_call': current_call
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@agent_required
@require_http_methods(["GET"])
def get_webrtc_config(request):
    agent = request.user
    try:
        phone = _get_agent_phone(agent)
        if not phone or not phone.webrtc_enabled:
            return JsonResponse({'success': False, 'error': 'WebRTC not enabled'})
        config = _build_webrtc_config(phone, agent)
        return JsonResponse({'success': True, **config})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@agent_required
@require_http_methods(["GET"])
def agent_statistics(request):
    agent = request.user
    try:
        today = timezone.now().date()
        tc = CallLog.objects.filter(agent=agent, start_time__date=today)
        ws = today - timedelta(days=today.weekday())
        wc = CallLog.objects.filter(agent=agent, start_time__date__gte=ws)
        tt, ta = tc.count(), tc.filter(call_status='answered').count()
        wt, wa = wc.count(), wc.filter(call_status='answered').count()
        return JsonResponse({
            'success': True,
            'today': {'total_calls': tt, 'answered_calls': ta,
                      'talk_time': tc.aggregate(t=Sum('talk_duration'))['t'] or 0,
                      'contact_rate': round((ta / tt * 100) if tt else 0, 1)},
            'week': {'total_calls': wt, 'answered_calls': wa,
                     'talk_time': wc.aggregate(t=Sum('talk_duration'))['t'] or 0,
                     'contact_rate': round((wa / wt * 100) if wt else 0, 1)},
            'pending_callbacks': AgentCallbackTask.objects.filter(
                agent=agent, status__in=['pending', 'scheduled']).count()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
