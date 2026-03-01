"""
campaigns/views_ai.py – Phase 8.3: AI Agent Configuration Views
================================================================

Views for managing AI agent configuration per campaign.
"""

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.utils import timezone

from campaigns.models import Campaign

logger = logging.getLogger(__name__)


def _is_manager(user):
    """Check if user is manager/supervisor."""
    try:
        return user.is_staff or user.profile.is_manager() or user.profile.is_supervisor()
    except Exception:
        return user.is_staff


@login_required
@user_passes_test(_is_manager)
@require_http_methods(['GET', 'POST'])
def ai_agent_config(request, campaign_id):
    """
    AI Agent configuration page for a campaign.
    
    GET: Show configuration form
    POST: Save configuration
    """
    campaign = get_object_or_404(Campaign, id=campaign_id)
    
    if request.method == 'POST':
        try:
            # Update AI configuration
            campaign.ai_enabled = request.POST.get('ai_enabled') == '1'
            campaign.ai_language = request.POST.get('ai_language', 'hi-IN')
            campaign.ai_agent_name = request.POST.get('ai_agent_name', 'AI सहायक')
            campaign.ai_company_name = request.POST.get('ai_company_name', '')
            campaign.ai_voice = request.POST.get('ai_voice', 'aditya')
            campaign.ai_max_turns = int(request.POST.get('ai_max_turns', 15))
            campaign.ai_fallback_to_human = request.POST.get('ai_fallback_to_human') == 'on'
            
            # Capabilities
            campaign.ai_can_book_appointments = request.POST.get('ai_can_book_appointments') == 'on'
            campaign.ai_can_cancel_appointments = request.POST.get('ai_can_cancel_appointments') == 'on'
            campaign.ai_can_collect_feedback = request.POST.get('ai_can_collect_feedback') == 'on'
            
            # Set enabled timestamp if just enabled
            if campaign.ai_enabled and not campaign.ai_enabled_at:
                campaign.ai_enabled_at = timezone.now()
            
            campaign.save()
            
            messages.success(request, 'AI Agent configuration saved successfully!')
            logger.info(f"AI config updated for campaign {campaign_id} by {request.user.username}")
            
            return redirect('campaigns:ai_agent_config', campaign_id=campaign.id)
        
        except Exception as e:
            logger.error(f"AI config save error: {e}", exc_info=True)
            messages.error(request, f'Error saving configuration: {str(e)}')
    
    # GET request - show form
    return render(request, 'campaigns/ai_agent_config.html', {
        'campaign': campaign,
    })


@login_required
@user_passes_test(_is_manager)
@require_POST
def test_ai_call(request, campaign_id):
    """
    Initiate a test AI call to verify configuration.
    
    POST data: {'phone_number': '+919999999999'}
    """
    campaign = get_object_or_404(Campaign, id=campaign_id)
    
    if not campaign.ai_enabled:
        return JsonResponse({
            'success': False,
            'error': 'AI agent is not enabled for this campaign'
        }, status=400)
    
    try:
        import json
        data = json.loads(request.body)
        phone_number = data.get('phone_number', '').strip()
        
        if not phone_number:
            return JsonResponse({
                'success': False,
                'error': 'Phone number is required'
            }, status=400)
        
        # Create a test lead
        from leads.models import Lead
        test_lead, created = Lead.objects.get_or_create(
            phone_number=phone_number,
            defaults={
                'first_name': 'Test',
                'last_name': 'AI Call',
                'status': 'new',
            }
        )
        
        # Queue AI call via Celery
        from campaigns.tasks import make_ai_outbound_call
        
        result = make_ai_outbound_call.delay(
            lead_id=test_lead.id,
            campaign_id=campaign.id,
        )
        
        logger.info(f"Test AI call queued: campaign={campaign_id}, "
                   f"phone={phone_number}, task_id={result.id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Test call initiated',
            'task_id': result.id,
            'lead_id': test_lead.id,
        })
    
    except Exception as e:
        logger.error(f"Test call error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(_is_manager)
def ai_call_history(request, campaign_id):
    """
    Show AI call history for a campaign.
    """
    campaign = get_object_or_404(Campaign, id=campaign_id)
    
    from calls.models import CallLog
    from django.core.paginator import Paginator
    
    # Get AI calls
    calls = CallLog.objects.filter(
        campaign=campaign,
        handled_by_ai=True,
    ).select_related('lead').order_by('-start_time')
    
    # Pagination
    paginator = Paginator(calls, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'campaigns/ai_call_history.html', {
        'campaign': campaign,
        'page_obj': page_obj,
    })


@login_required
@user_passes_test(_is_manager)
def ai_call_transcript(request, call_id):
    """
    View full AI conversation transcript for a call.
    """
    from calls.models import CallLog
    
    call_log = get_object_or_404(CallLog, id=call_id)
    
    # Check permission
    if not request.user.is_staff:
        # Check if user has access to this campaign
        if call_log.campaign.created_by != request.user:
            messages.error(request, 'You do not have permission to view this call')
            return redirect('campaigns:detail', campaign_id=call_log.campaign.id)
    
    transcript = call_log.ai_conversation_transcript or []
    
    return render(request, 'campaigns/ai_call_transcript.html', {
        'call_log': call_log,
        'transcript': transcript,
    })


@login_required
@user_passes_test(_is_manager)
def toggle_ai_enabled(request, campaign_id):
    """
    Quick toggle AI enabled/disabled via AJAX.
    
    POST: Toggle state
    """
    campaign = get_object_or_404(Campaign, id=campaign_id)
    
    if request.method == 'POST':
        campaign.ai_enabled = not campaign.ai_enabled
        
        if campaign.ai_enabled and not campaign.ai_enabled_at:
            campaign.ai_enabled_at = timezone.now()
        
        campaign.save()
        
        logger.info(f"AI {'enabled' if campaign.ai_enabled else 'disabled'} "
                   f"for campaign {campaign_id} by {request.user.username}")
        
        return JsonResponse({
            'success': True,
            'ai_enabled': campaign.ai_enabled,
            'message': f"AI Agent {'enabled' if campaign.ai_enabled else 'disabled'}",
        })
    
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)


@login_required
@user_passes_test(_is_manager)
def ai_stats_api(request, campaign_id):
    """
    Get AI stats for a campaign (AJAX endpoint for live updates).
    """
    campaign = get_object_or_404(Campaign, id=campaign_id)
    
    # Calculate success rate
    success_rate = 0
    if campaign.ai_total_calls > 0:
        success_rate = round(
            (campaign.ai_successful_calls / campaign.ai_total_calls) * 100,
            1
        )
    
    return JsonResponse({
        'success': True,
        'stats': {
            'total_calls': campaign.ai_total_calls,
            'successful_calls': campaign.ai_successful_calls,
            'transferred_calls': campaign.ai_transferred_calls,
            'appointments_booked': campaign.ai_appointments_booked,
            'success_rate': success_rate,
            'enabled': campaign.ai_enabled,
            'last_used': campaign.ai_last_used_at.isoformat() if campaign.ai_last_used_at else None,
        }
    })
