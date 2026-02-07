"""
Real-time Report WebSocket Consumer - Phase 3.2

WebSocket consumer for real-time report updates.
Supervisors connect to receive live agent and call updates.
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.db.models import Q, Count

logger = logging.getLogger(__name__)


class RealtimeReportConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time report updates
    
    Supervisors connect to this to receive live updates about:
    - Agent status changes
    - Call events
    - Campaign statistics
    
    URL patterns:
    - /ws/reports/realtime/ - All campaigns
    - /ws/reports/realtime/<campaign_id>/ - Specific campaign
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope['user']
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Check supervisor permission
        if not await self._is_supervisor():
            logger.warning(f"Non-supervisor {self.user.username} tried to access realtime reports")
            await self.close()
            return
        
        # Get campaign filter from URL
        self.campaign_id = self.scope['url_route']['kwargs'].get('campaign_id', 'all')
        self.group_name = f'realtime_report_{self.campaign_id}'
        
        # Join campaign-specific group
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
        
        logger.info(f"Supervisor {self.user.username} connected to realtime reports (campaign: {self.campaign_id})")
        
        # Send initial data
        await self.send_full_update()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave groups
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        
        await self.channel_layer.group_discard(
            'realtime_report_all',
            self.channel_name
        )
        
        logger.info(f"Supervisor {self.user.username} disconnected from realtime reports")
    
    async def receive(self, text_data):
        """Handle messages from client"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': timezone.now().isoformat()
                }))
            
            elif message_type == 'request_refresh':
                await self.send_full_update()
            
            elif message_type == 'change_campaign':
                # Change campaign filter
                new_campaign = data.get('campaign_id', 'all')
                
                # Leave old group
                await self.channel_layer.group_discard(
                    self.group_name,
                    self.channel_name
                )
                
                # Join new group
                self.campaign_id = new_campaign
                self.group_name = f'realtime_report_{self.campaign_id}'
                
                await self.channel_layer.group_add(
                    self.group_name,
                    self.channel_name
                )
                
                # Send updated data
                await self.send_full_update()
            
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
        except Exception as e:
            logger.error(f"Error handling realtime message: {e}", exc_info=True)
    
    async def send_full_update(self):
        """Send complete data refresh to client"""
        try:
            agents = await self._get_agents_data()
            stats = await self._get_campaign_stats()
            queue = await self._get_queue_data()
            
            await self.send(text_data=json.dumps({
                'type': 'full_update',
                'agents': agents,
                'stats': stats,
                'queue': queue,
                'timestamp': timezone.now().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error sending full update: {e}")
    
    # ========================================
    # Event Handlers (called from channel layer)
    # ========================================
    
    async def agent_update(self, event):
        """Handle agent status update broadcast"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'agent_update',
                'agent': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error sending agent_update: {e}")
    
    async def call_update(self, event):
        """Handle call event broadcast"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'call_update',
                'call': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error sending call_update: {e}")
    
    async def stats_update(self, event):
        """Handle statistics update broadcast"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'stats_update',
                'stats': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error sending stats_update: {e}")
    
    async def queue_update(self, event):
        """Handle queue update broadcast"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'queue_update',
                'queue': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error sending queue_update: {e}")
    
    # ========================================
    # Database Operations
    # ========================================
    
    @database_sync_to_async
    def _is_supervisor(self):
        """Check if user has supervisor permissions"""
        return (
            self.user.is_staff or 
            self.user.is_superuser or 
            self.user.groups.filter(name__in=['Supervisor', 'Manager']).exists()
        )
    
    @database_sync_to_async
    def _get_agents_data(self):
        """Get current state of all agents"""
        from users.models import AgentStatus
        from campaigns.models import CampaignAgent
        
        now = timezone.now()
        
        # Base query
        agents_query = AgentStatus.objects.select_related(
            'user', 'current_campaign'
        ).exclude(status='offline')
        
        # Filter by campaign if specified
        if self.campaign_id and self.campaign_id != 'all':
            try:
                campaign_id = int(self.campaign_id)
                agent_ids = CampaignAgent.objects.filter(
                    campaign_id=campaign_id,
                    is_active=True
                ).values_list('user_id', flat=True)
                agents_query = agents_query.filter(user_id__in=agent_ids)
            except (ValueError, TypeError):
                pass
        
        agents = []
        for agent in agents_query:
            # Calculate time in status
            status_time = 0
            if agent.status_changed_at:
                status_time = int((now - agent.status_changed_at).total_seconds())
            
            # Format status time
            hours = status_time // 3600
            minutes = (status_time % 3600) // 60
            seconds = status_time % 60
            
            if hours > 0:
                time_formatted = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                time_formatted = f"{minutes}:{seconds:02d}"
            
            agents.append({
                'id': agent.user.id,
                'username': agent.user.username,
                'name': agent.user.get_full_name() or agent.user.username,
                'status': agent.status,
                'status_time': status_time,
                'status_time_formatted': time_formatted,
                'campaign': agent.current_campaign.name if agent.current_campaign else None,
                'campaign_id': agent.current_campaign.id if agent.current_campaign else None,
                'current_call': agent.current_call_id,
            })
        
        return agents
    
    @database_sync_to_async
    def _get_campaign_stats(self):
        """Get campaign statistics"""
        from calls.models import CallLog
        from users.models import AgentStatus
        from django.db.models import Avg
        from datetime import timedelta
        
        now = timezone.now()
        today = now.date()
        hour_ago = now - timedelta(hours=1)
        
        # Base query
        calls_query = CallLog.objects.filter(start_time__date=today)
        
        # Filter by campaign if specified
        if self.campaign_id and self.campaign_id != 'all':
            try:
                calls_query = calls_query.filter(campaign_id=int(self.campaign_id))
            except (ValueError, TypeError):
                pass
        
        # Calculate metrics
        total_calls = calls_query.count()
        answered_calls = calls_query.filter(
            Q(call_status='answered') | Q(answer_time__isnull=False)
        ).count()
        dropped_calls = calls_query.filter(call_status='dropped').count()
        sales = calls_query.filter(disposition__is_sale=True).count()
        calls_last_hour = calls_query.filter(start_time__gte=hour_ago).count()
        
        avg_duration = calls_query.filter(
            talk_duration__gt=0
        ).aggregate(avg=Avg('talk_duration'))['avg'] or 0
        
        # Calculate rates
        contact_rate = (answered_calls / total_calls * 100) if total_calls > 0 else 0
        conversion_rate = (sales / answered_calls * 100) if answered_calls > 0 else 0
        drop_rate = (dropped_calls / total_calls * 100) if total_calls > 0 else 0
        
        # Format average duration
        avg_secs = int(avg_duration)
        avg_formatted = f"{avg_secs // 60}:{avg_secs % 60:02d}"
        
        # Get hourly trend
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
        
        # Agent counts
        agent_query = AgentStatus.objects.exclude(status='offline')
        if self.campaign_id and self.campaign_id != 'all':
            from campaigns.models import CampaignAgent
            try:
                agent_ids = CampaignAgent.objects.filter(
                    campaign_id=int(self.campaign_id),
                    is_active=True
                ).values_list('user_id', flat=True)
                agent_query = agent_query.filter(user_id__in=agent_ids)
            except (ValueError, TypeError):
                pass
        
        return {
            'total_calls': total_calls,
            'answered_calls': answered_calls,
            'dropped_calls': dropped_calls,
            'sales': sales,
            'calls_per_hour': calls_last_hour,
            'avg_duration': avg_secs,
            'avg_duration_formatted': avg_formatted,
            'contact_rate': round(contact_rate, 1),
            'conversion_rate': round(conversion_rate, 1),
            'drop_rate': round(drop_rate, 1),
            'agents_available': agent_query.filter(status='available').count(),
            'agents_busy': agent_query.filter(status='busy').count(),
            'agents_paused': agent_query.filter(status__in=['break', 'lunch', 'training', 'meeting']).count(),
            'agents_wrapup': agent_query.filter(status='wrapup').count(),
            'calls_trend': calls_trend
        }
    
    @database_sync_to_async
    def _get_queue_data(self):
        """Get call queue data"""
        from campaigns.models import DialerHopper
        
        hopper_query = DialerHopper.objects.all()
        
        if self.campaign_id and self.campaign_id != 'all':
            try:
                hopper_query = hopper_query.filter(campaign_id=int(self.campaign_id))
            except (ValueError, TypeError):
                pass
        
        return {
            'total': hopper_query.count(),
            'pending': hopper_query.filter(status='new').count(),
            'locked': hopper_query.filter(status='locked').count(),
            'dialing': hopper_query.filter(status='dialing').count()
        }


class MonitorDashboardConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for the legacy/supervisor monitor dashboard.
    Restored to fix ImportError in routing.
    """
    async def connect(self):
        if not self.scope["user"].is_authenticated:
            await self.close()
            return
            
        self.group_name = "monitor_dashboard"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass  # Basic implementation for now


# ============================================================================
# Broadcast Functions
# ============================================================================

def broadcast_agent_update(agent_id, status, campaign_id=None):
    """
    Broadcast agent status update to realtime report subscribers
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from django.utils import timezone
    
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


