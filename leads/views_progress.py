"""
Lead Views - Phase 2.4: Progress Tracking and Recycling

This module adds views for:
1. Lead list progress tracking
2. Lead recycling API
3. Recycle rule management

Add these views to your existing leads/views.py
"""

import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q

from core.decorators import manager_required, supervisor_required

logger = logging.getLogger(__name__)


# ============================================================================
# PHASE 2.4: Lead List Progress Tracking
# ============================================================================

@login_required
def lead_list_detail_with_progress(request, list_id):
    """
    Lead list detail page with progress tracking
    
    PHASE 2.4: Shows real-time progress and recycle rules
    """
    from leads.models import LeadList, LeadRecycleRule
    
    lead_list = get_object_or_404(LeadList, id=list_id)
    
    # Get progress stats
    progress = _get_list_progress(lead_list)
    
    # Get recycle rules for this list
    recycle_rules = LeadRecycleRule.objects.filter(
        Q(lead_list=lead_list) | Q(lead_list__isnull=True),
        is_active=True
    ).order_by('name')
    
    context = {
        'lead_list': lead_list,
        'progress': progress,
        'recycle_rules': recycle_rules,
    }
    
    return render(request, 'leads/lead_list_progress.html', context)


@login_required
@require_http_methods(["GET"])
def lead_list_progress_api(request, list_id):
    """
    API endpoint for lead list progress
    
    Returns real-time progress statistics as JSON
    """
    from leads.models import LeadList
    
    try:
        lead_list = get_object_or_404(LeadList, id=list_id)
        progress = _get_list_progress(lead_list)
        
        return JsonResponse({
            'success': True,
            'progress': progress
        })
        
    except Exception as e:
        logger.error(f"Error getting list progress: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch progress'
        })


def _get_list_progress(lead_list):
    """
    Calculate progress statistics for a lead list
    
    Args:
        lead_list: LeadList instance
    
    Returns:
        dict: Progress statistics
    """
    from leads.models import Lead
    
    leads = Lead.objects.filter(lead_list=lead_list)
    
    # Get status counts
    status_counts = leads.values('status').annotate(count=Count('id'))
    status_dict = {item['status']: item['count'] for item in status_counts}
    
    total = leads.count()
    used = leads.filter(call_count__gt=0).count()
    
    # Calculate percentages
    progress_pct = round((used / total) * 100, 1) if total > 0 else 0
    
    completed_statuses = ['sale', 'dnc', 'not_interested']
    completed = sum(status_dict.get(s, 0) for s in completed_statuses)
    completion_pct = round((completed / total) * 100, 1) if total > 0 else 0
    
    # Remaining leads (can still be called)
    remaining_statuses = ['new', 'callback', 'no_answer', 'busy']
    remaining = sum(status_dict.get(s, 0) for s in remaining_statuses)
    
    # Contacted = total - new - dnc
    contacted = total - status_dict.get('new', 0) - status_dict.get('dnc', 0)
    
    return {
        'total_leads': total,
        'new_leads': status_dict.get('new', 0),
        'contacted_leads': contacted,
        'used_leads': used,
        'remaining_leads': remaining,
        'sale_leads': status_dict.get('sale', 0),
        'callback_leads': status_dict.get('callback', 0),
        'dnc_leads': status_dict.get('dnc', 0),
        'no_answer_leads': status_dict.get('no_answer', 0),
        'busy_leads': status_dict.get('busy', 0),
        'not_interested_leads': status_dict.get('not_interested', 0),
        'progress_percentage': progress_pct,
        'completion_percentage': completion_pct,
        'status_breakdown': status_dict
    }


# ============================================================================
# PHASE 2.4: Lead Recycling
# ============================================================================

@login_required
@require_POST
def recycle_list_leads(request, list_id):
    """
    Recycle eligible leads in a list according to active rules
    """
    from leads.models import LeadList, LeadRecycleRule, LeadRecycleLog, Lead
    
    try:
        lead_list = get_object_or_404(LeadList, id=list_id)
        
        # Get active rules for this list
        rules = LeadRecycleRule.objects.filter(
            Q(lead_list=lead_list) | Q(lead_list__isnull=True),
            is_active=True
        )
        
        if not rules.exists():
            return JsonResponse({
                'success': False,
                'error': 'No active recycle rules found'
            })
        
        total_recycled = 0
        
        for rule in rules:
            # Get eligible leads
            eligible = rule.get_eligible_leads().filter(lead_list=lead_list)
            
            for lead in eligible:
                # Create log
                LeadRecycleLog.objects.create(
                    rule=rule,
                    lead=lead,
                    old_status=lead.status,
                    new_status=rule.target_status,
                    old_call_count=lead.call_count
                )
                
                # Update lead
                lead.status = rule.target_status
                lead.save(update_fields=['status'])
                
                total_recycled += 1
            
            # Update rule stats
            rule.last_run = timezone.now()
            rule.total_recycled += eligible.count()
            rule.save(update_fields=['last_run', 'total_recycled'])
        
        logger.info(f"Recycled {total_recycled} leads in list {list_id}")
        
        return JsonResponse({
            'success': True,
            'recycled_count': total_recycled,
            'message': f'Successfully recycled {total_recycled} leads'
        })
        
    except Exception as e:
        logger.error(f"Error recycling leads: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to recycle leads'
        })


@login_required
@manager_required
def create_recycle_rule(request):
    """
    Create a new lead recycle rule
    """
    from leads.models import LeadList, LeadRecycleRule
    from leads.forms import LeadRecycleRuleForm
    from campaigns.models import Campaign
    
    if request.method == 'POST':
        form = LeadRecycleRuleForm(request.POST)
        if form.is_valid():
            rule = form.save()
            messages.success(request, f'Recycle rule "{rule.name}" created successfully.')
            return redirect('leads:recycle_rules')
    else:
        form = LeadRecycleRuleForm()
        
        # Pre-fill list if provided
        list_id = request.GET.get('list')
        if list_id:
            form.fields['lead_list'].initial = list_id
    
    context = {
        'form': form,
        'lead_lists': LeadList.objects.all(),
        'campaigns': Campaign.objects.filter(status='active'),
    }
    
    return render(request, 'leads/recycle_rule_form.html', context)


@login_required
@manager_required
def recycle_rules_list(request):
    """
    List all recycle rules
    """
    from leads.models import LeadRecycleRule
    
    rules = LeadRecycleRule.objects.select_related(
        'campaign', 'lead_list'
    ).order_by('-is_active', 'name')
    
    context = {
        'rules': rules,
    }
    
    return render(request, 'leads/recycle_rules_list.html', context)


@login_required
@manager_required
def toggle_recycle_rule(request, rule_id):
    """
    Toggle a recycle rule active/inactive
    """
    from leads.models import LeadRecycleRule
    
    rule = get_object_or_404(LeadRecycleRule, id=rule_id)
    rule.is_active = not rule.is_active
    rule.save(update_fields=['is_active'])
    
    status = 'activated' if rule.is_active else 'deactivated'
    messages.success(request, f'Rule "{rule.name}" {status}.')
    
    return redirect('leads:recycle_rules')


@login_required
@manager_required
def delete_recycle_rule(request, rule_id):
    """
    Delete a recycle rule
    """
    from leads.models import LeadRecycleRule
    
    rule = get_object_or_404(LeadRecycleRule, id=rule_id)
    name = rule.name
    rule.delete()
    
    messages.success(request, f'Rule "{name}" deleted.')
    return redirect('leads:recycle_rules')


# ============================================================================
# URL Patterns to Add
# ============================================================================
"""
Add these URL patterns to leads/urls.py:

# Phase 2.4: Progress Tracking
path('lists/<int:list_id>/progress/', views.lead_list_detail_with_progress, name='list_progress'),
path('api/lists/<int:list_id>/progress/', views.lead_list_progress_api, name='list_progress_api'),

# Phase 2.4: Recycling
path('lists/<int:list_id>/recycle/', views.recycle_list_leads, name='recycle_list_leads'),
path('recycle-rules/', views.recycle_rules_list, name='recycle_rules'),
path('recycle-rules/create/', views.create_recycle_rule, name='create_recycle_rule'),
path('recycle-rules/<int:rule_id>/toggle/', views.toggle_recycle_rule, name='toggle_recycle_rule'),
path('recycle-rules/<int:rule_id>/delete/', views.delete_recycle_rule, name='delete_recycle_rule'),
"""
