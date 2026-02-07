"""
Real-time Reports - Phase 3.2

This module provides GoAutodial-style real-time reporting:
1. Live agent grid with status, current call, talk time
2. Campaign metrics: calls/hour, contact rate, conversion rate
3. WebSocket consumer for real-time updates
"""

import logging
from datetime import timedelta
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Q, F
from django.db.models.functions import TruncHour

from core.decorators import supervisor_required

logger = logging.getLogger(__name__)


# ============================================================================
# Real-time Dashboard Views
# ============================================================================

@login_required
@supervisor_required
def realtime_dashboard(request):
    """
    Main real-time monitoring dashboard
    """
    from campaigns.models import Campaign
    
    # Get active campaigns for filter
    campaigns = Campaign.objects.filter(status='active').order_by('name')
    
    # Get selected campaign
    campaign_id = request.GET.get('campaign')
    selected_campaign = None
    if campaign_id:
        selected_campaign = Campaign.objects.filter(id=campaign_id).first()
    
    context = {
        'campaigns': campaigns,
        'selected_campaign': selected_campaign,
    }
    
    return render(request, 'reports/realtime_dashboard.html', context)


@login_required
@supervisor_required
@require_http_methods(["GET"])
def realtime_agents_api(request):
    """
    API endpoint for real-time agent data
    
    Returns current status of all agents with call info
    """
    from users.models import AgentStatus
    from calls.models import CallLog
    from campaigns.models import Campaign, CampaignAgent
    
    campaign_id = request.GET.get('campaign')
    
    try:
        # Get agent statuses
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
        agents_data = []
        
        for agent in agents_query:
            # Calculate time in current status
            status_time = 0
            if agent.status_changed_at:
                status_time = int((now - agent.status_changed_at).total_seconds())
            
            # Calculate talk time if on call
            talk_time = 0
            if agent.status == 'busy' and agent.call_start_time:
                talk_time = int((now - agent.call_start_time).total_seconds())
            
            # Get current call info
            current_call = None
            if agent.current_call_id:
                call = CallLog.objects.filter(id=agent.current_call_id).first()
                if call:
                    current_call = {
                        'number': call.called_number,
                        'lead_name': f"{call.lead.first_name} {call.lead.last_name}" if call.lead else None,
                        'duration': talk_time
                    }
            
            agents_data.append({
                'id': agent.user.id,
                'username': agent.user.username,
                'name': agent.user.get_full_name() or agent.user.username,
                'status': agent.status,
                'status_time': status_time,
                'status_time_formatted': _format_duration(status_time),
                'campaign': agent.current_campaign.name if agent.current_campaign else None,
                'current_call': current_call,
                'extension': getattr(agent.user, 'phone', {}).extension if hasattr(agent.user, 'phone') else None
            })
        
        # Sort by status (busy first, then available, then others)
        status_order = {'busy': 0, 'available': 1, 'wrapup': 2}
        agents_data.sort(key=lambda x: (status_order.get(x['status'], 99), x['name']))
        
        return JsonResponse({
            'success': True,
            'agents': agents_data,
            'timestamp': now.isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in realtime_agents_api: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch agent data'
        })


@login_required
@supervisor_required
@require_http_methods(["GET"])
def realtime_campaign_stats_api(request):
    """
    API endpoint for real-time campaign statistics
    """
    from campaigns.models import Campaign
    from calls.models import CallLog
    from users.models import AgentStatus
    
    campaign_id = request.GET.get('campaign')
    
    try:
        now = timezone.now()
        today = now.date()
        hour_ago = now - timedelta(hours=1)
        
        # Base call query
        calls_query = CallLog.objects.filter(start_time__date=today)
        
        if campaign_id:
            calls_query = calls_query.filter(campaign_id=campaign_id)
        
        # Calculate metrics
        total_calls = calls_query.count()
        answered_calls = calls_query.filter(
            Q(call_status='answered') | Q(answer_time__isnull=False)
        ).count()
        dropped_calls = calls_query.filter(call_status='dropped').count()
        
        # Sales (disposition marked as sale)
        sales = calls_query.filter(disposition__is_sale=True).count()
        
        # Calls in last hour
        calls_last_hour = calls_query.filter(start_time__gte=hour_ago).count()
        
        # Average call duration
        avg_duration = calls_query.filter(
            talk_duration__gt=0
        ).aggregate(avg=Avg('talk_duration'))['avg'] or 0
        
        # Calculate rates
        contact_rate = (answered_calls / total_calls * 100) if total_calls > 0 else 0
        conversion_rate = (sales / answered_calls * 100) if answered_calls > 0 else 0
        drop_rate = (dropped_calls / total_calls * 100) if total_calls > 0 else 0
        
        # Agent counts
        agent_query = AgentStatus.objects.exclude(status='offline')
        if campaign_id:
            from campaigns.models import CampaignAgent
            agent_ids = CampaignAgent.objects.filter(
                campaign_id=campaign_id,
                is_active=True
            ).values_list('user_id', flat=True)
            agent_query = agent_query.filter(user_id__in=agent_ids)
        
        agents_available = agent_query.filter(status='available').count()
        agents_busy = agent_query.filter(status='busy').count()
        agents_paused = agent_query.filter(status__in=['break', 'lunch', 'training', 'meeting']).count()
        agents_wrapup = agent_query.filter(status='wrapup').count()
        
        # Calls per hour trend (last 8 hours)
        calls_trend = []
        for i in range(8, 0, -1):
            hour_start = now - timedelta(hours=i)
            hour_end = now - timedelta(hours=i-1)
            count = calls_query.filter(
                start_time__gte=hour_start,
                start_time__lt=hour_end
            ).count()
            calls_trend.append({
                'hour': hour_start.strftime('%H:%M'),
                'count': count
            })
        
        return JsonResponse({
            'success': True,
            'stats': {
                'total_calls': total_calls,
                'answered_calls': answered_calls,
                'dropped_calls': dropped_calls,
                'sales': sales,
                'calls_per_hour': calls_last_hour,
                'avg_duration': int(avg_duration),
                'avg_duration_formatted': _format_duration(int(avg_duration)),
                'contact_rate': round(contact_rate, 1),
                'conversion_rate': round(conversion_rate, 1),
                'drop_rate': round(drop_rate, 1),
                'agents_available': agents_available,
                'agents_busy': agents_busy,
                'agents_paused': agents_paused,
                'agents_wrapup': agents_wrapup,
                'agents_total': agents_available + agents_busy + agents_paused + agents_wrapup,
                'calls_trend': calls_trend
            },
            'timestamp': now.isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in realtime_campaign_stats_api: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch campaign stats'
        })


@login_required
@supervisor_required
@require_http_methods(["GET"])
def realtime_call_queue_api(request):
    """
    API endpoint for real-time call queue status
    """
    from campaigns.models import Campaign, DialerHopper
    
    campaign_id = request.GET.get('campaign')
    
    try:
        hopper_query = DialerHopper.objects.all()
        
        if campaign_id:
            hopper_query = hopper_query.filter(campaign_id=campaign_id)
        
        # Queue statistics
        queue_new = hopper_query.filter(status='new').count()
        queue_locked = hopper_query.filter(status='locked').count()
        queue_dialing = hopper_query.filter(status='dialing').count()
        
        # Get hopper by campaign
        campaigns_queue = hopper_query.values(
            'campaign__name'
        ).annotate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='new')),
            dialing=Count('id', filter=Q(status='dialing'))
        ).order_by('-total')[:10]
        
        return JsonResponse({
            'success': True,
            'queue': {
                'total': queue_new + queue_locked + queue_dialing,
                'pending': queue_new,
                'locked': queue_locked,
                'dialing': queue_dialing,
                'by_campaign': list(campaigns_queue)
            }
        })
        
    except Exception as e:
        logger.error(f"Error in realtime_call_queue_api: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch queue data'
        })


def _format_duration(seconds):
    """Format seconds as HH:MM:SS or MM:SS"""
    if seconds < 0:
        return "0:00"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


# ============================================================================
# WebSocket Consumer for Real-time Updates
# ============================================================================

"""
Create reports/consumers.py with the following content:
"""

CONSUMER_CODE = '''
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)


class RealtimeReportConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time report updates
    
    Supervisors connect to this to receive live updates about:
    - Agent status changes
    - Call events
    - Campaign statistics
    """
    
    async def connect(self):
        self.user = self.scope['user']
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Check supervisor permission
        if not await self._is_supervisor():
            await self.close()
            return
        
        # Get campaign filter from URL
        self.campaign_id = self.scope['url_route']['kwargs'].get('campaign_id', 'all')
        self.group_name = f'realtime_report_{self.campaign_id}'
        
        # Join group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        # Also join global group for all updates
        await self.channel_layer.group_add(
            'realtime_report_all',
            self.channel_name
        )
        
        await self.accept()
        
        logger.info(f"Supervisor {self.user.username} connected to realtime reports")
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        await self.channel_layer.group_discard(
            'realtime_report_all',
            self.channel_name
        )
    
    async def receive(self, text_data):
        """Handle messages from client"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'request_refresh':
                await self.send_full_update()
            
        except Exception as e:
            logger.error(f"Error handling realtime message: {e}")
    
    async def send_full_update(self):
        """Send complete data refresh"""
        agents = await self._get_agents_data()
        stats = await self._get_campaign_stats()
        
        await self.send(text_data=json.dumps({
            'type': 'full_update',
            'agents': agents,
            'stats': stats,
            'timestamp': timezone.now().isoformat()
        }))
    
    # Event handlers (called from channel layer)
    
    async def agent_update(self, event):
        """Handle agent status update"""
        await self.send(text_data=json.dumps({
            'type': 'agent_update',
            'agent': event['data'],
            'timestamp': timezone.now().isoformat()
        }))
    
    async def call_update(self, event):
        """Handle call event update"""
        await self.send(text_data=json.dumps({
            'type': 'call_update',
            'call': event['data'],
            'timestamp': timezone.now().isoformat()
        }))
    
    async def stats_update(self, event):
        """Handle statistics update"""
        await self.send(text_data=json.dumps({
            'type': 'stats_update',
            'stats': event['data'],
            'timestamp': timezone.now().isoformat()
        }))
    
    @database_sync_to_async
    def _is_supervisor(self):
        return (
            self.user.is_staff or 
            self.user.is_superuser or 
            self.user.groups.filter(name__in=['Supervisor', 'Manager']).exists()
        )
    
    @database_sync_to_async
    def _get_agents_data(self):
        from users.models import AgentStatus
        
        agents = AgentStatus.objects.select_related('user', 'current_campaign').exclude(status='offline')
        
        return [
            {
                'id': a.user.id,
                'name': a.user.get_full_name() or a.user.username,
                'status': a.status,
                'campaign': a.current_campaign.name if a.current_campaign else None
            }
            for a in agents
        ]
    
    @database_sync_to_async
    def _get_campaign_stats(self):
        from calls.models import CallLog
        from django.db.models import Count
        
        today = timezone.now().date()
        
        stats = CallLog.objects.filter(
            start_time__date=today
        ).aggregate(
            total=Count('id'),
            answered=Count('id', filter=Q(answer_time__isnull=False))
        )
        
        return stats
'''


# ============================================================================
# Broadcast Functions (call from ARI worker, views, etc.)
# ============================================================================

def broadcast_agent_update(agent_id, status, campaign_id=None):
    """
    Broadcast agent status update to realtime report subscribers
    
    Call this from:
    - Agent status change views
    - ARI worker on call events
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    
    data = {
        'agent_id': agent_id,
        'status': status,
        'campaign_id': campaign_id,
        'timestamp': timezone.now().isoformat()
    }
    
    # Broadcast to all subscribers
    async_to_sync(channel_layer.group_send)(
        'realtime_report_all',
        {
            'type': 'agent_update',
            'data': data
        }
    )
    
    # Also broadcast to campaign-specific group
    if campaign_id:
        async_to_sync(channel_layer.group_send)(
            f'realtime_report_{campaign_id}',
            {
                'type': 'agent_update',
                'data': data
            }
        )


def broadcast_call_event(call_data, campaign_id=None):
    """
    Broadcast call event to realtime report subscribers
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    
    async_to_sync(channel_layer.group_send)(
        'realtime_report_all',
        {
            'type': 'call_update',
            'data': call_data
        }
    )


# ============================================================================
# URL Patterns
# ============================================================================
"""
Add to reports/urls.py:

from django.urls import path
from . import realtime_views

urlpatterns = [
    path('realtime/', realtime_views.realtime_dashboard, name='realtime_dashboard'),
    path('api/realtime/agents/', realtime_views.realtime_agents_api, name='realtime_agents_api'),
    path('api/realtime/stats/', realtime_views.realtime_campaign_stats_api, name='realtime_stats_api'),
    path('api/realtime/queue/', realtime_views.realtime_call_queue_api, name='realtime_queue_api'),
]

Add to routing.py (WebSocket):

from django.urls import re_path
from reports.consumers import RealtimeReportConsumer

websocket_urlpatterns = [
    re_path(r'ws/reports/realtime/(?P<campaign_id>\w+)/$', RealtimeReportConsumer.as_asgi()),
    re_path(r'ws/reports/realtime/$', RealtimeReportConsumer.as_asgi()),
]
"""
