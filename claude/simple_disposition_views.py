# Simple Disposition Views - Add these to your agents/views_simple.py

import json
import logging
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from core.decorators import agent_required

logger = logging.getLogger(__name__)

@login_required
@agent_required
@require_http_methods(["POST"])
@csrf_exempt
def submit_disposition(request):
    """
    Simple disposition submission for your existing workflow
    Keeps your UI design, just fixes the backend logic
    """
    try:
        data = json.loads(request.body)
        call_id = data.get('call_id')
        disposition_id = data.get('disposition_id')
        notes = data.get('notes', '')
        
        if not call_id or not disposition_id:
            return JsonResponse({
                'success': False,
                'error': 'Call ID and disposition required'
            })
        
        from telephony.models import CallLog
        from campaigns.models import Disposition
        
        # Get call log
        call_log = CallLog.objects.filter(
            id=call_id,
            agent=request.user
        ).first()
        
        if not call_log:
            return JsonResponse({
                'success': False,
                'error': 'Call not found or not assigned to you'
            })
            
        # Check if already dispositioned
        if call_log.disposition:
            return JsonResponse({
                'success': False,
                'error': 'Call already dispositioned'
            })
            
        # Get disposition
        disposition = Disposition.objects.filter(id=disposition_id).first()
        if not disposition:
            return JsonResponse({
                'success': False,
                'error': 'Invalid disposition'
            })
        
        # Update call log
        call_log.disposition = disposition
        call_log.disposition_time = timezone.now()
        call_log.agent_notes = notes
        call_log.call_status = 'dispositioned'
        call_log.save()
        
        # Update lead if exists
        if call_log.lead_id:
            from leads.models import Lead
            lead = Lead.objects.filter(id=call_log.lead_id).first()
            if lead:
                if disposition.is_sale:
                    lead.status = 'sale'
                elif disposition.schedule_callback:
                    lead.status = 'callback' 
                else:
                    lead.status = disposition.category
                lead.last_contact_date = timezone.now()
                lead.save()
        
        # Update agent to available if auto_available
        if disposition.auto_available:
            from users.models import AgentStatus
            from agents.models import AgentDialerSession
            
            # Update agent status
            AgentStatus.objects.filter(user=request.user).update(
                status='available'
            )
            
            # Update dialer session back to ready
            AgentDialerSession.objects.filter(
                agent=request.user,
                status='on_call'
            ).update(
                status='ready',
                current_call_channel_id=None
            )
        
        logger.info(f"Disposition '{disposition.name}' submitted for call {call_id} by {request.user.username}")
        
        return JsonResponse({
            'success': True,
            'message': f'Disposition "{disposition.name}" submitted successfully',
            'disposition': disposition.name,
            'auto_available': disposition.auto_available
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        })
    except Exception as e:
        logger.error(f"Disposition error: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })

@login_required 
@agent_required
@require_http_methods(["GET"])
def get_dispositions(request):
    """
    Get available dispositions for current campaign
    Works with your existing UI elements
    """
    try:
        from campaigns.models import Disposition
        from agents.models import AgentDialerSession
        
        # Try to get campaign-specific dispositions first
        agent_session = AgentDialerSession.objects.filter(
            agent=request.user,
            status__in=['ready', 'on_call']
        ).first()
        
        if agent_session and agent_session.campaign:
            # Get dispositions for current campaign
            dispositions = Disposition.objects.filter(
                campaigns=agent_session.campaign,
                is_active=True
            ).order_by('sort_order', 'name')
        else:
            # Get general dispositions
            dispositions = Disposition.objects.filter(
                is_active=True
            ).order_by('sort_order', 'name')
        
        disposition_data = []
        for disp in dispositions:
            disposition_data.append({
                'id': disp.id,
                'name': disp.name,
                'category': disp.category,
                'description': disp.description or '',
                'is_sale': disp.is_sale,
                'schedule_callback': disp.schedule_callback,
                'auto_available': disp.auto_available,
                'color': disp.color or '#6c757d',
                'hotkey': disp.hotkey
            })
        
        return JsonResponse({
            'success': True,
            'dispositions': disposition_data,
            'campaign': agent_session.campaign.name if agent_session and agent_session.campaign else None
        })
        
    except Exception as e:
        logger.error(f"Get dispositions error: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })

@login_required
@agent_required  
@require_http_methods(["GET"])
def get_agent_status(request):
    """
    Get current agent status and session info
    For your existing workflow checks
    """
    try:
        from users.models import AgentStatus
        from agents.models import AgentDialerSession
        from telephony.models import CallLog
        
        # Get agent status
        agent_status = AgentStatus.objects.filter(user=request.user).first()
        
        # Get current session
        session = AgentDialerSession.objects.filter(
            agent=request.user,
            status__in=['connecting', 'ready', 'on_call']
        ).first()
        
        # Get active call
        active_call = None
        if session and session.current_call_channel_id:
            call_log = CallLog.objects.filter(
                channel=session.current_call_channel_id,
                agent=request.user,
                end_time__isnull=True
            ).first()
            
            if call_log:
                active_call = {
                    'id': call_log.id,
                    'channel_id': call_log.channel,
                    'number': call_log.called_number,
                    'status': call_log.call_status,
                    'start_time': call_log.start_time.isoformat() if call_log.start_time else None
                }
        
        return JsonResponse({
            'success': True,
            'agent_status': agent_status.status if agent_status else 'offline',
            'session_status': session.status if session else None,
            'current_campaign': session.campaign.name if session and session.campaign else None,
            'current_call': active_call,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting agent status: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

# Also update your existing update_status view to handle session properly:

@login_required
@agent_required
@require_http_methods(["POST"])
@csrf_exempt 
def update_agent_status_fixed(request):
    """
    Enhanced status update that properly handles your AgentDialerSession workflow
    """
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
        
        if not new_status:
            return JsonResponse({
                'success': False,
                'error': 'Status is required'
            })
        
        agent = request.user
        from users.models import AgentStatus
        from agents.models import AgentDialerSession
        from agents.telephony_service import AgentTelephonyService
        from campaigns.models import Campaign
        
        # Update or create agent status
        agent_status, created = AgentStatus.objects.get_or_create(
            user=agent,
            defaults={'status': new_status}
        )
        
        old_status = agent_status.status
        agent_status.status = new_status
        agent_status.status_changed_at = timezone.now()
        agent_status.save()
        
        # Handle telephony status changes according to YOUR workflow
        telephony_service = AgentTelephonyService(agent)
        
        # Map your UI statuses to your backend logic
        mapped_status = {
            'available': 'available',
            'break': 'break', 
            'lunch': 'lunch',
            'training': 'training',
            'meeting': 'meeting',
            'offline': 'offline'
        }.get(new_status, new_status)
        
        if mapped_status == 'available':
            # Make agent ready for calls (YOUR workflow)
            # Find campaign for session binding
            campaign = agent_status.current_campaign
            if not campaign:
                campaign = Campaign.objects.filter(
                    assigned_users=agent,
                    status='active'
                ).first()
                if campaign:
                    agent_status.current_campaign = campaign
                    agent_status.save(update_fields=['current_campaign'])
            
            if campaign:
                # Check if already has session
                existing_session = AgentDialerSession.objects.filter(
                    agent=agent,
                    status__in=['connecting', 'ready']
                ).first()
                
                if not existing_session:
                    # Create new session (YOUR login_campaign flow)
                    result = telephony_service.login_campaign(campaign.id)
                    if not result.get('success'):
                        logger.warning(f"Failed to login {agent.username} to campaign")
                        
        elif mapped_status in ['break', 'lunch', 'training', 'meeting', 'offline']:
            # Logout agent from session (YOUR workflow)
            telephony_service.logout_session()
        
        # Broadcast status update to agent websocket (YOUR approach)
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"agent_{agent.id}",
                {
                    'type': 'call_event',
                    'data': {
                        'type': 'status_update',
                        'old_status': old_status,
                        'new_status': mapped_status,
                        'message': f'Status updated to {mapped_status}',
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
        except Exception:
            pass
        
        return JsonResponse({
            'success': True,
            'old_status': old_status,
            'new_status': mapped_status,
            'message': f'Status updated to {mapped_status}',
            'timestamp': agent_status.status_changed_at.isoformat()
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        })
    except Exception as e:
        logger.error(f"Error updating status for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })
