"""
Enhanced Lead Recycling Views - Phase 2.3

Complete status breakdown and recycling interface
"""

import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q
from django.utils import timezone
from django.contrib import messages

from core.decorators import supervisor_required
from leads.models import Lead, LeadList, LeadRecycleRule
from campaigns.models import Campaign

logger = logging.getLogger(__name__)


@login_required
@supervisor_required
def lead_recycling_page(request, list_id):
    """
    Enhanced lead recycling page with complete status breakdown
    
    Phase 2.3: Shows ALL statuses including NULL/empty
    """
    try:
        lead_list = get_object_or_404(LeadList, id=list_id)
        
        # Get ALL status counts including NULL
        status_breakdown = Lead.objects.filter(
            lead_list=lead_list
        ).values('status').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Count leads with NULL/empty status
        null_status_count = Lead.objects.filter(
            lead_list=lead_list,
            status__isnull=True
        ).count() + Lead.objects.filter(
            lead_list=lead_list,
            status=''
        ).count()
        
        # Build comprehensive status dict
        status_dict = {}
        for item in status_breakdown:
            status = item['status'] or 'no_status'
            status_dict[status] = item['count']
        
        if null_status_count > 0:
            status_dict['no_status'] = null_status_count
        
        # Get leads with dial attempts but still 'new' status (problematic)
        problematic_leads = Lead.objects.filter(
            lead_list=lead_list,
            dial_attempts__gt=0,
            status='new'
        ).count()
        
        # Get leads with calls but no dial tracking
        from calls.models import CallLog
        leads_with_calls = CallLog.objects.filter(
            lead__lead_list=lead_list
        ).values_list('lead_id', flat=True).distinct()
        
        missing_tracking = Lead.objects.filter(
            id__in=leads_with_calls,
            dial_attempts=0
        ).count()
        
        # Calculate recyclable counts by status
        recyclable_statuses = [
            'no_answer', 'busy', 'failed', 'dropped', 
            'congestion', 'callback', 'no_status'
        ]
        
        recyclable_count = sum(
            status_dict.get(status, 0) 
            for status in recyclable_statuses
        )
        
        # Get active recycling rules for this list
        active_rules = LeadRecycleRule.objects.filter(
            Q(lead_list=lead_list) | Q(lead_list__isnull=True),
            is_active=True
        ).order_by('-created_at')
        
        context = {
            'lead_list': lead_list,
            'status_breakdown': status_dict,
            'total_leads': lead_list.total_leads,
            'recyclable_count': recyclable_count,
            'problematic_leads': problematic_leads,
            'missing_tracking': missing_tracking,
            'active_rules': active_rules,
            'recyclable_statuses': recyclable_statuses,
        }
        
        return render(request, 'leads/lead_recycling.html', context)
        
    except Exception as e:
        logger.error(f"Error in lead_recycling_page: {e}", exc_info=True)
        messages.error(request, f'Error loading recycling page: {str(e)}')
        return redirect('leads:lead_list_list')


@login_required
@supervisor_required
@require_http_methods(["POST"])
def recycle_leads_action(request, list_id):
    """
    Execute lead recycling action
    
    Phase 2.3: Recycle selected statuses including no_status
    """
    try:
        lead_list = get_object_or_404(LeadList, id=list_id)
        
        # Get selected statuses to recycle
        selected_statuses = request.POST.getlist('selected_statuses')
        target_status = request.POST.get('target_status', 'new')
        reset_dial_count = request.POST.get('reset_dial_count') == 'true'
        
        if not selected_statuses:
            return JsonResponse({
                'success': False,
                'error': 'No statuses selected for recycling'
            })
        
        # Build query
        query = Q(lead_list=lead_list)
        
        # Handle 'no_status' specially
        if 'no_status' in selected_statuses:
            query &= (Q(status__isnull=True) | Q(status=''))
            selected_statuses.remove('no_status')
        
        if selected_statuses:
            query |= Q(lead_list=lead_list, status__in=selected_statuses)
        
        leads_to_recycle = Lead.objects.filter(query)
        
        count = leads_to_recycle.count()
        
        # Update leads
        update_fields = {
            'status': target_status,
            'last_status_change': timezone.now()
        }
        
        if reset_dial_count:
            update_fields['dial_attempts'] = 0
            update_fields['answered_count'] = 0
            update_fields['call_count'] = 0
            update_fields['last_dial_attempt'] = None
        
        leads_to_recycle.update(**update_fields)
        
        # Log the recycling action
        from leads.models import LeadRecycleLog
        try:
            # Log a sample of recycled leads
            for lead in leads_to_recycle[:100]:
                LeadRecycleLog.objects.create(
                    lead=lead,
                    old_status=lead.status,
                    new_status=target_status,
                    recycled_by=request.user,
                    reason='Manual recycling'
                )
        except Exception as e:
            logger.warning(f"Could not log recycling: {e}")
        
        logger.info(
            f"Recycled {count} leads in list {lead_list.name} "
            f"by {request.user.username}"
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully recycled {count} leads',
            'count': count
        })
        
    except Exception as e:
        logger.error(f"Error recycling leads: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@supervisor_required
@require_http_methods(["POST"])
def fix_problematic_leads_action(request, list_id):
    """
    Fix leads with missing or incorrect status
    
    Phase 2.1: Use LeadStatusService to fix problematic leads
    """
    try:
        lead_list = get_object_or_404(LeadList, id=list_id)
        
        from leads.lead_status_service import get_lead_status_service
        
        service = get_lead_status_service()
        
        # Fix leads in this list
        result = service.fix_leads_with_missing_status(
            campaign_id=lead_list.assigned_campaign_id if lead_list.assigned_campaign else None,
            dry_run=False
        )
        
        if 'error' in result:
            return JsonResponse({
                'success': False,
                'error': result['error']
            })
        
        return JsonResponse({
            'success': True,
            'message': f'Fixed {result["leads_fixed"]} leads',
            'stats': result
        })
        
    except Exception as e:
        logger.error(f"Error fixing problematic leads: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@supervisor_required
def lead_status_report(request, list_id):
    """
    Detailed status report for lead list
    
    Shows:
    - Complete status breakdown
    - Dial attempt distribution
    - Problematic leads
    - Recycling recommendations
    """
    try:
        lead_list = get_object_or_404(LeadList, id=list_id)
        
        # Status breakdown
        status_breakdown = Lead.objects.filter(
            lead_list=lead_list
        ).values('status').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Dial attempts distribution
        dial_distribution = Lead.objects.filter(
            lead_list=lead_list
        ).values('dial_attempts').annotate(
            count=Count('id')
        ).order_by('dial_attempts')
        
        # Problematic leads analysis
        from calls.models import CallLog
        
        # Leads with calls but no status change
        leads_with_calls = CallLog.objects.filter(
            lead__lead_list=lead_list
        ).values_list('lead_id', flat=True).distinct()
        
        problematic = {
            'dial_but_new': Lead.objects.filter(
                lead_list=lead_list,
                dial_attempts__gt=0,
                status='new'
            ).count(),
            'calls_but_no_tracking': Lead.objects.filter(
                id__in=leads_with_calls,
                dial_attempts=0
            ).count(),
            'high_attempts_no_answer': Lead.objects.filter(
                lead_list=lead_list,
                dial_attempts__gte=5,
                answered_count=0
            ).count(),
            'never_contacted': Lead.objects.filter(
                lead_list=lead_list,
                dial_attempts__gt=0,
                answered_count=0
            ).count(),
        }
        
        # Recycling recommendations
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(hours=24)
        
        recommendations = {
            'no_answer_retry': Lead.objects.filter(
                lead_list=lead_list,
                status='no_answer',
                dial_attempts__lt=3,
                last_dial_attempt__lt=cutoff
            ).count(),
            'busy_retry': Lead.objects.filter(
                lead_list=lead_list,
                status='busy',
                dial_attempts__lt=3,
                last_dial_attempt__lt=cutoff
            ).count(),
            'callback_due': Lead.objects.filter(
                lead_list=lead_list,
                status='callback',
                last_contact_date__lt=cutoff
            ).count(),
        }
        
        context = {
            'lead_list': lead_list,
            'status_breakdown': status_breakdown,
            'dial_distribution': dial_distribution,
            'problematic': problematic,
            'recommendations': recommendations,
        }
        
        return render(request, 'leads/lead_status_report.html', context)
        
    except Exception as e:
        logger.error(f"Error generating status report: {e}", exc_info=True)
        messages.error(request, f'Error generating report: {str(e)}')
        return redirect('leads:lead_list_detail', pk=list_id)
