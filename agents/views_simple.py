# agents/views_simple.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta
import json
import logging

from .models import AgentCallbackTask, AgentScript, AgentQueue
from .telephony_service import AgentTelephonyService
from campaigns.models import Campaign, Disposition
from leads.models import Lead
from calls.models import CallLog
from users.models import AgentStatus
from core.decorators import agent_required

logger = logging.getLogger(__name__)


@login_required
@agent_required
def agent_dashboard(request):
    """
    Enhanced agent dashboard with telephony integration
    """
    agent = request.user
    
    try:
        # Get agent's current status
        agent_status, created = AgentStatus.objects.get_or_create(user=agent)
        
        # Get pending callbacks for this agent
        pending_callbacks = AgentCallbackTask.objects.filter(
            agent=agent,
            status__in=['pending', 'scheduled'],
            scheduled_time__lte=timezone.now() + timedelta(hours=24)
        ).select_related('lead', 'campaign').order_by('scheduled_time')[:10]
        
        # Get default script content
        default_script = AgentScript.objects.filter(
            is_global=True,
            script_type='opening',
            is_active=True
        ).first()
        
        script_content = default_script.content if default_script else "Hello, this is [Agent Name] calling from [Company]. How are you today?"
        
        # Get agent's telephony info
        telephony_service = AgentTelephonyService(agent)
        webrtc_config = telephony_service.get_webrtc_config()
        call_status = telephony_service.get_agent_call_status()
        
        # Get agent's assigned campaigns
        assigned_campaigns = Campaign.objects.filter(
            assigned_users=agent,
            status='active',
            campaignagent__is_active=True
        ).distinct()
        
        context = {
            'agent': agent,
            'agent_status': agent_status,
            'pending_callbacks': pending_callbacks,
            'script_content': script_content,
            'webrtc_config': json.dumps(webrtc_config) if webrtc_config else '{}',
            'call_status': call_status,
            'assigned_campaigns': assigned_campaigns,
            'dialer_session': None,
        }
        
        return render(request, 'agents/simple_dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error in agent dashboard: {str(e)}")
        messages.error(request, 'Error loading dashboard. Please try again.')
        return render(request, 'agents/simple_dashboard.html', {
            'agent': agent,
            'webrtc_config': '{}',
            'assigned_campaigns': [],
            'pending_callbacks': [],
            'script_content': ''
        })


# Removed persistent session flow and push_call to simplify UX


@login_required
@agent_required
@require_POST
def manual_dial(request):
    """Manual dial: originate customer only when the agent requests, then auto-bridge to agent."""
    agent = request.user
    number = request.POST.get('phone_number', '').strip()
    campaign_id = request.POST.get('campaign_id')
    if not number:
        return JsonResponse({'success': False, 'error': 'phone_number required'}, status=400)
    # Enqueue a one-off queue item and process immediately for this agent
    try:
        from campaigns.models import OutboundQueue, Campaign
        from campaigns.tasks import process_outbound_queue_item
        campaign = Campaign.objects.filter(id=campaign_id).first() if campaign_id else None
        if not campaign:
            # Fallback: use any active campaign assigned to agent
            campaign = Campaign.objects.filter(assigned_users=agent, status='active').first()
        if not campaign:
            return JsonResponse({'success': False, 'error': 'No campaign available'}, status=400)
        q = OutboundQueue.objects.create(campaign=campaign, phone_number=number)
        process_outbound_queue_item.delay(q.id)
        return JsonResponse({'success': True, 'queue_id': q.id, 'message': 'Dial requested'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@agent_required
@require_POST
def register_phone(request):
    """
    Register agent's WebRTC phone
    """
    agent = request.user
    
    try:
        telephony_service = AgentTelephonyService(agent)
        result = telephony_service.register_webrtc_phone()
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error registering phone for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Phone registration failed. Please try again.'
        })


@login_required
@agent_required
@require_POST
def make_call(request):
    """
    Initiate a call using telephony service
    """
    agent = request.user
    phone_number = request.POST.get('phone_number', '').strip()
    campaign_id = request.POST.get('campaign_id')
    lead_id = request.POST.get('lead_id')
    
    if not phone_number:
        return JsonResponse({
            'success': False,
            'error': 'Phone number is required'
        })
    
    try:
        telephony_service = AgentTelephonyService(agent)
        result = telephony_service.make_call(
            phone_number=phone_number,
            campaign_id=campaign_id,
            lead_id=lead_id
        )
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error making call for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Call failed. Please try again.'
        })


@login_required
@agent_required
@require_POST
def answer_call(request):
    """
    Answer incoming call
    """
    agent = request.user
    call_id = request.POST.get('call_id')
    
    if not call_id:
        return JsonResponse({
            'success': False,
            'error': 'Call ID is required'
        })
    
    try:
        telephony_service = AgentTelephonyService(agent)
        result = telephony_service.answer_call(call_id)
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error answering call for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to answer call'
        })


@login_required
@agent_required
@require_POST
def hangup_call(request):
    """
    Hangup current call
    """
    agent = request.user
    call_id = request.POST.get('call_id')
    reason = request.POST.get('reason', 'agent_hangup')
    
    if not call_id:
        return JsonResponse({
            'success': False,
            'error': 'Call ID is required'
        })
    
    try:
        telephony_service = AgentTelephonyService(agent)
        result = telephony_service.hangup_call(call_id, reason)
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error hanging up call for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to hangup call'
        })


@login_required
@agent_required
@require_POST
def transfer_call(request):
    """
    Transfer call to another extension/number
    """
    agent = request.user
    call_id = request.POST.get('call_id')
    transfer_to = request.POST.get('transfer_to', '').strip()
    transfer_type = request.POST.get('transfer_type', 'warm')
    
    if not call_id or not transfer_to:
        return JsonResponse({
            'success': False,
            'error': 'Call ID and transfer destination are required'
        })
    
    try:
        telephony_service = AgentTelephonyService(agent)
        result = telephony_service.transfer_call(call_id, transfer_to, transfer_type)
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error transferring call for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Transfer failed'
        })


@login_required
@agent_required
@require_POST
def hold_call(request):
    """
    Put call on hold
    """
    agent = request.user
    call_id = request.POST.get('call_id')
    
    if not call_id:
        return JsonResponse({
            'success': False,
            'error': 'Call ID is required'
        })
    
    try:
        telephony_service = AgentTelephonyService(agent)
        result = telephony_service.hold_call(call_id)
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error holding call for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Hold failed'
        })


@login_required
@agent_required
@require_http_methods(["GET"])
def get_next_lead(request):
    """
    Get next lead for preview dialing
    """
    agent = request.user
    campaign_id = request.GET.get('campaign_id')
    
    if not campaign_id:
        return JsonResponse({
            'success': False,
            'error': 'Campaign ID is required'
        })
    
    try:
        telephony_service = AgentTelephonyService(agent)
        result = telephony_service.get_next_lead(campaign_id)
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error getting next lead for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get next lead'
        })


@login_required
@agent_required
@require_http_methods(["GET"])
def call_status(request):
    """
    Get current call status
    """
    agent = request.user
    
    try:
        telephony_service = AgentTelephonyService(agent)
        result = telephony_service.get_agent_call_status()
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error getting call status for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get call status'
        })


@login_required
@agent_required
@require_POST
def update_status(request):
    """
    Update agent status (break, lunch, available, etc.)
    """
    agent = request.user
    new_status = request.POST.get('status', '').lower().strip()
    break_reason = request.POST.get('break_reason', '').strip()
    
    # Valid status mapping
    status_mapping = {
        'available': 'available',
        'break': 'break',
        'lunch': 'lunch', 
        'coffee': 'break',
        'wc': 'break',
        'wrapup': 'busy'
    }
    
    if new_status not in status_mapping:
        return JsonResponse({
            'success': False,
            'error': 'Invalid status'
        })
    
    try:
        # Get or create agent status
        agent_status, created = AgentStatus.objects.get_or_create(user=agent)
        
        # Update status
        mapped_status = status_mapping[new_status]
        agent_status.set_status(mapped_status, break_reason)
        
        return JsonResponse({
            'success': True,
            'status': new_status,
            'message': f'Status updated to {new_status}'
        })
        
    except Exception as e:
        logger.error(f"Error updating status for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to update status'
        })


@login_required
@agent_required
@require_http_methods(["GET"])
def pending_callbacks(request):
    """
    Get pending callbacks for the agent (AJAX endpoint)
    """
    agent = request.user
    
    try:
        callbacks = AgentCallbackTask.objects.filter(
            agent=agent,
            status__in=['pending', 'scheduled']
        ).select_related('lead', 'campaign').order_by('scheduled_time')[:20]
        
        data = {
            'callbacks': [
                {
                    'id': callback.id,
                    'lead_name': f"{callback.lead.first_name} {callback.lead.last_name}",
                    'lead_phone': callback.lead.phone_number,
                    'scheduled_time': callback.scheduled_time.strftime('%Y-%m-%d %H:%M'),
                    'notes': callback.notes,
                    'is_overdue': callback.is_overdue(),
                    'campaign': callback.campaign.name,
                    'priority': callback.get_priority_display(),
                }
                for callback in callbacks
            ]
        }
        
        return JsonResponse(data)
        
    except Exception as e:
        logger.error(f"Error getting callbacks for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get callbacks'
        })


@login_required
@agent_required
@require_POST
def complete_callback(request):
    """
    Mark a callback as completed
    """
    agent = request.user
    callback_id = request.POST.get('callback_id')
    completion_notes = request.POST.get('completion_notes', '').strip()
    
    if not callback_id:
        return JsonResponse({
            'success': False,
            'error': 'Callback ID is required'
        })
    
    try:
        callback = AgentCallbackTask.objects.get(
            id=callback_id,
            agent=agent,
            status__in=['pending', 'scheduled']
        )
        
        callback.status = 'completed'
        callback.completed_time = timezone.now()
        callback.completion_notes = completion_notes
        callback.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Callback marked as completed'
        })
        
    except AgentCallbackTask.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Callback not found'
        })
    except Exception as e:
        logger.error(f"Error completing callback for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to complete callback'
        })


@login_required
@agent_required
@require_POST
def reschedule_callback(request):
    """
    Reschedule a callback
    """
    agent = request.user
    callback_id = request.POST.get('callback_id')
    new_time = request.POST.get('new_time', '').strip()
    
    if not callback_id or not new_time:
        return JsonResponse({
            'success': False,
            'error': 'Callback ID and new time are required'
        })
    
    try:
        # Parse the new time
        try:
            new_datetime = timezone.datetime.fromisoformat(new_time.replace('Z', '+00:00'))
            if timezone.is_naive(new_datetime):
                new_datetime = timezone.make_aware(new_datetime)
        except ValueError:
            # Try parsing different format
            new_datetime = timezone.datetime.strptime(new_time, '%Y-%m-%d %H:%M')
            new_datetime = timezone.make_aware(new_datetime)
        
        callback = AgentCallbackTask.objects.get(
            id=callback_id,
            agent=agent
        )
        
        callback.scheduled_time = new_datetime
        callback.status = 'scheduled'
        callback.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Callback rescheduled successfully'
        })
        
    except AgentCallbackTask.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Callback not found'
        })
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid time format. Use YYYY-MM-DD HH:MM'
        })
    except Exception as e:
        logger.error(f"Error rescheduling callback for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to reschedule callback'
        })


@login_required
@agent_required
@require_POST
def save_lead_info(request):
    """
    Save lead information during call
    """
    agent = request.user
    phone_number = request.POST.get('phone_number', '').strip()
    
    if not phone_number:
        return JsonResponse({
            'success': False,
            'error': 'Phone number is required'
        })
    
    # Lead data
    lead_data = {
        'first_name': request.POST.get('first_name', '').strip(),
        'last_name': request.POST.get('last_name', '').strip(),
        'email': request.POST.get('email', '').strip(),
        'company': request.POST.get('company', '').strip(),
        'address': request.POST.get('address', '').strip(),
        'city': request.POST.get('city', '').strip(),
        'state': request.POST.get('state', '').strip(),
        'zip_code': request.POST.get('zip_code', '').strip(),
        'comments': request.POST.get('comments', '').strip(),
    }
    
    try:
        # Try to find existing lead
        lead = Lead.objects.filter(phone_number=phone_number).first()
        
        if lead:
            # Update existing lead
            for field, value in lead_data.items():
                if value and hasattr(lead, field):
                    setattr(lead, field, value)
            lead.save()
            message = 'Lead information updated successfully'
        else:
            # Create new lead
            lead_data['phone_number'] = phone_number
            # Remove empty values
            lead_data = {k: v for k, v in lead_data.items() if v}
            lead = Lead.objects.create(**lead_data)
            message = 'New lead created successfully'
        
        return JsonResponse({
            'success': True,
            'message': message,
            'lead_id': lead.id
        })
        
    except Exception as e:
        logger.error(f"Error saving lead info for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to save lead information'
        })


@login_required
@agent_required
@require_http_methods(["GET"])
def get_lead_info(request):
    """
    Get lead information by phone number or lead ID
    """
    phone_number = request.GET.get('phone_number', '').strip()
    lead_id = request.GET.get('lead_id', '').strip()
    
    if not phone_number and not lead_id:
        return JsonResponse({
            'success': False,
            'error': 'Phone number or lead ID is required'
        })
    
    try:
        # Try to find lead by ID first, then by phone number
        lead = None
        if lead_id:
            lead = Lead.objects.filter(id=lead_id).first()
        elif phone_number:
            lead = Lead.objects.filter(phone_number=phone_number).first()
        
        if lead:
            data = {
                'success': True,
                'lead': {
                    'id': lead.id,
                    'first_name': lead.first_name,
                    'last_name': lead.last_name,
                    'phone_number': lead.phone_number,
                    'email': lead.email,
                    'company': lead.company,
                    'address': lead.address,
                    'city': lead.city,
                    'state': lead.state,
                    'zip_code': lead.zip_code,
                    'comments': lead.comments,
                    'status': lead.status,
                    'last_contact_date': lead.last_contact_date.isoformat() if lead.last_contact_date else None,
                }
            }
        else:
            data = {
                'success': True,
                'lead': None,
                'message': 'Lead not found'
            }
        
        return JsonResponse(data)
        
    except Exception as e:
        logger.error(f"Error getting lead info: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve lead information'
        })


@login_required
@agent_required
@require_http_methods(["GET"])
def agent_statistics(request):
    """
    Get agent's current statistics
    """
    agent = request.user
    
    try:
        today = timezone.now().date()
        
        # Today's calls
        today_calls = CallLog.objects.filter(agent=agent, start_time__date=today)
        
        # This week's calls
        week_start = today - timedelta(days=today.weekday())
        week_calls = CallLog.objects.filter(
            agent=agent,
            start_time__date__gte=week_start
        )
        
        # Calculate statistics
        today_total = today_calls.count()
        today_answered = today_calls.filter(call_status='answered').count()
        today_talk_time = sum((call.talk_duration or 0) for call in today_calls)
        
        week_total = week_calls.count()
        week_answered = week_calls.filter(call_status='answered').count()
        week_talk_time = sum((call.talk_duration or 0) for call in week_calls)
        
        # Pending callbacks count
        pending_callbacks_count = AgentCallbackTask.objects.filter(
            agent=agent,
            status__in=['pending', 'scheduled']
        ).count()
        
        stats = {
            'today': {
                'total_calls': today_total,
                'answered_calls': today_answered,
                'talk_time': today_talk_time,
                'contact_rate': round((today_answered / today_total * 100) if today_total > 0 else 0, 1),
            },
            'week': {
                'total_calls': week_total,
                'answered_calls': week_answered,
                'talk_time': week_talk_time,
                'contact_rate': round((week_answered / week_total * 100) if week_total > 0 else 0, 1),
            },
            'pending_callbacks': pending_callbacks_count
        }
        
        return JsonResponse(stats)
        
    except Exception as e:
        logger.error(f"Error getting statistics for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get statistics'
        })


@login_required
@agent_required
@require_POST
def set_disposition(request):
    """
    Set call disposition
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
        # Get call log and disposition
        call_log = CallLog.objects.filter(id=call_id, agent=agent).first()
        disposition = Disposition.objects.filter(id=disposition_id).first()
        
        if not call_log:
            return JsonResponse({
                'success': False,
                'error': 'Call not found'
            })
        
        if not disposition:
            return JsonResponse({
                'success': False,
                'error': 'Disposition not found'
            })
        
        # Update call with disposition
        call_log.disposition = disposition
        call_log.disposition_notes = notes
        call_log.save()
        
        # Update lead status if applicable
        if call_log.lead and disposition.status_to_set:
            lead = call_log.lead
            lead.status = disposition.status_to_set
            lead.last_contact_date = timezone.now().date()
            lead.save()
        
        return JsonResponse({
            'success': True,
            'disposition': disposition.name,
            'message': 'Disposition set successfully'
        })
        
    except Exception as e:
        logger.error(f"Error setting disposition for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to set disposition'
        })


@login_required
@agent_required
@require_POST
def schedule_callback(request):
    """
    Schedule a callback for a lead
    """
    agent = request.user
    lead_id = request.POST.get('lead_id')
    callback_time = request.POST.get('callback_time', '').strip()
    notes = request.POST.get('notes', '').strip()
    priority = request.POST.get('priority', '2')
    
    if not lead_id or not callback_time:
        return JsonResponse({
            'success': False,
            'error': 'Lead ID and callback time are required'
        })
    
    try:
        # Parse callback time
        try:
            callback_datetime = timezone.datetime.fromisoformat(callback_time.replace('Z', '+00:00'))
            if timezone.is_naive(callback_datetime):
                callback_datetime = timezone.make_aware(callback_datetime)
        except ValueError:
            callback_datetime = timezone.datetime.strptime(callback_time, '%Y-%m-%d %H:%M')
            callback_datetime = timezone.make_aware(callback_datetime)
        
        # Get lead
        lead = Lead.objects.filter(id=lead_id).first()
        if not lead:
            return JsonResponse({
                'success': False,
                'error': 'Lead not found'
            })
        
        # Get current campaign (or use first available)
        current_campaign = Campaign.objects.filter(
            assigned_users=agent,
            status='active',
            campaignagent__is_active=True
        ).first()
        
        if not current_campaign:
            return JsonResponse({
                'success': False,
                'error': 'No active campaign found'
            })
        
        # Create callback task
        callback_task = AgentCallbackTask.objects.create(
            agent=agent,
            lead=lead,
            campaign=current_campaign,
            scheduled_time=callback_datetime,
            notes=notes,
            priority=int(priority),
            created_by=agent
        )
        
        return JsonResponse({
            'success': True,
            'callback_id': callback_task.id,
            'message': 'Callback scheduled successfully'
        })
        
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid time format. Use YYYY-MM-DD HH:MM'
        })
    except Exception as e:
        logger.error(f"Error scheduling callback for {agent.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to schedule callback'
        })
