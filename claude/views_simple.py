# agents/views_simple.py
# =============================================================================
# COMPLETE REWRITE - All bugs fixed:
#   ✔ Disposition ForeignKey fix (was assigning string, must be Disposition instance)
#   ✔ Call state persisted in DB - survives page refresh
#   ✔ Wrapup popup forces disposition before status clears
#   ✔ Logout blocked during wrapup
#   ✔ Heartbeat endpoint to kill zombie sessions
#   ✔ Agent time monitoring via AgentTimeLog
#   ✔ check_wrapup_state API so frontend always knows what to show on load
# =============================================================================

import json
import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from agents.decorators import agent_required
from agents.models import AgentCallbackTask
from calls.models import CallLog
from campaigns.models import Campaign, Disposition, CampaignDisposition, OutboundQueue
from leads.models import Lead
from users.models import AgentStatus
from telephony.models import Phone

logger = logging.getLogger(__name__)


# ==========================================================================
# HELPERS
# ==========================================================================

def _get_agent_phone(agent):
    """Return active phone for agent, trying profile extension as fallback."""
    phone = Phone.objects.filter(user=agent, is_active=True).first()
    if not phone:
        try:
            ext = (agent.profile.extension or '').strip()
            if ext:
                phone = Phone.objects.filter(extension=ext, is_active=True).first()
        except Exception:
            pass
    return phone


def _build_webrtc_config(phone, agent=None):
    """Build WebRTC config dict from Phone object."""
    server = getattr(phone, 'asterisk_server', None)
    host = server.server_ip if server else 'localhost'
    ws_port = getattr(server, 'websocket_port', 8089) if server else 8089
    domain = getattr(server, 'domain', host) if server else host
    return {
        'extension': phone.extension,
        'secret': getattr(phone, 'secret', '') or getattr(phone, 'password', ''),
        'domain': domain,
        'host': host,
        'ws_server': f"wss://{host}:{ws_port}/ws",
        'stun_server': getattr(phone, 'ice_host', None) or 'stun:stun.l.google.com:19302',
        'codecs': phone.codec.split(',') if getattr(phone, 'codec', None) else ['ulaw', 'alaw', 'g722'],
        'transport': 'wss',
        'realm': domain,
    }


def _get_dashboard_context(request, agent, agent_status, phone):
    """Build dashboard context dict."""
    from agents.models import AgentCallbackTask

    assigned_campaigns = Campaign.objects.filter(assigned_users=agent, status='active')
    current_campaign = agent_status.current_campaign
    if not current_campaign and assigned_campaigns.exists():
        current_campaign = assigned_campaigns.first()

    phone_info = {
        'extension': phone.extension if phone else None,
        'is_active': phone.is_active if phone else False,
        'webrtc_enabled': getattr(phone, 'webrtc_enabled', False) if phone else False,
        'registered': False,
    }

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

    available_dispositions = []
    if current_campaign:
        camp_disps = CampaignDisposition.objects.filter(
            campaign=current_campaign, is_active=True
        ).select_related('disposition').order_by('sort_order')
        available_dispositions = [
            {
                'id': cd.disposition.id,
                'name': cd.disposition.name,
                'category': cd.disposition.category,
                'is_sale': cd.disposition.is_sale,
                'is_callback': cd.disposition.requires_callback,
            }
            for cd in camp_disps if cd.disposition.is_active
        ]

    # Fallback: all active dispositions when no campaign
    if not available_dispositions:
        available_dispositions = [
            {'id': d.id, 'name': d.name, 'category': d.category,
             'is_sale': d.is_sale, 'is_callback': d.requires_callback}
            for d in Disposition.objects.filter(is_active=True).order_by('name')
        ]

    webrtc_config = {}
    if phone and getattr(phone, 'webrtc_enabled', False):
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
        'user': agent,
        'agent': agent,
        'agent_status': agent_status,
        'assigned_campaigns': assigned_campaigns,
        'current_campaign': current_campaign,
        'today_stats': today_stats,
        'pending_callbacks': pending_callbacks,
        'available_dispositions': available_dispositions,
        'phone_info': phone_info,
        'webrtc_config': webrtc_config,
        'script_content': script_content,
        # URLs injected into templates for JS
        'call_status_url': '/agents/api/call-status/',
        'lead_info_url': '/agents/api/lead-info/',
        'disposition_url': '/agents/api/set-disposition/',
        'manual_dial_url': '/agents/api/manual-dial/',
        'hangup_url': '/agents/api/hangup/',
        'transfer_call_url': '/agents/api/transfer/',
        'heartbeat_url': '/agents/api/heartbeat/',
        'wrapup_state_url': '/agents/api/wrapup-state/',
        'logout_check_url': '/agents/api/can-logout/',
    }


def _broadcast_agent_event(agent_id, event_type, data=None):
    """Fire and forget WebSocket broadcast to agent group."""
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        payload = {'type': event_type}
        if data:
            payload.update(data)
        async_to_sync(channel_layer.group_send)(
            f"agent_{agent_id}",
            {'type': 'call_event', 'data': payload}
        )
    except Exception as e:
        logger.debug(f"WS broadcast failed: {e}")


# ==========================================================================
# DASHBOARD VIEW
# ==========================================================================

@login_required
@agent_required
def simple_dashboard(request):
    agent = request.user
    agent_status, _ = AgentStatus.objects.get_or_create(user=agent)

    # Mark heartbeat on every page load
    agent_status.last_heartbeat = timezone.now()
    agent_status.save(update_fields=['last_heartbeat'])

    phone = _get_agent_phone(agent)
    context = _get_dashboard_context(request, agent, agent_status, phone)

    if phone and getattr(phone, 'webrtc_enabled', False):
        return render(request, 'agents/webrtc_dashboard.html', context)

    return render(request, 'agents/simple_dashboard.html', context)


# ==========================================================================
# HEARTBEAT  — call every 30s from frontend to prevent zombie status
# ==========================================================================

@login_required
@agent_required
@require_POST
def agent_heartbeat(request):
    """
    Receives periodic ping from agent browser.
    Updates last_heartbeat so the zombie-cleanup task knows the agent is alive.
    """
    agent = request.user
    try:
        agent_status, _ = AgentStatus.objects.get_or_create(user=agent)
        agent_status.update_heartbeat()
        return JsonResponse({'success': True, 'ts': timezone.now().isoformat()})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==========================================================================
# WRAPUP STATE CHECK — called on page load to restore call UI
# ==========================================================================

@login_required
@agent_required
@require_http_methods(["GET"])
def get_wrapup_state(request):
    """
    Returns current wrapup state so dashboard JS can restore disposition popup
    after a page refresh without losing the pending call.
    """
    agent = request.user
    try:
        agent_status = getattr(agent, 'agent_status', None)
        if not agent_status:
            return JsonResponse({'needs_disposition': False, 'status': 'offline'})

        if agent_status.needs_disposition():
            call_id = agent_status.wrapup_call_id or agent_status.current_call_id
            call_log = None
            try:
                call_log = CallLog.objects.filter(id=int(call_id)).first()
            except (TypeError, ValueError):
                pass

            call_data = None
            if call_log:
                call_data = {
                    'id': call_log.id,
                    'number': call_log.called_number,
                    'status': call_log.call_status,
                    'duration': call_log.talk_duration or 0,
                    'lead_id': call_log.lead_id,
                    'start_time': call_log.start_time.isoformat() if call_log.start_time else None,
                }

            return JsonResponse({
                'needs_disposition': True,
                'status': agent_status.status,
                'call_id': call_id,
                'call': call_data,
                'wrapup_started_at': (
                    agent_status.wrapup_started_at.isoformat()
                    if agent_status.wrapup_started_at else None
                ),
            })

        return JsonResponse({
            'needs_disposition': False,
            'status': agent_status.status,
        })
    except Exception as e:
        logger.error(f"get_wrapup_state error: {e}")
        return JsonResponse({'needs_disposition': False, 'status': 'unknown', 'error': str(e)})


# ==========================================================================
# CAN LOGOUT CHECK
# ==========================================================================

@login_required
@require_http_methods(["GET"])
def can_logout(request):
    """
    Returns {can_logout: bool, reason: str}.
    Frontend calls this before allowing logout.
    """
    agent = request.user
    try:
        agent_status = getattr(agent, 'agent_status', None)
        if agent_status and agent_status.needs_disposition():
            return JsonResponse({
                'can_logout': False,
                'reason': 'You have a pending call that requires disposition. Please dispose the call before logging out.',
                'call_id': agent_status.wrapup_call_id or agent_status.current_call_id,
            })
        return JsonResponse({'can_logout': True})
    except Exception as e:
        return JsonResponse({'can_logout': True, 'error': str(e)})


# ==========================================================================
# STATUS UPDATE
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
        'available': 'available', 'ready': 'available',
        'break': 'break', 'lunch': 'lunch',
        'meeting': 'meeting', 'training': 'training',
        'offline': 'offline', 'busy': 'busy', 'wrapup': 'wrapup',
        'system_issues': 'system_issues',
    }
    mapped = status_map.get(new_status, new_status)

    try:
        agent_status, _ = AgentStatus.objects.get_or_create(user=agent)

        # Block status change away from wrapup if disposition is pending
        if agent_status.needs_disposition() and mapped not in ('wrapup', 'offline'):
            return JsonResponse({
                'success': False,
                'blocked': True,
                'error': 'Cannot change status — please dispose the call first.',
                'call_id': agent_status.wrapup_call_id or agent_status.current_call_id,
            })

        agent_status.set_status(mapped)
        return JsonResponse({
            'success': True,
            'status': mapped,
            'display': agent_status.get_status_display()
        })
    except Exception as e:
        logger.error(f"update_status error for {agent.username}: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


# ==========================================================================
# SET DISPOSITION  — THE CRITICAL FIX
# ==========================================================================

@login_required
@agent_required
@require_POST
def set_disposition(request):
    """
    Save call disposition and clear wrapup state.

    KEY FIX: CallLog.disposition is a ForeignKey to campaigns.Disposition.
             Must assign the Disposition INSTANCE, not its name/id string.
    """
    agent = request.user
    call_id = request.POST.get('call_id')
    disposition_id = request.POST.get('disposition_id') or request.POST.get('disposition')
    notes = request.POST.get('notes', '').strip()

    if not call_id:
        return JsonResponse({'success': False, 'error': 'Call ID required'})
    if not disposition_id:
        return JsonResponse({'success': False, 'error': 'Disposition required'})

    try:
        # ── 1. Resolve CallLog ─────────────────────────────────────
        call_log = None
        try:
            call_log = CallLog.objects.filter(id=int(call_id)).first()
        except (TypeError, ValueError):
            pass

        if not call_log:
            # Try by call UUID
            call_log = CallLog.objects.filter(call_id=str(call_id)).first()

        if not call_log:
            return JsonResponse({
                'success': False,
                'error': f'Call log {call_id} not found'
            })

        # ── 2. Resolve Disposition instance ───────────────────────
        #       THIS IS THE CRITICAL FIX - must assign FK instance
        disposition = None
        try:
            disposition = Disposition.objects.get(id=int(disposition_id))
        except (Disposition.DoesNotExist, TypeError, ValueError):
            return JsonResponse({
                'success': False,
                'error': f'Disposition ID {disposition_id} not found'
            })

        # ── 3. Save disposition on CallLog (FK assignment) ─────────
        call_log.disposition = disposition          # FK instance — fixes the bug
        call_log.disposition_notes = notes
        if not call_log.end_time:
            call_log.end_time = timezone.now()
        if call_log.answer_time and not call_log.talk_duration:
            call_log.talk_duration = max(
                0, int((call_log.end_time - call_log.answer_time).total_seconds())
            )
        call_log.call_status = 'answered'
        call_log.save(update_fields=[
            'disposition', 'disposition_notes', 'end_time',
            'talk_duration', 'call_status'
        ])

        logger.info(
            f"Disposition set: agent={agent.username}, "
            f"call={call_log.id}, disposition={disposition.name}"
        )

        # ── 4. Update lead status ───────────────────────────────────
        if call_log.lead:
            lead = call_log.lead
            category = disposition.category
            status_map = {
                'sale': 'sale',
                'callback': 'callback',
                'dnc': 'dnc',
                'not_interested': 'not_interested',
                'no_answer': 'no_answer',
                'busy': 'busy',
            }
            lead.status = status_map.get(category, 'contacted')
            lead.last_contact_date = timezone.now()
            lead.save(update_fields=['status', 'last_contact_date'])

        # ── 5. Update OutboundQueue if applicable ──────────────────
        try:
            OutboundQueue.objects.filter(
                Q(call_log=call_log) | Q(lead=call_log.lead)
            ).update(
                status='completed',
                last_tried_at=timezone.now(),
            )
        except Exception:
            pass

        # ── 6. Clear agent wrapup state ────────────────────────────
        agent_status, _ = AgentStatus.objects.get_or_create(user=agent)
        # Close time log for wrapup period
        agent_status._close_time_log(ended_at=timezone.now())
        # Set status to available
        agent_status.status = 'available'
        agent_status.current_call_id = ''
        agent_status.call_start_time = None
        agent_status.wrapup_started_at = None
        agent_status.wrapup_call_id = ''
        agent_status.save()
        # Open time log for available
        agent_status._open_time_log(status='available', started_at=timezone.now())

        # ── 7. Broadcast call_cleared to agent's WS group ──────────
        _broadcast_agent_event(agent.id, 'call_cleared', {
            'call_id': call_log.id,
            'disposition': disposition.name,
        })

        return JsonResponse({
            'success': True,
            'message': f'Disposition "{disposition.name}" saved',
            'new_status': 'available',
        })

    except Exception as e:
        logger.error(f"set_disposition error: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'Failed to save disposition: {e}'})


# ==========================================================================
# HANGUP CALL
# ==========================================================================

@login_required
@agent_required
@require_POST
def hangup_call(request):
    """
    Hang up a call and move agent to wrapup (disposition required).
    The call_id is stored in wrapup_call_id so it survives page refresh.
    """
    agent = request.user
    call_id = request.POST.get('call_id')

    if not call_id:
        return JsonResponse({'success': False, 'error': 'Call ID required'})

    try:
        call_log = None
        try:
            call_log = CallLog.objects.filter(id=int(call_id), agent=agent).first()
        except (TypeError, ValueError):
            pass

        if not call_log:
            call_log = CallLog.objects.filter(
                Q(call_id=str(call_id)) | Q(channel=str(call_id)),
                agent=agent
            ).first()

        if not call_log:
            # Still put agent in wrapup so they can try to dispose
            agent_status, _ = AgentStatus.objects.get_or_create(user=agent)
            agent_status.set_status('wrapup', call_id=str(call_id))
            return JsonResponse({
                'success': False,
                'error': 'Call record not found but agent placed in wrapup',
                'wrapup': True,
            })

        # Update call log
        if call_log.call_status not in ('completed', 'hangup', 'answered'):
            call_log.call_status = 'hangup'
        call_log.end_time = timezone.now()
        if call_log.answer_time and not call_log.talk_duration:
            call_log.talk_duration = max(
                0, int((call_log.end_time - call_log.answer_time).total_seconds())
            )
        if call_log.start_time:
            call_log.total_duration = max(
                0, int((call_log.end_time - call_log.start_time).total_seconds())
            )
        call_log.save(update_fields=['call_status', 'end_time', 'talk_duration', 'total_duration'])

        # Put agent in wrapup
        agent_status, _ = AgentStatus.objects.get_or_create(user=agent)
        agent_status.set_status('wrapup', call_id=str(call_log.id))

        # Broadcast wrapup needed
        _broadcast_agent_event(agent.id, 'call_ended', {
            'call_id': call_log.id,
            'disposition_needed': True,
            'message': 'Call ended — please set disposition',
        })

        return JsonResponse({
            'success': True,
            'call_id': call_log.id,
            'wrapup': True,
            'message': 'Call ended — please set disposition',
        })

    except Exception as e:
        logger.error(f"hangup_call error: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


# ==========================================================================
# CALL STATUS
# ==========================================================================

@login_required
@agent_required
@require_http_methods(["GET"])
def get_call_status(request):
    agent = request.user
    try:
        agent_status, _ = AgentStatus.objects.get_or_create(user=agent)
        current_call = None
        call_id_to_use = agent_status.wrapup_call_id or agent_status.current_call_id

        if call_id_to_use:
            try:
                cl = CallLog.objects.filter(id=int(call_id_to_use)).first()
                if cl:
                    dur = 0
                    if cl.answer_time:
                        dur = int((timezone.now() - cl.answer_time).total_seconds())
                    current_call = {
                        'id': cl.id,
                        'number': cl.called_number,
                        'status': cl.call_status,
                        'duration': dur,
                        'lead_id': cl.lead_id,
                        'disposed': cl.disposition_id is not None,
                    }
            except (TypeError, ValueError):
                pass

        return JsonResponse({
            'success': True,
            'status': agent_status.status,
            'display': agent_status.get_status_display(),
            'current_call': current_call,
            'needs_disposition': agent_status.needs_disposition(),
            'wrapup_call_id': agent_status.wrapup_call_id,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==========================================================================
# LEAD INFO
# ==========================================================================

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
                'id': lead.id,
                'first_name': lead.first_name,
                'last_name': lead.last_name,
                'phone_number': lead.phone_number,
                'email': getattr(lead, 'email', ''),
                'company': getattr(lead, 'company', ''),
                'city': getattr(lead, 'city', ''),
                'state': getattr(lead, 'state', ''),
                'status': lead.status,
            },
            'call_history': [
                {
                    'id': c.id,
                    'date': c.start_time.strftime('%Y-%m-%d %H:%M'),
                    'status': c.call_status,
                    'duration': c.talk_duration or 0,
                    'disposition': c.disposition.name if c.disposition else '',
                }
                for c in history
            ]
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==========================================================================
# WEBRTC CONFIG
# ==========================================================================

@login_required
@agent_required
@require_http_methods(["GET"])
def get_webrtc_config(request):
    agent = request.user
    try:
        phone = _get_agent_phone(agent)
        if not phone or not getattr(phone, 'webrtc_enabled', False):
            return JsonResponse({'success': False, 'error': 'WebRTC not enabled'})
        config = _build_webrtc_config(phone, agent)
        return JsonResponse({'success': True, **config})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==========================================================================
# AGENT STATISTICS
# ==========================================================================

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

        # Time stats for today
        from users.models import AgentTimeLog
        time_summary = AgentTimeLog.get_daily_summary(agent, today)

        return JsonResponse({
            'success': True,
            'today': {
                'total_calls': tt,
                'answered_calls': ta,
                'talk_time': tc.aggregate(t=Sum('talk_duration'))['t'] or 0,
                'contact_rate': round((ta / tt * 100) if tt else 0, 1),
                'available_time': time_summary.get('available', 0),
                'busy_time': time_summary.get('busy', 0),
                'wrapup_time': time_summary.get('wrapup', 0),
                'break_time': (
                    time_summary.get('break', 0) +
                    time_summary.get('lunch', 0) +
                    time_summary.get('training', 0) +
                    time_summary.get('meeting', 0)
                ),
            },
            'week': {
                'total_calls': wt,
                'answered_calls': wa,
                'talk_time': wc.aggregate(t=Sum('talk_duration'))['t'] or 0,
                'contact_rate': round((wa / wt * 100) if wt else 0, 1),
            },
            'pending_callbacks': AgentCallbackTask.objects.filter(
                agent=agent, status__in=['pending', 'scheduled']
            ).count(),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ─────────────────────────────────────────────────────────────────────────────
# Force-logout  (supervisor / admin only)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def force_logout_agent(request):
    """
    Supervisor endpoint: forcibly log out an agent.

    Steps:
      1. Set AgentStatus → offline, record AgentTimeLog entry
      2. Expire all active Django sessions for the agent
      3. Push 'force_logout' via WebSocket → agent JS redirects to /logout/

    POST param: agent_id (int)
    Auth: must be staff/superuser or Supervisor/Manager group
    """
    from django.contrib.auth.models import User
    from django.contrib.sessions.models import Session

    user = request.user
    is_supervisor = (
        user.is_staff or user.is_superuser or
        user.groups.filter(name__in=['Supervisor', 'Manager']).exists()
    )
    if not is_supervisor:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    target_id = request.POST.get('agent_id')
    if not target_id:
        return JsonResponse({'success': False, 'error': 'agent_id required'}, status=400)

    try:
        target = User.objects.get(id=int(target_id))
    except (User.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Agent not found'}, status=404)

    now = timezone.now()

    # 1. Update AgentStatus → offline
    try:
        ag_status, _ = AgentStatus.objects.get_or_create(user=target)
        if hasattr(ag_status, '_close_time_log'):
            ag_status._close_time_log(ended_at=now)
        if hasattr(ag_status, '_open_time_log'):
            ag_status._open_time_log(status='offline', started_at=now)
        ag_status.status            = 'offline'
        ag_status.status_changed_at = now
        ag_status.current_call_id   = ''
        if hasattr(ag_status, 'wrapup_call_id'):
            ag_status.wrapup_call_id = ''
        if hasattr(ag_status, 'wrapup_started_at'):
            ag_status.wrapup_started_at = None
        if hasattr(ag_status, 'last_heartbeat'):
            ag_status.last_heartbeat = now
        ag_status.save()
    except Exception as e:
        logger.warning(f'force_logout: AgentStatus update failed for {target.username}: {e}')

    # 2. Expire active UserSession records
    try:
        from users.models import UserSession
        UserSession.objects.filter(
            user=target, is_active=True
        ).update(is_active=False, logout_time=now)
    except Exception as e:
        logger.warning(f'force_logout: UserSession cleanup failed: {e}')

    # 2b. Delete actual Django session cookies so agent can't keep using old session
    try:
        active_sessions = Session.objects.filter(expire_date__gte=now)
        for sess in active_sessions:
            try:
                data = sess.get_decoded()
                if str(data.get('_auth_user_id')) == str(target.id):
                    sess.delete()
            except Exception:
                pass
    except Exception as e:
        logger.warning(f'force_logout: Django Session deletion failed: {e}')

    # 3. Push force_logout event via WebSocket to agent's channel
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'agent_{target.id}',
                {
                    'type': 'agent_message',
                    'message': {
                        'type'    : 'force_logout',
                        'reason'  : f'Logged out by {user.get_full_name() or user.username}',
                        'agent_id': target.id,
                    },
                }
            )
    except Exception as e:
        logger.warning(f'force_logout: WebSocket push failed: {e}')

    logger.info(f'Supervisor {user.username} force-logged out agent {target.username}')
    return JsonResponse({
        'success'   : True,
        'agent_id'  : target.id,
        'agent_name': target.get_full_name() or target.username,
        'message'   : f'{target.get_full_name() or target.username} has been logged out.',
    })


# ─────────────────────────────────────────────────────────────────────────────
# Agent own-status info (seeds panel timer accurately after refresh)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@agent_required
@require_http_methods(["GET"])
def agent_status_info(request):
    """
    Return agent current status + ACCURATE Unix-ms of when current status started.

    ROOT FIX: status_changed_at has auto_now=True — it resets on EVERY .save()
    call (heartbeat every 30s, call-ID writes, wrapup saves, etc.).
    This made the timer restart on every save, not just on status changes.

    THE FIX: Use AgentTimeLog.started_at of the current OPEN log (ended_at=None).
    started_at is written ONCE when the status changes and is NEVER modified.

    Both the agent panel and admin realtime monitor use this same DB field, so
    they always show identical times and survive any page refresh.
    """
    try:
        ag  = AgentStatus.objects.get(user=request.user)
        now = timezone.now()

        from users.models import AgentTimeLog
        today = now.date()

        # ── Step 1: current open log = reliable "status started at" ────────
        current_log = (
            AgentTimeLog.objects
            .filter(user=request.user, date=today, ended_at__isnull=True)
            .order_by('-started_at')
            .first()
        )

        changed_ms  = None
        status_secs = 0

        if current_log:
            # RELIABLE: written once on status change, never touched again
            changed_ms  = int(current_log.started_at.timestamp() * 1000)
            status_secs = max(0, int((now - current_log.started_at).total_seconds()))
        elif ag.status_changed_at:
            # Fallback only — open log missing (edge case on first login)
            changed_ms  = int(ag.status_changed_at.timestamp() * 1000)
            status_secs = max(0, int((now - ag.status_changed_at).total_seconds()))

        # ── Step 2: login time = all non-offline logs today ─────────────────
        all_logs = (
            AgentTimeLog.objects
            .filter(user=request.user, date=today)
            .exclude(status='offline')
            .order_by('started_at')
        )

        login_ms   = None
        login_secs = 0

        for log in all_logs:
            if login_ms is None and log.started_at:
                login_ms = int(log.started_at.timestamp() * 1000)
            if log.ended_at:
                login_secs += log.duration_seconds or int(
                    (log.ended_at - log.started_at).total_seconds()
                )
            else:
                login_secs += max(0, int((now - log.started_at).total_seconds()))

        return JsonResponse({
            'success'              : True,
            'status'               : ag.status,
            'status_display'       : ag.get_status_display(),
            # Seed frontend timers from these — do NOT use a client-side counter:
            'status_changed_at_ms' : changed_ms,   # Unix ms — start of current status
            'status_time_secs'     : status_secs,   # pre-calculated (for initial render)
            'login_at_ms'          : login_ms,      # Unix ms — first login today
            'login_time_secs'      : login_secs,    # total seconds logged in today
            # Clock sync: client skew = server_time_ms - Date.now()
            'server_time_ms'       : int(now.timestamp() * 1000),
            'needs_disposition'    : ag.needs_disposition() if hasattr(ag, 'needs_disposition') else False,
        })
    except AgentStatus.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'No status record'})
    except Exception as e:
        logger.exception('agent_status_info error')
        return JsonResponse({'success': False, 'error': str(e)})
