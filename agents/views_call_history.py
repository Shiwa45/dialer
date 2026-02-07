"""
Agent Views - Phase 2.2: Call History Feature

This module adds the call history page and related API endpoints.
Add these views to your existing agents/views_simple.py or agents/views.py
"""

import logging
from datetime import timedelta

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import timezone
from django.db.models import Q, Sum, Count
from django.core.paginator import Paginator

from agents.decorators import agent_required
from agents.models import AgentCallbackTask
from calls.models import CallLog
from campaigns.models import Campaign, Disposition
from leads.models import Lead

logger = logging.getLogger(__name__)


# ============================================================================
# PHASE 2.2: Call History Page
# ============================================================================

@login_required
@agent_required
def call_history_page(request):
    """
    Render call history page with filters and pagination
    
    PHASE 2.2: Full call history view for agents
    """
    agent = request.user
    
    # Base queryset
    calls = CallLog.objects.filter(agent=agent).select_related(
        'lead', 'disposition', 'campaign'
    ).order_by('-start_time')
    
    # Apply filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    disposition_id = request.GET.get('disposition')
    campaign_id = request.GET.get('campaign')
    call_type = request.GET.get('call_type')
    
    if date_from:
        calls = calls.filter(start_time__date__gte=date_from)
    if date_to:
        calls = calls.filter(start_time__date__lte=date_to)
    if disposition_id:
        calls = calls.filter(disposition_id=disposition_id)
    if campaign_id:
        calls = calls.filter(campaign_id=campaign_id)
    if call_type:
        calls = calls.filter(call_type=call_type)
    
    # Pagination
    paginator = Paginator(calls, 25)  # 25 calls per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Calculate statistics for the filtered results
    stats = _calculate_call_stats(calls)
    
    # Get filter options
    dispositions = Disposition.objects.filter(is_active=True).order_by('name')
    campaigns = Campaign.objects.filter(assigned_users=agent).order_by('name')
    
    context = {
        'calls': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'stats': stats,
        'dispositions': dispositions,
        'campaigns': campaigns,
    }
    
    return render(request, 'agents/call_history.html', context)


@login_required
@agent_required
@require_http_methods(["GET"])
def call_history_api(request):
    """
    API endpoint for call history (AJAX/DataTables)
    
    Returns paginated call data as JSON
    """
    agent = request.user
    
    # Pagination parameters
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 25))
    
    # Filter parameters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    disposition_id = request.GET.get('disposition')
    campaign_id = request.GET.get('campaign')
    call_type = request.GET.get('call_type')
    search = request.GET.get('search', '').strip()
    
    try:
        calls = CallLog.objects.filter(agent=agent).select_related(
            'lead', 'disposition', 'campaign'
        ).order_by('-start_time')
        
        # Apply filters
        if date_from:
            calls = calls.filter(start_time__date__gte=date_from)
        if date_to:
            calls = calls.filter(start_time__date__lte=date_to)
        if disposition_id:
            calls = calls.filter(disposition_id=disposition_id)
        if campaign_id:
            calls = calls.filter(campaign_id=campaign_id)
        if call_type:
            calls = calls.filter(call_type=call_type)
        if search:
            calls = calls.filter(
                Q(called_number__icontains=search) |
                Q(lead__first_name__icontains=search) |
                Q(lead__last_name__icontains=search) |
                Q(lead__company__icontains=search)
            )
        
        # Get total count before pagination
        total = calls.count()
        
        # Paginate
        offset = (page - 1) * per_page
        calls = calls[offset:offset + per_page]
        
        # Format response
        call_list = []
        for call in calls:
            call_list.append({
                'id': call.id,
                'start_time': call.start_time.isoformat() if call.start_time else None,
                'called_number': call.called_number or call.caller_id,
                'call_type': call.call_type,
                'talk_duration': call.talk_duration or 0,
                'call_status': call.call_status,
                'disposition': {
                    'id': call.disposition.id,
                    'name': call.disposition.name,
                    'category': call.disposition.category
                } if call.disposition else None,
                'campaign': {
                    'id': call.campaign.id,
                    'name': call.campaign.name
                } if call.campaign else None,
                'lead': {
                    'id': call.lead.id,
                    'name': f"{call.lead.first_name} {call.lead.last_name}",
                    'company': call.lead.company
                } if call.lead else None,
                'has_recording': bool(call.recording_file)
            })
        
        return JsonResponse({
            'success': True,
            'calls': call_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        })
        
    except Exception as e:
        logger.error(f"Error in call_history_api: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch call history'
        })


@login_required
@agent_required
@require_http_methods(["GET"])
def call_history_stats(request):
    """
    API endpoint for call history statistics
    
    Returns aggregated stats for the agent
    """
    agent = request.user
    
    # Get date range from request or default to today
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    try:
        calls = CallLog.objects.filter(agent=agent)
        
        if date_from:
            calls = calls.filter(start_time__date__gte=date_from)
        if date_to:
            calls = calls.filter(start_time__date__lte=date_to)
        else:
            # Default to today if no date range
            today = timezone.now().date()
            calls = calls.filter(start_time__date=today)
        
        stats = _calculate_call_stats(calls)
        
        return JsonResponse({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Error in call_history_stats: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch statistics'
        })


@login_required
@agent_required
@require_http_methods(["GET"])
def call_details_api(request, call_id):
    """
    API endpoint for detailed call information
    """
    agent = request.user
    
    try:
        call = CallLog.objects.filter(id=call_id, agent=agent).select_related(
            'lead', 'disposition', 'campaign'
        ).first()
        
        if not call:
            return JsonResponse({
                'success': False,
                'error': 'Call not found'
            })
        
        call_data = {
            'id': call.id,
            'called_number': call.called_number,
            'caller_id': call.caller_id,
            'call_type': call.call_type,
            'call_status': call.call_status,
            'start_time': call.start_time.strftime('%Y-%m-%d %H:%M:%S') if call.start_time else None,
            'answer_time': call.answer_time.strftime('%Y-%m-%d %H:%M:%S') if call.answer_time else None,
            'end_time': call.end_time.strftime('%Y-%m-%d %H:%M:%S') if call.end_time else None,
            'talk_duration': call.talk_duration,
            'total_duration': call.total_duration,
            'disposition': call.disposition.name if call.disposition else None,
            'notes': call.disposition_notes,
            'campaign': call.campaign.name if call.campaign else None,
            'recording_available': bool(call.recording_file),
            'lead': None
        }
        
        if call.lead:
            call_data['lead'] = {
                'id': call.lead.id,
                'name': f"{call.lead.first_name} {call.lead.last_name}",
                'phone': call.lead.phone_number,
                'email': call.lead.email,
                'company': call.lead.company,
                'status': call.lead.status,
                'call_count': call.lead.call_count
            }
        
        return JsonResponse({
            'success': True,
            'call': call_data
        })
        
    except Exception as e:
        logger.error(f"Error in call_details_api: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch call details'
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
    scheduled_time = request.POST.get('scheduled_time')
    notes = request.POST.get('notes', '').strip()
    
    if not lead_id or not scheduled_time:
        return JsonResponse({
            'success': False,
            'error': 'Lead ID and scheduled time are required'
        })
    
    try:
        lead = Lead.objects.filter(id=lead_id).first()
        if not lead:
            return JsonResponse({
                'success': False,
                'error': 'Lead not found'
            })
        
        # Get agent's current campaign
        from users.models import AgentStatus
        agent_status = AgentStatus.objects.filter(user=agent).first()
        campaign = agent_status.current_campaign if agent_status else None
        
        # Create callback task
        callback = AgentCallbackTask.objects.create(
            agent=agent,
            lead=lead,
            campaign=campaign,
            scheduled_time=scheduled_time,
            notes=notes,
            status='scheduled',
            priority='medium'
        )
        
        # Update lead status
        lead.status = 'callback'
        lead.save(update_fields=['status'])
        
        logger.info(f"Callback scheduled for lead {lead_id} by agent {agent.username}")
        
        return JsonResponse({
            'success': True,
            'callback_id': callback.id,
            'message': 'Callback scheduled successfully'
        })
        
    except Exception as e:
        logger.error(f"Error scheduling callback: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to schedule callback'
        })


def _calculate_call_stats(calls_queryset):
    """
    Calculate statistics from a calls queryset
    
    Args:
        calls_queryset: QuerySet of CallLog objects
    
    Returns:
        dict: Statistics dictionary
    """
    stats = calls_queryset.aggregate(
        total_calls=Count('id'),
        answered_calls=Count('id', filter=Q(call_status='answered') | Q(answer_time__isnull=False)),
        total_talk_seconds=Sum('talk_duration'),
        sales=Count('id', filter=Q(disposition__is_sale=True))
    )
    
    total_seconds = stats['total_talk_seconds'] or 0
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    
    if hours > 0:
        talk_time_str = f"{hours}h {minutes}m"
    else:
        talk_time_str = f"{minutes}m"
    
    return {
        'total_calls': stats['total_calls'] or 0,
        'answered_calls': stats['answered_calls'] or 0,
        'total_talk_time': talk_time_str,
        'total_talk_seconds': total_seconds,
        'sales': stats['sales'] or 0
    }


# ============================================================================
# URL Patterns to Add
# ============================================================================
"""
Add these URL patterns to agents/urls.py:

# Phase 2.2: Call History
path('call-history/', views.call_history_page, name='call_history_page'),
path('api/call-history/', views.call_history_api, name='call_history_api'),
path('api/call-history/stats/', views.call_history_stats, name='call_history_stats'),
path('api/call-details/<int:call_id>/', views.call_details_api, name='call_details_api'),
path('api/schedule-callback/', views.schedule_callback, name='schedule_callback'),
"""
