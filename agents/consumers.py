"""
WebSocket Consumer for Agent Real-time Updates

Handles real-time communication between the server and agent interface
for call events, status updates, and campaign statistics.
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class AgentConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for agent real-time updates
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope['user']
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Join agent-specific group
        self.agent_group_name = f'agent_{self.user.id}'
        
        await self.channel_layer.group_add(
            self.agent_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        logger.info(f"Agent {self.user.username} connected to WebSocket")
        
        # Send initial connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'agent_id': self.user.id,
            'username': self.user.username
        }))
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave agent group
        await self.channel_layer.group_discard(
            self.agent_group_name,
            self.channel_name
        )
        
        logger.info(f"Agent {self.user.username} disconnected from WebSocket")
    
    async def receive(self, text_data):
        """Handle messages from WebSocket"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            # Handle different message types
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                }))
            
            elif message_type == 'status_update':
                # Agent is updating their status
                await self.handle_status_update(data)
            
            elif message_type == 'request_stats':
                # Agent requesting campaign statistics
                await self.handle_stats_request(data)
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received from agent {self.user.username}")
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
    
    async def handle_status_update(self, data):
        """Handle agent status update"""
        new_status = data.get('status')
        
        # Update agent status in database
        await self.update_agent_status(new_status)
        
        # Confirm status update
        await self.send(text_data=json.dumps({
            'type': 'status_updated',
            'status': new_status
        }))
    
    async def handle_stats_request(self, data):
        """Handle request for campaign statistics"""
        campaign_id = data.get('campaign_id')
        
        if campaign_id:
            stats = await self.get_campaign_stats(campaign_id)
            await self.send(text_data=json.dumps({
                'type': 'campaign_stats',
                'campaign_id': campaign_id,
                'stats': stats
            }))
    
    # Event handlers (called from channel layer)
    
    async def call_event(self, event):
        """Handle call events from channel layer"""
        # Send call event to WebSocket
        await self.send(text_data=json.dumps(event['data']))
    
    async def status_event(self, event):
        """Handle status events from channel layer"""
        await self.send(text_data=json.dumps(event['data']))
    
    async def campaign_stats_event(self, event):
        """Handle campaign statistics events"""
        await self.send(text_data=json.dumps(event['data']))
    
    async def notification_event(self, event):
        """Handle notification events"""
        await self.send(text_data=json.dumps(event['data']))
    
    # Database operations
    
    @database_sync_to_async
    def update_agent_status(self, status):
        """Update agent status in database"""
        from users.models import AgentStatus
        
        try:
            agent_status, created = AgentStatus.objects.get_or_create(
                user=self.user
            )
            agent_status.status = status
            agent_status.save()
            return True
        except Exception as e:
            logger.error(f"Error updating agent status: {e}")
            return False
    
    @database_sync_to_async
    def get_campaign_stats(self, campaign_id):
        """Get campaign statistics"""
        from campaigns.models import Campaign, CampaignStats
        from django.utils import timezone
        from datetime import datetime
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            today = timezone.now().date()
            
            # Get today's stats
            stats = CampaignStats.objects.filter(
                campaign=campaign,
                date=today
            ).first()
            
            if stats:
                return {
                    'calls_made': stats.calls_made,
                    'calls_answered': stats.calls_answered,
                    'calls_dropped': stats.calls_dropped,
                    'contact_rate': float(stats.contact_rate),
                    'conversion_rate': float(stats.conversion_rate),
                    'average_call_duration': stats.average_call_duration
                }
            else:
                return {
                    'calls_made': 0,
                    'calls_answered': 0,
                    'calls_dropped': 0,
                    'contact_rate': 0.0,
                    'conversion_rate': 0.0,
                    'average_call_duration': 0
                }
        except Exception as e:
            logger.error(f"Error getting campaign stats: {e}")
            return {}


class CampaignMonitorConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for campaign monitoring (supervisors)
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope['user']
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Check if user has supervisor permissions
        if not await self.is_supervisor():
            await self.close()
            return
        
        self.campaign_id = self.scope['url_route']['kwargs']['campaign_id']
        self.campaign_group_name = f'campaign_{self.campaign_id}'
        
        await self.channel_layer.group_add(
            self.campaign_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        logger.info(f"Supervisor {self.user.username} monitoring campaign {self.campaign_id}")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        await self.channel_layer.group_discard(
            self.campaign_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """Handle messages from WebSocket"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'request_agent_list':
                await self.send_agent_list()
            
            elif message_type == 'request_call_queue':
                await self.send_call_queue()
            
        except Exception as e:
            logger.error(f"Error handling supervisor message: {e}")
    
    async def send_agent_list(self):
        """Send list of agents in campaign"""
        agents = await self.get_campaign_agents()
        await self.send(text_data=json.dumps({
            'type': 'agent_list',
            'agents': agents
        }))
    
    async def send_call_queue(self):
        """Send current call queue status"""
        queue_stats = await self.get_queue_stats()
        await self.send(text_data=json.dumps({
            'type': 'call_queue',
            'stats': queue_stats
        }))
    
    # Event handlers
    
    async def campaign_update(self, event):
        """Handle campaign update events"""
        await self.send(text_data=json.dumps(event['data']))
    
    async def agent_status_change(self, event):
        """Handle agent status change events"""
        await self.send(text_data=json.dumps(event['data']))
    
    async def call_completed(self, event):
        """Handle call completion events"""
        await self.send(text_data=json.dumps(event['data']))
    
    # Database operations
    
    @database_sync_to_async
    def is_supervisor(self):
        """Check if user has supervisor permissions"""
        return self.user.is_staff or self.user.groups.filter(name='Supervisors').exists()
    
    @database_sync_to_async
    def get_campaign_agents(self):
        """Get list of agents in campaign"""
        from agents.models import AgentDialerSession
        from users.models import AgentStatus
        
        try:
            sessions = AgentDialerSession.objects.filter(
                campaign_id=self.campaign_id,
                status__in=['connecting', 'ready']
            ).select_related('agent')
            
            agents = []
            for session in sessions:
                agent_status = AgentStatus.objects.filter(user=session.agent).first()
                agents.append({
                    'id': session.agent.id,
                    'username': session.agent.username,
                    'status': session.status,
                    'agent_status': agent_status.status if agent_status else 'offline',
                    'calls_handled': session.calls_handled,
                    'average_handle_time': float(session.average_handle_time)
                })
            
            return agents
        except Exception as e:
            logger.error(f"Error getting campaign agents: {e}")
            return []
    
    @database_sync_to_async
    def get_queue_stats(self):
        """Get call queue statistics"""
        from campaigns.services import HopperService
        
        try:
            hopper_count = HopperService.get_hopper_count(self.campaign_id)
            active_calls = HopperService.get_active_call_count(self.campaign_id)
            
            return {
                'hopper_count': hopper_count,
                'active_calls': active_calls
            }
        except Exception as e:
            logger.error(f"Error getting queue stats: {e}")
            return {}
