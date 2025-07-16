# agents/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, Avg, F
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views import View
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta, datetime
import json
import uuid

from .models import (
    AgentQueue, AgentScript, AgentHotkey, AgentBreakCode, 
    AgentSkill, AgentPerformanceGoal, AgentNote, 
    AgentWebRTCSession, AgentCallbackTask
)
from .forms import (
    AgentStatusForm, CallControlForm, DispositionForm,
    CallbackScheduleForm, AgentScriptForm, AgentHotkeyForm
)
from campaigns.models import Campaign, Disposition
from leads.models import Lead
from calls.models import CallLog, AgentSession
from users.models import AgentStatus
from core.decorators import agent_required, supervisor_required


@login_required
@agent_required
def agent_dashboard(request):
    """
    Main agent interface dashboard
    """
    agent = request.user
    today = timezone.now().date()
    
    # Get agent's current status
    agent_status, created = AgentStatus.objects.get_or_create(user=agent)
    
    # Get agent's assigned campaigns
    assigned_campaigns = Campaign.objects.filter(
        agent_assignments__agent=agent,
        agent_assignments__is_active=True,
        status='active'
    )
    
    # Get today's statistics
    today_calls = CallLog.objects.filter(agent=agent, start_time__date=today)
    today_stats = {
        'total_calls': today_calls.count(),
        'answered_calls': today_calls.filter(call_status='answered').count(),
        'sales': today_calls.filter(disposition__is_sale=True).count(),
        'talk_time': today_calls.aggregate(Sum('talk_duration'))['talk_duration__sum'] or 0,
    }
    
    # Get pending callbacks
    pending_callbacks = AgentCallbackTask.objects.filter(
        agent=agent,
        status__in=['pending', 'scheduled'],
        scheduled_time__lte=timezone.now() + timedelta(hours=2)
    ).order_by('scheduled_time')[:5]
    
    # Get current active session
    active_session = AgentSession.objects.filter(
        agent=agent,
        status='active'
    ).first()
    
    # Get available scripts
    available_scripts = AgentScript.objects.filter(
        Q(campaign__in=assigned_campaigns) | Q(is_global=True),
        is_active=True
    ).order_by('display_order')
    
    # Get agent's hotkeys
    agent_hotkeys = AgentHotkey.objects.filter(
        agent=agent,
        is_active=True
    ).order_by('key_combination')
    
    context = {
        'agent': agent,
        'agent_status': agent_status,
        'assigned_campaigns': assigned_campaigns,
        'today_stats': today_stats,
        'pending_callbacks': pending_callbacks,
        'active_session': active_session,
        'available_scripts': available_scripts,
        'agent_hotkeys': agent_hotkeys,
        'break_codes': AgentBreakCode.objects.filter(is_active=True),
    }
    
    return render(request, 'agents/dashboard.html', context)


@login_required
@agent_required
def agent_phone_interface(request):
    """
    Agent phone control interface
    """
    agent = request.user
    
    # Get or create WebRTC session
    webrtc_session, created = AgentWebRTCSession.objects.get_or_create(
        agent=agent,
        defaults={
            'session_id': str(uuid.uuid4()),
            'status': 'connecting'
        }
    )
    
    # Get current call if any
    current_call = CallLog.objects.filter(
        agent=agent,
        end_time__isnull=True
    ).first()
    
    # Get agent's phone settings
    agent_queue = AgentQueue.objects.filter(
        agent=agent,
        is_active=True
    ).first()
    
    context = {
        'webrtc_session': webrtc_session,
        'current_call': current_call,
        'agent_queue': agent_queue,
        'sip_servers': [],  # Add your SIP server configuration
    }
    
    return render(request, 'agents/phone_interface.html', context)


@login_required
@agent_required 
def lead_interface(request, lead_id=None):
    """
    Lead information interface during calls
    """
    agent = request.user
    lead = None
    call_history = []
    
    if lead_id:
        lead = get_object_or_404(Lead, id=lead_id)
        call_history = CallLog.objects.filter(
            lead=lead
        ).order_by('-start_time')[:10]
    
    # Get available dispositions for current campaign
    current_campaign = getattr(request.user.agent_status, 'current_campaign', None)
    available_dispositions = []
    if current_campaign:
        available_dispositions = Disposition.objects.filter(
            campaign=current_campaign,
            is_active=True
        ).order_by('sort_order')
    
    # Get lead's previous callbacks
    previous_callbacks = AgentCallbackTask.objects.filter(
        lead=lead,
        status='completed'
    ).order_by('-completed_time')[:5] if lead else []
    
    context = {
        'lead': lead,
        'call_history': call_history,
        'available_dispositions': available_dispositions,
        'previous_callbacks': previous_callbacks,
        'disposition_form': DispositionForm(campaign=current_campaign),
        'callback_form': CallbackScheduleForm(),
    }
    
    return render(request, 'agents/lead_interface.html', context)


@login_required
@agent_required
@require_POST
def update_agent_status(request):
    """
    Update agent status (available, break, etc.)
    """
    agent = request.user
    new_status = request.POST.get('status')
    break_reason = request.POST.get('break_reason', '')
    
    if new_status not in dict(AgentStatus.STATUS_CHOICES):
        return JsonResponse({'success': False, 'error': 'Invalid status'})
    
    # Get or create agent status
    agent_status, created = AgentStatus.objects.get_or_create(user=agent)
    
    # Update status
    old_status = agent_status.status
    agent_status.set_status(new_status, break_reason)
    
    # If going on break, create pause record
    if new_status == 'break' and old_status != 'break':
        active_session = AgentSession.objects.filter(
            agent=agent,
            status='active'
        ).first()
        
        if active_session:
            from calls.models import AgentPause
            AgentPause.objects.create(
                agent_session=active_session,
                pause_reason='break',
                pause_start=timezone.now(),
                notes=break_reason
            )
    
    return JsonResponse({
        'success': True,
        'status': new_status,
        'status_display': agent_status.get_status_display(),
        'timestamp': agent_status.status_changed_at.isoformat()
    })


@login_required
@agent_required
@require_POST  
def make_call(request):
    """
    Initiate outbound call
    """
    agent = request.user
    phone_number = request.POST.get('phone_number')
    lead_id = request.POST.get('lead_id')
    campaign_id = request.POST.get('campaign_id')
    
    if not phone_number:
        return JsonResponse({'success': False, 'error': 'Phone number required'})
    
    # Validate agent can make calls
    agent_status = getattr(agent, 'agent_status', None)
    if not agent_status or agent_status.status != 'available':
        return JsonResponse({'success': False, 'error': 'Agent not available'})
    
    # Get lead and campaign
    lead = None
    if lead_id:
        lead = Lead.objects.filter(id=lead_id).first()
    
    campaign = None
    if campaign_id:
        campaign = Campaign.objects.filter(id=campaign_id).first()
    
    # Create call log entry
    call_log = CallLog.objects.create(
        call_id=str(uuid.uuid4()),
        call_type='outbound',
        call_status='initiated',
        called_number=phone_number,
        agent=agent,
        lead=lead,
        campaign=campaign,
        start_time=timezone.now()
    )
    
    # Update agent status
    agent_status.current_call_id = call_log.call_id
    agent_status.call_start_time = timezone.now()
    agent_status.set_status('busy')
    
    # TODO: Integrate with Asterisk ARI to actually place the call
    # This would involve calling Asterisk REST Interface
    
    return JsonResponse({
        'success': True,
        'call_id': call_log.call_id,
        'message': 'Call initiated'
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
        return JsonResponse({'success': False, 'error': 'Call ID required'})
    
    # Get call log
    call_log = CallLog.objects.filter(call_id=call_id, agent=agent).first()
    if not call_log:
        return JsonResponse({'success': False, 'error': 'Call not found'})
    
    # Update call status
    call_log.call_status = 'answered'
    call_log.answer_time = timezone.now()
    call_log.save()
    
    # Update agent status
    agent_status = getattr(agent, 'agent_status', None)
    if agent_status:
        agent_status.current_call_id = call_id
        agent_status.call_start_time = timezone.now()
        agent_status.set_status('busy')
    
    return JsonResponse({
        'success': True,
        'call_id': call_id,
        'message': 'Call answered'
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
    
    if not call_id:
        return JsonResponse({'success': False, 'error': 'Call ID required'})
    
    # Get call log
    call_log = CallLog.objects.filter(call_id=call_id, agent=agent).first()
    if not call_log:
        return JsonResponse({'success': False, 'error': 'Call not found'})
    
    # Update call status
    call_log.call_status = 'hangup'
    call_log.end_time = timezone.now()
    
    # Calculate durations
    if call_log.answer_time:
        call_log.talk_duration = int((call_log.end_time - call_log.answer_time).total_seconds())
    
    if call_log.start_time:
        call_log.total_duration = int((call_log.end_time - call_log.start_time).total_seconds())
    
    call_log.save()
    
    # Update agent status
    agent_status = getattr(agent, 'agent_status', None)
    if agent_status:
        agent_status.current_call_id = ''
        agent_status.call_start_time = None
        agent_status.set_status('available')
    
    return JsonResponse({
        'success': True,
        'call_id': call_id,
        'message': 'Call ended'
    })


@login_required
@agent_required
@require_POST
def transfer_call(request):
    """
    Transfer current call
    """
    agent = request.user
    call_id = request.POST.get('call_id')
    transfer_to = request.POST.get('transfer_to')
    transfer_type = request.POST.get('transfer_type', 'warm')  # warm, cold
    
    if not call_id or not transfer_to:
        return JsonResponse({'success': False, 'error': 'Call ID and transfer destination required'})
    
    # Get call log
    call_log = CallLog.objects.filter(call_id=call_id, agent=agent).first()
    if not call_log:
        return JsonResponse({'success': False, 'error': 'Call not found'})
    
    # Create transfer record
    from calls.models import Transfer
    transfer = Transfer.objects.create(
        call_log=call_log,
        from_agent=agent,
        transfer_type=transfer_type,
        to_number=transfer_to,
        transfer_time=timezone.now()
    )
    
    # Update call status
    call_log.call_status = 'transferred'
    call_log.save()
    
    # TODO: Integrate with Asterisk to perform actual transfer
    
    return JsonResponse({
        'success': True,
        'transfer_id': transfer.id,
        'message': f'{transfer_type.title()} transfer initiated'
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
    notes = request.POST.get('notes', '')
    
    if not call_id or not disposition_id:
        return JsonResponse({'success': False, 'error': 'Call ID and disposition required'})
    
    # Get call log and disposition
    call_log = CallLog.objects.filter(call_id=call_id, agent=agent).first()
    disposition = Disposition.objects.filter(id=disposition_id).first()
    
    if not call_log or not disposition:
        return JsonResponse({'success': False, 'error': 'Call or disposition not found'})
    
    # Update call with disposition
    call_log.disposition = disposition
    call_log.disposition_notes = notes
    call_log.save()
    
    # Update lead status if applicable
    if call_log.lead:
        lead = call_log.lead
        if disposition.status_to_set:
            lead.status = disposition.status_to_set
            lead.last_contact_date = timezone.now().date()
            lead.save()
    
    return JsonResponse({
        'success': True,
        'disposition': disposition.name,
        'message': 'Disposition set successfully'
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
    callback_time = request.POST.get('callback_time')
    notes = request.POST.get('notes', '')
    priority = request.POST.get('priority', 2)
    
    if not lead_id or not callback_time:
        return JsonResponse({'success': False, 'error': 'Lead ID and callback time required'})
    
    try:
        # Parse callback time
        callback_datetime = timezone.datetime.fromisoformat(callback_time.replace('Z', '+00:00'))
        if timezone.is_naive(callback_datetime):
            callback_datetime = timezone.make_aware(callback_datetime)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid callback time format'})
    
    # Get lead
    lead = Lead.objects.filter(id=lead_id).first()
    if not lead:
        return JsonResponse({'success': False, 'error': 'Lead not found'})
    
    # Get current campaign
    current_campaign = getattr(agent.agent_status, 'current_campaign', None)
    if not current_campaign:
        return JsonResponse({'success': False, 'error': 'No active campaign'})
    
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


@login_required
@agent_required
def get_lead_info(request, lead_id):
    """
    Get detailed lead information for agent interface
    """
    lead = get_object_or_404(Lead, id=lead_id)
    
    # Get call history
    call_history = CallLog.objects.filter(lead=lead).order_by('-start_time')[:10]
    
    # Get previous notes
    from leads.models import LeadNote
    lead_notes = LeadNote.objects.filter(lead=lead).order_by('-created_at')[:5]
    
    # Get callback history
    callback_history = AgentCallbackTask.objects.filter(
        lead=lead,
        status='completed'
    ).order_by('-completed_time')[:5]
    
    # Prepare response data
    data = {
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
            'status': lead.status,
            'priority': lead.priority,
            'comments': lead.comments,
            'last_contact_date': lead.last_contact_date.isoformat() if lead.last_contact_date else None,
        },
        'call_history': [
            {
                'id': call.id,
                'call_type': call.call_type,
                'call_status': call.call_status,
                'start_time': call.start_time.isoformat(),
                'duration': call.total_duration,
                'disposition': call.disposition.name if call.disposition else None,
                'agent': call.agent.get_full_name() if call.agent else None,
            }
            for call in call_history
        ],
        'notes': [
            {
                'id': note.id,
                'content': note.content,
                'created_at': note.created_at.isoformat(),
                'created_by': note.created_by.get_full_name(),
            }
            for note in lead_notes
        ],
        'callbacks': [
            {
                'id': callback.id,
                'scheduled_time': callback.scheduled_time.isoformat(),
                'completed_time': callback.completed_time.isoformat() if callback.completed_time else None,
                'notes': callback.notes,
                'completion_notes': callback.completion_notes,
            }
            for callback in callback_history
        ]
    }
    
    return JsonResponse(data)


@login_required
@agent_required
def get_campaign_scripts(request, campaign_id):
    """
    Get scripts for a specific campaign
    """
    campaign = get_object_or_404(Campaign, id=campaign_id)
    
    # Get campaign-specific and global scripts
    scripts = AgentScript.objects.filter(
        Q(campaign=campaign) | Q(is_global=True),
        is_active=True
    ).order_by('display_order', 'name')
    
    data = {
        'scripts': [
            {
                'id': script.id,
                'name': script.name,
                'script_type': script.script_type,
                'content': script.content,
                'auto_display': script.auto_display,
            }
            for script in scripts
        ]
    }
    
    return JsonResponse(data)


@login_required
@agent_required
def agent_statistics(request):
    """
    Get real-time agent statistics
    """
    agent = request.user
    
    # Today's stats
    today = timezone.now().date()
    today_calls = CallLog.objects.filter(agent=agent, start_time__date=today)
    
    # Week's stats
    week_start = today - timedelta(days=today.weekday())
    week_calls = CallLog.objects.filter(
        agent=agent,
        start_time__date__gte=week_start
    )
    
    # Current session stats
    current_session = AgentSession.objects.filter(
        agent=agent,
        status='active'
    ).first()
    
    session_stats = {}
    if current_session:
        session_duration = current_session.session_duration()
        session_stats = {
            'session_duration': int(session_duration),
            'calls_handled': current_session.calls_handled,
            'talk_time': current_session.talk_time,
            'idle_time': current_session.idle_time,
            'pause_time': current_session.pause_time,
        }
    
    data = {
        'today': {
            'total_calls': today_calls.count(),
            'answered_calls': today_calls.filter(call_status='answered').count(),
            'sales': today_calls.filter(disposition__is_sale=True).count(),
            'talk_time': today_calls.aggregate(Sum('talk_duration'))['talk_duration__sum'] or 0,
        },
        'week': {
            'total_calls': week_calls.count(),
            'answered_calls': week_calls.filter(call_status='answered').count(),
            'sales': week_calls.filter(disposition__is_sale=True).count(),
            'talk_time': week_calls.aggregate(Sum('talk_duration'))['talk_duration__sum'] or 0,
        },
        'session': session_stats,
        'goals': []  # TODO: Add performance goals progress
    }
    
    return JsonResponse(data)


@login_required
@agent_required
def pending_callbacks(request):
    """
    Get pending callbacks for agent
    """
    agent = request.user
    
    callbacks = AgentCallbackTask.objects.filter(
        agent=agent,
        status__in=['pending', 'scheduled']
    ).select_related('lead', 'campaign').order_by('scheduled_time')
    
    data = {
        'callbacks': [
            {
                'id': callback.id,
                'lead_name': f"{callback.lead.first_name} {callback.lead.last_name}",
                'lead_phone': callback.lead.phone_number,
                'scheduled_time': callback.scheduled_time.isoformat(),
                'notes': callback.notes,
                'priority': callback.priority,
                'is_overdue': callback.is_overdue(),
                'campaign': callback.campaign.name,
            }
            for callback in callbacks
        ]
    }
    
    return JsonResponse(data)


@login_required 
@supervisor_required
def agent_monitoring(request):
    """
    Supervisor interface for monitoring agents
    """
    # Get all active agents
    active_agents = User.objects.filter(
        agent_status__status__in=['available', 'busy', 'break'],
        is_active=True
    ).select_related('agent_status', 'profile')
    
    # Get current calls
    active_calls = CallLog.objects.filter(
        end_time__isnull=True
    ).select_related('agent', 'lead', 'campaign')
    
    # Get today's statistics by agent
    today = timezone.now().date()
    agent_stats = {}
    
    for agent in active_agents:
        today_calls = CallLog.objects.filter(agent=agent, start_time__date=today)
        agent_stats[agent.id] = {
            'total_calls': today_calls.count(),
            'answered_calls': today_calls.filter(call_status='answered').count(),
            'sales': today_calls.filter(disposition__is_sale=True).count(),
            'talk_time': today_calls.aggregate(Sum('talk_duration'))['talk_duration__sum'] or 0,
        }
    
    context = {
        'active_agents': active_agents,
        'active_calls': active_calls,
        'agent_stats': agent_stats,
    }
    
    return render(request, 'agents/monitoring.html', context)


@login_required
@supervisor_required
@require_POST
def coach_agent(request):
    """
    Whisper coaching to agent during call
    """
    agent_id = request.POST.get('agent_id')
    message = request.POST.get('message')
    
    if not agent_id or not message:
        return JsonResponse({'success': False, 'error': 'Agent ID and message required'})
    
    agent = get_object_or_404(User, id=agent_id)
    
    # TODO: Implement whisper coaching via Asterisk
    # This would involve sending a whisper message to the agent's channel
    
    return JsonResponse({
        'success': True,
        'message': 'Coaching message sent'
    })


@login_required
@supervisor_required  
@require_POST
def barge_call(request):
    """
    Barge into agent's call
    """
    call_id = request.POST.get('call_id')
    
    if not call_id:
        return JsonResponse({'success': False, 'error': 'Call ID required'})
    
    call_log = get_object_or_404(CallLog, call_id=call_id)
    
    # TODO: Implement call barging via Asterisk
    # This would involve joining the supervisor to the call channel
    
    return JsonResponse({
        'success': True,
        'message': 'Joined call'
    })


class AgentScriptListView(LoginRequiredMixin, ListView):
    """
    List available scripts for agent
    """
    model = AgentScript
    template_name = 'agents/scripts.html'
    context_object_name = 'scripts'
    
    def get_queryset(self):
        agent = self.request.user
        
        # Get agent's assigned campaigns
        assigned_campaigns = Campaign.objects.filter(
            agent_assignments__agent=agent,
            agent_assignments__is_active=True
        )
        
        return AgentScript.objects.filter(
            Q(campaign__in=assigned_campaigns) | Q(is_global=True),
            is_active=True
        ).order_by('script_type', 'display_order')


class AgentPerformanceView(LoginRequiredMixin, DetailView):
    """
    Agent performance dashboard
    """
    template_name = 'agents/performance.html'
    
    def get_object(self):
        return self.request.user
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agent = self.object
        
        # Get date ranges
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        
        # Get performance data
        context['performance_data'] = {
            'today': self.get_period_stats(agent, today, today),
            'week': self.get_period_stats(agent, week_start, today),
            'month': self.get_period_stats(agent, month_start, today),
        }
        
        # Get performance goals
        context['goals'] = AgentPerformanceGoal.objects.filter(
            agent=agent,
            is_active=True,
            start_date__lte=today,
            end_date__gte=today
        )
        
        return context
    
    def get_period_stats(self, agent, start_date, end_date):
        """Get statistics for a date period"""
        calls = CallLog.objects.filter(
            agent=agent,
            start_time__date__range=[start_date, end_date]
        )
        
        total_calls = calls.count()
        answered_calls = calls.filter(call_status='answered').count()
        sales = calls.filter(disposition__is_sale=True).count()
        
        return {
            'total_calls': total_calls,
            'answered_calls': answered_calls,
            'sales': sales,
            'contact_rate': round((answered_calls / total_calls * 100) if total_calls > 0 else 0, 1),
            'conversion_rate': round((sales / answered_calls * 100) if answered_calls > 0 else 0, 1),
            'talk_time': calls.aggregate(Sum('talk_duration'))['talk_duration__sum'] or 0,
        }