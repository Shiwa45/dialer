"""
Phase 4 Views - Analytics & Monitoring

This module contains all views for Phase 4 features:
- Analytics dashboard and API endpoints
- Supervisor monitoring endpoints
- Report export functionality
"""

import json
import logging
from datetime import datetime, timedelta

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone

from reports.analytics import AnalyticsEngine, ReportExporter
from calls.quality_scoring import (
    CallScorer, AgentScorecard, SupervisorMonitor, MonitorMode
)

logger = logging.getLogger(__name__)


# ============================================================================
# Decorator for supervisor access
# ============================================================================

def supervisor_required(view_func):
    """Decorator to require supervisor permissions"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Not authenticated'}, status=401)
        
        is_supervisor = (
            request.user.is_staff or
            request.user.is_superuser or
            request.user.groups.filter(name__in=['Supervisor', 'Manager']).exists()
        )
        
        if not is_supervisor:
            return JsonResponse({'error': 'Supervisor access required'}, status=403)
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


# ============================================================================
# Analytics Dashboard Views
# ============================================================================

@login_required
@supervisor_required
def analytics_dashboard(request):
    """
    Main analytics dashboard view
    
    Phase 4.3: Comprehensive analytics with trends, ROI, and leaderboards
    """
    from campaigns.models import Campaign
    
    engine = AnalyticsEngine()
    
    # Get filters
    campaign_id = request.GET.get('campaign')
    days = int(request.GET.get('days', 30))
    
    # Build context
    context = {
        'trends': engine.get_call_trends(
            campaign_id=int(campaign_id) if campaign_id else None,
            days=days
        ),
        'hourly': engine.get_hourly_performance(
            campaign_id=int(campaign_id) if campaign_id else None,
            days=days
        ),
        'leaderboard': engine.get_agent_leaderboard(
            campaign_id=int(campaign_id) if campaign_id else None,
            days=days
        )[:10],
        'campaigns': Campaign.objects.filter(status='active'),
        'days': days,
        'selected_campaign_id': int(campaign_id) if campaign_id else None,
    }
    
    # Add ROI if campaign selected
    if campaign_id:
        context['roi'] = engine.get_campaign_roi(int(campaign_id), days)
    
    return render(request, 'reports/analytics_dashboard.html', context)


@login_required
@supervisor_required
@require_GET
def analytics_trends_api(request):
    """API endpoint for call trends data"""
    engine = AnalyticsEngine()
    
    campaign_id = request.GET.get('campaign')
    days = int(request.GET.get('days', 30))
    granularity = request.GET.get('granularity', 'day')
    
    data = engine.get_call_trends(
        campaign_id=int(campaign_id) if campaign_id else None,
        days=days,
        granularity=granularity
    )
    
    return JsonResponse({'success': True, 'data': data})


@login_required
@supervisor_required
@require_GET
def analytics_hourly_api(request):
    """API endpoint for hourly performance data"""
    engine = AnalyticsEngine()
    
    campaign_id = request.GET.get('campaign')
    days = int(request.GET.get('days', 7))
    
    data = engine.get_hourly_performance(
        campaign_id=int(campaign_id) if campaign_id else None,
        days=days
    )
    
    return JsonResponse({'success': True, 'data': data})


@login_required
@supervisor_required
@require_GET
def leaderboard_api(request):
    """API endpoint for agent leaderboard"""
    engine = AnalyticsEngine()
    
    campaign_id = request.GET.get('campaign')
    days = int(request.GET.get('days', 7))
    metric = request.GET.get('metric', 'sales')
    
    data = engine.get_agent_leaderboard(
        campaign_id=int(campaign_id) if campaign_id else None,
        days=days,
        metric=metric
    )
    
    return JsonResponse({'success': True, 'leaderboard': data})


@login_required
@supervisor_required
@require_GET
def roi_api(request):
    """API endpoint for campaign ROI"""
    engine = AnalyticsEngine()
    
    campaign_id = request.GET.get('campaign')
    days = int(request.GET.get('days', 30))
    
    if not campaign_id:
        return JsonResponse({'success': False, 'error': 'Campaign ID required'})
    
    data = engine.get_campaign_roi(int(campaign_id), days)
    
    return JsonResponse({'success': True, 'data': data})


@login_required
@supervisor_required
@require_GET
def compare_periods_api(request):
    """API endpoint for period comparison"""
    engine = AnalyticsEngine()
    
    campaign_id = request.GET.get('campaign')
    
    if not campaign_id:
        return JsonResponse({'success': False, 'error': 'Campaign ID required'})
    
    # Parse dates
    try:
        p1_start = datetime.fromisoformat(request.GET.get('p1_start'))
        p1_end = datetime.fromisoformat(request.GET.get('p1_end'))
        p2_start = datetime.fromisoformat(request.GET.get('p2_start'))
        p2_end = datetime.fromisoformat(request.GET.get('p2_end'))
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid date format'})
    
    data = engine.compare_periods(
        int(campaign_id),
        p1_start, p1_end,
        p2_start, p2_end
    )
    
    return JsonResponse({'success': True, 'data': data})


@login_required
@supervisor_required
@require_GET
def export_report(request):
    """Export report to Excel or CSV"""
    engine = AnalyticsEngine()
    exporter = ReportExporter()
    
    report_type = request.GET.get('type', 'trends')
    format_type = request.GET.get('format', 'xlsx')
    campaign_id = request.GET.get('campaign')
    days = int(request.GET.get('days', 30))
    
    # Get data based on report type
    if report_type == 'trends':
        data = engine.get_call_trends(
            campaign_id=int(campaign_id) if campaign_id else None,
            days=days
        )
    elif report_type == 'leaderboard':
        data = engine.get_agent_leaderboard(
            campaign_id=int(campaign_id) if campaign_id else None,
            days=days
        )
    elif report_type == 'hourly':
        data = engine.get_hourly_performance(
            campaign_id=int(campaign_id) if campaign_id else None,
            days=days
        )
    elif report_type == 'roi' and campaign_id:
        data = engine.get_campaign_roi(int(campaign_id), days)
    else:
        return HttpResponse('Invalid report type', status=400)
    
    # Generate filename
    filename = f"{report_type}_report_{timezone.now().strftime('%Y%m%d')}"
    
    # Export based on format
    if format_type == 'xlsx':
        buffer = exporter.export_to_excel(data, report_type)
        return exporter.get_http_response(
            buffer,
            f"{filename}.xlsx",
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    elif format_type == 'csv':
        if isinstance(data, list):
            buffer = exporter.export_to_csv(data)
            return exporter.get_http_response(
                buffer,
                f"{filename}.csv",
                'text/csv'
            )
        else:
            return HttpResponse('CSV export not supported for this report type', status=400)
    
    return HttpResponse('Invalid format', status=400)


# ============================================================================
# Supervisor Monitoring Views
# ============================================================================

@login_required
@supervisor_required
def monitoring_dashboard(request):
    """
    Supervisor monitoring dashboard
    
    Phase 4.2: Real-time agent monitoring with listen/whisper/barge
    """
    from campaigns.models import Campaign
    
    context = {
        'campaigns': Campaign.objects.filter(status='active')
    }
    
    return render(request, 'agents/supervisor_monitoring.html', context)


@login_required
@supervisor_required
@require_GET
def monitoring_agents_api(request):
    """API endpoint to get agents for monitoring"""
    from users.models import AgentStatus
    from campaigns.models import CampaignAgent
    from calls.models import CallLog
    
    campaign_id = request.GET.get('campaign')
    
    # Build agent query
    agents_query = AgentStatus.objects.select_related(
        'user', 'current_campaign'
    ).exclude(status='offline')
    
    # Filter by campaign if specified
    if campaign_id:
        agent_ids = CampaignAgent.objects.filter(
            campaign_id=campaign_id,
            is_active=True
        ).values_list('user_id', flat=True)
        agents_query = agents_query.filter(user_id__in=agent_ids)
    
    now = timezone.now()
    agents = []
    
    for agent_status in agents_query:
        user = agent_status.user
        
        # Get current call if busy
        current_call = None
        if agent_status.status == 'busy':
            call_log = CallLog.objects.filter(
                agent=user,
                end_time__isnull=True
            ).first()
            
            if call_log:
                duration = 0
                if call_log.answer_time:
                    duration = int((now - call_log.answer_time).total_seconds())
                
                current_call = {
                    'id': call_log.id,
                    'phone_number': call_log.phone_number,
                    'lead_name': str(call_log.lead) if call_log.lead else None,
                    'duration': duration,
                    'quality_score': call_log.quality_score
                }
        
        # Get extension
        extension = None
        if hasattr(user, 'phone'):
            extension = user.phone.extension
        
        agents.append({
            'id': user.id,
            'name': user.get_full_name() or user.username,
            'username': user.username,
            'extension': extension,
            'status': agent_status.status,
            'campaign': agent_status.current_campaign.name if agent_status.current_campaign else None,
            'current_call': current_call
        })
    
    # Calculate stats
    stats = {
        'total': len(agents),
        'available': sum(1 for a in agents if a['status'] == 'available'),
        'busy': sum(1 for a in agents if a['status'] == 'busy'),
        'paused': sum(1 for a in agents if a['status'] in ['break', 'lunch', 'training'])
    }
    
    return JsonResponse({
        'success': True,
        'agents': agents,
        'stats': stats
    })


@login_required
@supervisor_required
@require_POST
def start_monitoring(request):
    """Start monitoring an agent's call"""
    from telephony.services import get_asterisk_service
    
    try:
        data = json.loads(request.body)
        agent_id = data.get('agent_id')
        mode = data.get('mode', 'listen')
        
        if not agent_id:
            return JsonResponse({'success': False, 'error': 'Agent ID required'})
        
        # Get Asterisk service
        asterisk_service = get_asterisk_service()
        
        # Create monitor instance
        monitor = SupervisorMonitor(asterisk_service)
        
        # Get channels
        supervisor_channel = _get_supervisor_channel(request.user)
        agent_channel = _get_agent_channel(agent_id)
        
        if not agent_channel:
            return JsonResponse({'success': False, 'error': 'Agent not on a call'})
        
        # Start monitoring
        result = monitor.start_monitoring(
            supervisor_channel=supervisor_channel,
            target_channel=agent_channel,
            mode=MonitorMode(mode)
        )
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error starting monitoring: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@supervisor_required
@require_POST
def stop_monitoring(request):
    """Stop monitoring session"""
    from telephony.services import get_asterisk_service
    
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        
        if not session_id:
            return JsonResponse({'success': False, 'error': 'Session ID required'})
        
        asterisk_service = get_asterisk_service()
        monitor = SupervisorMonitor(asterisk_service)
        
        result = monitor.stop_monitoring(session_id)
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error stopping monitoring: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@supervisor_required
@require_POST
def switch_monitoring_mode(request):
    """Switch monitoring mode (listen/whisper/barge)"""
    from telephony.services import get_asterisk_service
    
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        mode = data.get('mode')
        
        if not session_id or not mode:
            return JsonResponse({'success': False, 'error': 'Session ID and mode required'})
        
        asterisk_service = get_asterisk_service()
        monitor = SupervisorMonitor(asterisk_service)
        
        result = monitor.change_mode(session_id, MonitorMode(mode))
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error switching mode: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


# ============================================================================
# Agent Scorecard Views
# ============================================================================

@login_required
@supervisor_required
@require_GET
def agent_scorecard_api(request):
    """Get agent performance scorecard"""
    agent_id = request.GET.get('agent_id')
    
    if not agent_id:
        return JsonResponse({'success': False, 'error': 'Agent ID required'})
    
    scorecard = AgentScorecard(int(agent_id))
    
    return JsonResponse({
        'success': True,
        'daily': scorecard.get_daily_metrics(),
        'weekly': scorecard.get_weekly_summary(),
        'ranking': scorecard.get_quality_ranking()
    })


@login_required
def my_scorecard(request):
    """Agent viewing their own scorecard"""
    scorecard = AgentScorecard(request.user.id)
    
    return JsonResponse({
        'success': True,
        'daily': scorecard.get_daily_metrics(),
        'weekly': scorecard.get_weekly_summary(),
        'ranking': scorecard.get_quality_ranking()
    })


# ============================================================================
# Dialer Status Views
# ============================================================================

@login_required
@supervisor_required
@require_GET
def dialer_status_api(request):
    """Get predictive dialer status for all campaigns"""
    from campaigns.predictive_dialer import DialerManager
    
    statuses = DialerManager.get_all_campaigns_status()
    
    return JsonResponse({
        'success': True,
        'campaigns': statuses
    })


@login_required
@supervisor_required
@require_GET
def campaign_dialer_status_api(request, campaign_id):
    """Get predictive dialer status for specific campaign"""
    from campaigns.predictive_dialer import DialerManager
    
    dialer = DialerManager.get_dialer(campaign_id)
    status = dialer.get_dialer_status()
    
    return JsonResponse({
        'success': True,
        'status': status
    })


# ============================================================================
# Helper Functions
# ============================================================================

def _get_supervisor_channel(user):
    """Get or create a channel for the supervisor"""
    # This would typically originate a call to the supervisor's phone
    # For now, return a placeholder
    if hasattr(user, 'phone') and user.phone:
        return f"PJSIP/{user.phone.extension}"
    return None


def _get_agent_channel(agent_id):
    """Get the agent's current active channel"""
    from calls.models import CallLog
    from django.contrib.auth.models import User
    
    try:
        user = User.objects.get(id=agent_id)
        
        # Find active call
        call_log = CallLog.objects.filter(
            agent=user,
            end_time__isnull=True
        ).first()
        
        if call_log and call_log.agent_channel:
            return call_log.agent_channel
        
        return None
        
    except User.DoesNotExist:
        return None
