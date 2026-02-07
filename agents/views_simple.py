"""
Agent Views (Simple Dashboard) - IMPROVED with Phase 1 Fixes

Phase 1 Fixes Applied:
- 1.2: Broadcast call_cleared event after disposition
- 1.3: Force hangup and cleanup after disposition
"""

import json
import logging
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
from campaigns.models import Campaign, Disposition, OutboundQueue
from leads.models import Lead
from users.models import AgentStatus
from telephony.models import Phone, AsteriskServer
from telephony.services import AsteriskService

logger = logging.getLogger(__name__)


def _get_dashboard_context(request, agent, agent_status, phone):
    """Helper to build consistent dashboard context"""
    from campaigns.models import Campaign, Disposition
    from agents.models import AgentCallbackTask
    from agents.telephony_service import AgentTelephonyService
    
    # Get assigned campaigns
    assigned_campaigns = Campaign.objects.filter(
        assigned_users=agent,
        status='active'
    )
    
    # Get current campaign
    current_campaign = agent_status.current_campaign
    if not current_campaign and assigned_campaigns.exists():
        current_campaign = assigned_campaigns.first()
        
    # Get phone info
    phone_info = {
        'extension': phone.extension if phone else None,
        'is_active': phone.is_active if phone else False,
        'webrtc_enabled': getattr(phone, 'webrtc_enabled', False) if phone else False,
        'registered': False
    }
    
    if phone:
        telephony_service = AgentTelephonyService(agent)
        try:
            phone_info['registered'] = telephony_service.is_extension_registered()
        except:
            phone_info['registered'] = False
            
    # Get available dispositions
    available_dispositions = Disposition.objects.filter(is_active=True)
    if current_campaign:
        campaign_dispositions = current_campaign.dispositions.filter(is_active=True).select_related('disposition')
        if campaign_dispositions.exists():
            # Get the actual Disposition IDs from CampaignDisposition objects
            disposition_ids = [cd.disposition_id for cd in campaign_dispositions]
            available_dispositions = Disposition.objects.filter(
                id__in=disposition_ids,
                is_active=True
            ).order_by('name')
            
    # Get script content
    script_content = ""
    if current_campaign and hasattr(current_campaign, 'script') and current_campaign.script:
        script_content = current_campaign.script.content

    # Get pending callbacks
    pending_callbacks = AgentCallbackTask.objects.filter(
        agent=agent,
        status__in=['pending', 'scheduled']
    ).order_by('scheduled_time')[:5]
    
    # Get other agents for transfer
    other_agents = AgentStatus.objects.filter(
        status='available'
    ).exclude(user=agent).select_related('user')[:10]
        
    return {
        'agent': agent,
        'agent_status': agent_status,
        'assigned_campaigns': assigned_campaigns,
        'current_campaign': current_campaign,
        'phone_info': phone_info,
        'available_dispositions': list(available_dispositions.values('id', 'name', 'code', 'category')),
        'transfer_targets': [
             {'name': a.user.username, 'extension': a.extension} 
             for a in other_agents if hasattr(a, 'extension') and a.extension
        ],
        'script_content': script_content,
        'pending_callbacks': pending_callbacks,
        'other_agents': other_agents,
        'call_status_url': '/agents/api/call-status/',
        'lead_info_url': '/agents/api/lead-info/',
        'disposition_url': '/agents/api/set-disposition/',
        'manual_dial_url': '/agents/api/manual-dial/',
        'hangup_url': '/agents/api/hangup/',
        'transfer_call_url': '/agents/api/transfer/',
    }

@login_required
@agent_required
def simple_dashboard(request):
    """
    Main agent dashboard view
    Routes to WebRTC or standard interface based on phone configuration
    """
    agent = request.user
    agent_status, _ = AgentStatus.objects.get_or_create(user=agent)
    phone = Phone.objects.filter(user=agent, is_active=True).first()
    
    # Calculate context immediately
    context = _get_dashboard_context(request, agent, agent_status, phone)
    
    # Phase 3.1: Route to WebRTC Dashboard if enabled
    if phone and getattr(phone, 'webrtc_enabled', False):
        from django.conf import settings
        
        webrtc_config = {
            'ws_server': settings.WEBRTC_CONFIG['ws_server'],
            'sip_uri': f'sip:{phone.extension}@{settings.WEBRTC_CONFIG["domain"]}',
            'password': getattr(phone, 'sip_password', phone.secret),
            'displayName': agent.get_full_name() or agent.username,
            'debug': settings.WEBRTC_CONFIG.get('debug', False),
            'extension': phone.extension,
        }
        context['webrtc_config'] = webrtc_config
        return render(request, 'agents/webrtc_dashboard.html', context)
    
    return render(request, 'agents/simple_dashboard.html', context)
    
    return render(request, 'agents/simple_dashboard.html', context)


@login_required
@agent_required
@require_POST
def update_status(request):
    """
    Update agent status
    """
    agent = request.user
    new_status = request.POST.get('status', '').strip().lower()
    
    if not new_status:
        return JsonResponse({
            'success': False,
            'error': 'Status is required'
        })
    
    # Map frontend status to backend
    status_map = {
        'available': 'available',
        'ready': 'available',
        'break': 'break',
        'lunch': 'lunch',
        'meeting': 'meeting',
        'training': 'training',
        'offline': 'offline',
        'busy': 'busy',
        'wrapup': 'wrapup'
    }
    
    mapped_status = status_map.get(new_status, new_status)
    
    try:
        agent_status, _ = AgentStatus.objects.get_or_create(user=agent)
        
        # Get campaign and telephony service
        campaign = agent_status.current_campaign
        if not campaign:
            campaign = Campaign.objects.filter(assigned_users=agent, status='active').first()
        
        telephony_service = AgentTelephonyService(agent)
        
        # Handle status-specific logic
        if mapped_status == 'available':
            # Login to campaign if WebRTC enabled
            if campaign and telephony_service.agent_phone and telephony_service.agent_phone.webrtc_enabled:
                existing_session = AgentDialerSession.objects.filter(
                    agent=agent,
                    status__in=['connecting', 'ready']
                ).first()
                
                if not existing_session:
                    result = telephony_service.login_campaign(campaign.id)
                    if not result.get('success'):
                        agent_status.set_status('offline')
                        return JsonResponse({
                            'success': False,
                            'error': result.get('error', 'Softphone not registered')
                        })
        
        elif mapped_status in ['break', 'lunch', 'training', 'meeting', 'system_issues', 'offline']:
            # Disconnect agent leg when unavailable
            telephony_service.logout_session()
        
        # Update status
        agent_status.set_status(mapped_status)
        
        # Broadcast status update
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"agent_{agent.id}",
                {
                    'type': 'call_event',
                    'data': {
                        'type': 'status_update',
                        'status': mapped_status,
                        'message': f'Status updated to {mapped_status}'
                    }
                }
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast status update: {e}")
        
        return JsonResponse({
            'success': True,
            'status': mapped_status,
            'message': f'Status updated to {mapped_status}'
        })
        
    except Exception as e:
        logger.error(f"Error updating status for {agent.username}: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to update status'
        })


@login_required
@agent_required
@require_POST
def set_disposition(request):
    """
    Set call disposition
    
    PHASE 1.2 FIX: Broadcast call_cleared event after disposition
    PHASE 1.3 FIX: Force hangup and cleanup agent session
    """
    agent = request.user
    call_id = request.POST.get('call_id')
    disposition_id = request.POST.get('disposition_id')
    notes = request.POST.get('notes', '').strip()
    
    if not call_id or not disposition_id:
        return JsonResponse({
            'success': False,
            'error': 'Call ID and disposition are required'
        })
    
    try:
        logger.info(f"Setting disposition - Agent: {agent.username}, Call ID: {call_id}, Disposition ID: {disposition_id}")
        
        # Find call log - try multiple methods
        call_log = None
        
        # Method 1: Try as primary key (integer ID)
        try:
            call_pk = int(call_id)
            call_log = CallLog.objects.filter(id=call_pk, agent=agent).first()
            if call_log:
                logger.info(f"Found call by primary key: {call_pk}")
        except (TypeError, ValueError):
            pass
        
        # Method 2: Try as call_id UUID field
        if not call_log:
            call_log = CallLog.objects.filter(call_id=call_id, agent=agent).first()
            if call_log:
                logger.info(f"Found call by call_id UUID: {call_id}")
        
        # Method 3: Try as channel, uniqueid, or other identifiers
        if not call_log:
            call_log = CallLog.objects.filter(
                Q(channel=call_id) | Q(uniqueid=call_id),
                agent=agent
            ).first()
            if call_log:
                logger.info(f"Found call by channel/uniqueid: {call_id}")
        
        # Method 4: Try without agent filter (in case agent wasn't set properly)
        if not call_log:
            try:
                call_pk = int(call_id)
                call_log = CallLog.objects.filter(id=call_pk).first()
                if call_log:
                    # Verify it's for this agent or update it
                    if not call_log.agent:
                        call_log.agent = agent
                        call_log.save(update_fields=['agent'])
                        logger.info(f"Found call without agent, assigned to {agent.username}")
                    elif call_log.agent == agent:
                        logger.info(f"Found call by primary key without agent filter: {call_pk}")
                    else:
                        call_log = None  # Don't allow setting disposition for other agent's calls
            except (TypeError, ValueError):
                pass
        
        # Method 5: Try call_id UUID without agent filter
        if not call_log:
            call_log = CallLog.objects.filter(call_id=call_id).first()
            if call_log:
                # Verify it's for this agent or update it
                if not call_log.agent:
                    call_log.agent = agent
                    call_log.save(update_fields=['agent'])
                    logger.info(f"Found call by UUID without agent, assigned to {agent.username}")
                elif call_log.agent == agent:
                    logger.info(f"Found call by UUID without agent filter: {call_id}")
                else:
                    call_log = None  # Don't allow setting disposition for other agent's calls
        
        # Get disposition
        disposition = Disposition.objects.filter(id=disposition_id).first()
        
        if not call_log:
            logger.error(f"Call not found - Agent: {agent.username}, Call ID: {call_id}, Disposition ID: {disposition_id}")
            # Log recent calls for this agent for debugging
            recent_calls = CallLog.objects.filter(agent=agent).order_by('-start_time')[:5]
            logger.error(f"Recent calls for agent: {[(c.id, c.call_id, c.called_number) for c in recent_calls]}")
            return JsonResponse({
                'success': False,
                'error': f'Call not found. Call ID: {call_id}. Please ensure the call is associated with your account.'
            })
        
        if not disposition:
            return JsonResponse({
                'success': False,
                'error': 'Disposition not found'
            })
        
        # Update call log with disposition
        call_log.disposition = disposition
        call_log.disposition_notes = notes
        call_log.save(update_fields=['disposition', 'disposition_notes'])
        
        # Update lead status based on disposition
        if call_log.lead:
            lead = call_log.lead
            if disposition.category == 'sale':
                lead.status = 'sale'
            elif disposition.category == 'callback':
                lead.status = 'callback'
            elif disposition.category == 'dnc':
                lead.status = 'dnc'
            elif disposition.category == 'not_interested':
                lead.status = 'not_interested'
            elif disposition.category in ['no_answer', 'busy']:
                lead.status = disposition.category
            else:
                lead.status = 'contacted'
            
            lead.last_contact_date = timezone.now()
            lead.save(update_fields=['status', 'last_contact_date'])
        
        # Update outbound queue if applicable
        try:
            OutboundQueue.objects.filter(id=call_log.id).update(
                status='completed',
                last_tried_at=timezone.now(),
                disposition=disposition.code
            )
        except Exception:
            pass
        
        # PHASE 1.3 FIX: Force hangup any active channels
        _force_cleanup_call(agent, call_log)
        
        # Update agent status
        agent_status = getattr(agent, 'agent_status', None)
        if agent_status:
            if disposition.auto_available if hasattr(disposition, 'auto_available') else True:
                agent_status.set_status('available')
                agent_status.current_call_id = ''
                agent_status.call_start_time = None
                agent_status.save()
            else:
                agent_status.set_status('wrapup')
        
        # PHASE 1.2 FIX: Broadcast call_cleared event to wipe UI
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"agent_{agent.id}",
                {
                    'type': 'call_event',
                    'data': {
                        'type': 'call_cleared',  # NEW event type
                        'call_id': call_log.id,
                        'disposition': disposition.name,
                        'clear_ui': True,  # Signal to clear all call data from UI
                        'message': f'Call dispositioned as {disposition.name}'
                    }
                }
            )
            
            # Also send status update
            async_to_sync(channel_layer.group_send)(
                f"agent_{agent.id}",
                {
                    'type': 'call_event',
                    'data': {
                        'type': 'status_update',
                        'status': 'available',
                        'message': 'Ready for next call'
                    }
                }
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast call_cleared: {e}")
        
        logger.info(f"Disposition set for call {call_log.id}: {disposition.name}")
        
        return JsonResponse({
            'success': True,
            'disposition': disposition.name,
            'call_id': call_log.id,
            'message': f'Call dispositioned as {disposition.name}'
        })
        
    except Exception as e:
        logger.error(f"Error setting disposition: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to set disposition'
        })


def _force_cleanup_call(agent, call_log):
    """
    PHASE 1.3: Force cleanup of call and agent session
    Ensures softphone doesn't show stale call
    """
    logger.info(f"CLEANUP: Starting force cleanup for agent {agent.username}, call {call_log.id if call_log else 'None'}")
    try:
        # Get Asterisk server
        server = AsteriskServer.objects.filter(is_active=True).first()
        if not server:
            return
        
        asterisk_service = AsteriskService(server)
        
        # Find and destroy any active bridges for this call
        try:
            import requests
            ari_base_url = f"http://{server.ari_host}:{server.ari_port}/ari"
            
            # Get all bridges
            response = requests.get(
                f"{ari_base_url}/bridges",
                auth=(server.ari_username, server.ari_password),
                timeout=5
            )
            
            if response.status_code == 200:
                bridges = response.json()
                for bridge in bridges:
                    bridge_id = bridge.get('id')
                    channels = bridge.get('channels', [])
                    
                    # If this bridge contains our call channel, destroy it
                    if call_log.channel in channels:
                        logger.info(f"Destroying bridge {bridge_id} containing channel {call_log.channel}")
                        asterisk_service.destroy_bridge(bridge_id)
                        
                        # Hangup all channels in the bridge
                        for channel_id in channels:
                            try:
                                asterisk_service.hangup_channel(channel_id)
                                logger.info(f"Hung up channel {channel_id}")
                            except Exception as e:
                                logger.debug(f"Channel {channel_id} already hung up: {e}")
        except Exception as e:
            logger.error(f"Error destroying bridges: {e}")
        
        # Hangup any active channels associated with this call (fallback)
        if call_log.channel:
            try:
                asterisk_service.hangup_channel(call_log.channel)
            except Exception as e:
                logger.debug(f"Channel {call_log.channel} already hung up: {e}")
        
        if call_log.uniqueid and call_log.uniqueid != call_log.channel:
            try:
                asterisk_service.hangup_channel(call_log.uniqueid)
            except Exception:
                pass
        
        # Clean up agent dialer session
        sessions = AgentDialerSession.objects.filter(agent=agent)
        for session in sessions:
            # Destroy bridge if exists
            if session.agent_bridge_id:
                try:
                    asterisk_service.destroy_bridge(session.agent_bridge_id)
                except Exception:
                    pass
            
            # Hangup agent channel to disconnect softphone
            if session.agent_channel_id:
                try:
                    asterisk_service.hangup_channel(session.agent_channel_id)
                    logger.info(f"Hung up agent channel {session.agent_channel_id}")
                except Exception:
                    pass
        
        # Reset session state (but keep session for next call)
        AgentDialerSession.objects.filter(
            agent=agent,
            status__in=['busy', 'wrapup']
        ).update(status='ready')
        
        logger.info(f"Cleaned up call for agent {agent.username}")
        
    except Exception as e:
        logger.error(f"Error in force cleanup: {e}")


@login_required
@agent_required
@require_POST
def hangup_call(request):
    """
    Hangup current call
    
    PHASE 1.3 FIX: Ensure proper cleanup
    """
    agent = request.user
    call_id = request.POST.get('call_id')
    
    if not call_id:
        return JsonResponse({
            'success': False,
            'error': 'Call ID required'
        })
    
    try:
        # Find call
        call_log = None
        try:
            call_pk = int(call_id)
            call_log = CallLog.objects.filter(id=call_pk, agent=agent).first()
        except (TypeError, ValueError):
            pass
        
        if not call_log:
            call_log = CallLog.objects.filter(
                Q(channel=call_id) | Q(uniqueid=call_id),
                agent=agent
            ).first()
        
        if not call_log:
            return JsonResponse({
                'success': False,
                'error': 'Call not found'
            })
        
        # Update call log
        call_log.call_status = 'hangup'
        call_log.end_time = timezone.now()
        
        if call_log.answer_time:
            call_log.talk_duration = int(
                (call_log.end_time - call_log.answer_time).total_seconds()
            )
        
        if call_log.start_time:
            call_log.total_duration = int(
                (call_log.end_time - call_log.start_time).total_seconds()
            )
        
        call_log.save()
        
        # Force cleanup
        _force_cleanup_call(agent, call_log)
        
        # Update agent status to wrapup (needs disposition)
        agent_status = getattr(agent, 'agent_status', None)
        if agent_status:
            agent_status.set_status('wrapup')
            agent_status.current_call_id = str(call_log.id)  # Keep for disposition
        
        # Broadcast
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"agent_{agent.id}",
                {
                    'type': 'call_event',
                    'data': {
                        'type': 'call_ended',
                        'call_id': call_log.id,
                        'disposition_needed': True,
                        'message': 'Call ended - Please select disposition'
                    }
                }
            )
        except Exception:
            pass
        
        return JsonResponse({
            'success': True,
            'call_id': call_log.id,
            'message': 'Call ended'
        })
        
    except Exception as e:
        logger.error(f"Error hanging up call: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to hangup call'
        })


@login_required
@agent_required
@require_http_methods(["GET"])
def get_lead_info(request):
    """
    Get lead information for screen pop
    """
    lead_id = request.GET.get('lead_id')
    
    if not lead_id:
        return JsonResponse({
            'success': False,
            'error': 'Lead ID required'
        })
    
    try:
        lead = Lead.objects.filter(id=lead_id).first()
        
        if not lead:
            return JsonResponse({
                'success': False,
                'error': 'Lead not found'
            })
        
        # Get call history for this lead
        call_history = CallLog.objects.filter(lead=lead).order_by('-start_time')[:5]
        
        return JsonResponse({
            'success': True,
            'lead': {
                'id': lead.id,
                'first_name': lead.first_name,
                'last_name': lead.last_name,
                'phone': lead.phone_number,
                'email': lead.email or '',
                'company': lead.company or '',
                'address': lead.address or '',
                'city': lead.city or '',
                'state': lead.state or '',
                'zip_code': lead.zip_code or '',
                'status': lead.status,
                'call_count': lead.call_count,
                'notes': lead.notes or '',
                'created_at': lead.created_at.isoformat() if lead.created_at else None,
                'last_contact_date': lead.last_contact_date.isoformat() if lead.last_contact_date else None
            },
            'call_history': [
                {
                    'id': call.id,
                    'date': call.start_time.isoformat() if call.start_time else None,
                    'duration': call.talk_duration or 0,
                    'disposition': call.disposition.name if call.disposition else 'N/A',
                    'agent': call.agent.username if call.agent else 'N/A'
                }
                for call in call_history
            ]
        })
        
    except Exception as e:
        logger.error(f"Error getting lead info: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve lead information'
        })


@login_required
@agent_required
@require_http_methods(["GET"])
def get_call_status(request):
    """
    Get current call status for agent
    """
    agent = request.user
    
    try:
        agent_status = getattr(agent, 'agent_status', None)
        
        current_call = None
        if agent_status and agent_status.current_call_id:
            try:
                call_id = int(agent_status.current_call_id)
                call_log = CallLog.objects.filter(id=call_id).first()
                if call_log:
                    duration = 0
                    if call_log.answer_time:
                        duration = int((timezone.now() - call_log.answer_time).total_seconds())
                    
                    current_call = {
                        'id': call_log.id,
                        'number': call_log.called_number,
                        'status': call_log.call_status,
                        'duration': duration,
                        'lead_id': call_log.lead_id
                    }
            except (TypeError, ValueError):
                pass
        
        return JsonResponse({
            'success': True,
            'status': agent_status.status if agent_status else 'offline',
            'current_call': current_call
        })
        
    except Exception as e:
        logger.error(f"Error getting call status: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get call status'
        })


@login_required
@agent_required
@require_http_methods(["GET"])
def get_webrtc_config(request):
    """
    Get WebRTC configuration for agent's phone
    """
    agent = request.user
    
    try:
        phone = Phone.objects.filter(user=agent, is_active=True).first()
        
        if not phone or not phone.webrtc_enabled:
            return JsonResponse({
                'success': False,
                'error': 'WebRTC not enabled for this phone'
            })
        
        server = phone.asterisk_server
        
        return JsonResponse({
            'success': True,
            'config': {
                'extension': phone.extension,
                'secret': phone.secret,
                'domain': server.server_ip if server else 'localhost',
                'ws_server': f"wss://{server.server_ip}:8089/ws" if server else None,
                'stun_server': phone.ice_host or 'stun:stun.l.google.com:19302',
                'codecs': phone.codec.split(',') if phone.codec else ['ulaw', 'alaw']
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting WebRTC config: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get WebRTC configuration'
        })


@login_required
@agent_required
@require_http_methods(["GET"])
def agent_statistics(request):
    """
    Get agent statistics
    """
    agent = request.user
    
    try:
        today = timezone.now().date()
        
        # Today's calls
        today_calls = CallLog.objects.filter(agent=agent, start_time__date=today)
        
        # Week's calls
        week_start = today - timedelta(days=today.weekday())
        week_calls = CallLog.objects.filter(
            agent=agent,
            start_time__date__gte=week_start
        )
        
        # Calculate stats
        today_total = today_calls.count()
        today_answered = today_calls.filter(call_status='answered').count()
        today_talk_time = today_calls.aggregate(total=Sum('talk_duration'))['total'] or 0
        
        week_total = week_calls.count()
        week_answered = week_calls.filter(call_status='answered').count()
        week_talk_time = week_calls.aggregate(total=Sum('talk_duration'))['total'] or 0
        
        # Pending callbacks
        pending_callbacks = AgentCallbackTask.objects.filter(
            agent=agent,
            status__in=['pending', 'scheduled']
        ).count()
        
        return JsonResponse({
            'success': True,
            'today': {
                'total_calls': today_total,
                'answered_calls': today_answered,
                'talk_time': today_talk_time,
                'contact_rate': round((today_answered / today_total * 100) if today_total > 0 else 0, 1)
            },
            'week': {
                'total_calls': week_total,
                'answered_calls': week_answered,
                'talk_time': week_talk_time,
                'contact_rate': round((week_answered / week_total * 100) if week_total > 0 else 0, 1)
            },
            'pending_callbacks': pending_callbacks
        })
        
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get statistics'
        })


@login_required
@agent_required
@require_http_methods(["GET"])
def agent_call_history(request):
    """
    PHASE 2.2: Get agent's call history
    """
    agent = request.user
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 25))
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    disposition_filter = request.GET.get('disposition')
    
    try:
        calls = CallLog.objects.filter(agent=agent).select_related(
            'lead', 'disposition', 'campaign'
        ).order_by('-start_time')
        
        # Apply filters
        if date_from:
            calls = calls.filter(start_time__date__gte=date_from)
        if date_to:
            calls = calls.filter(start_time__date__lte=date_to)
        if disposition_filter:
            calls = calls.filter(disposition_id=disposition_filter)
        
        # Paginate
        total = calls.count()
        offset = (page - 1) * per_page
        calls = calls[offset:offset + per_page]
        
        return JsonResponse({
            'success': True,
            'calls': [
                {
                    'id': call.id,
                    'date': call.start_time.isoformat() if call.start_time else None,
                    'number': call.called_number,
                    'lead_name': f"{call.lead.first_name} {call.lead.last_name}" if call.lead else 'Unknown',
                    'lead_id': call.lead_id,
                    'duration': call.talk_duration or 0,
                    'disposition': call.disposition.name if call.disposition else 'N/A',
                    'campaign': call.campaign.name if call.campaign else 'N/A',
                    'recording_available': bool(call.recording_file)
                }
                for call in calls
            ],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting call history: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get call history'
        })
