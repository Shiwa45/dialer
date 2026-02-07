"""
ARI Event Worker - Real-time event consumer for Asterisk ARI

This worker listens to Asterisk ARI WebSocket events and manages call states,
bridging customer calls to available agents in real-time.

Following Vicidial workflow approach.
"""

import asyncio
import json
import logging
import websockets
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from asgiref.sync import sync_to_async, async_to_sync
from channels.layers import get_channel_layer

from telephony.models import AsteriskServer
from telephony.services import AsteriskService
from campaigns.models import Campaign
from campaigns.services import HopperService
from agents.models import AgentDialerSession
from calls.models import CallLog
from leads.models import Lead
from users.models import AgentStatus

logger = logging.getLogger(__name__)


class ARIEventWorker:
    """
    Real-time ARI event processor for predictive dialer
    """
    
    def __init__(self, asterisk_server):
        self.server = asterisk_server
        self.service = AsteriskService(asterisk_server)
        self.ws_url = f"ws://{asterisk_server.ari_host}:{asterisk_server.ari_port}/ari/events"
        self.running = False
        self.channel_layer = get_channel_layer()
        
        # Track active calls and bridges
        self.active_calls = {}  # channel_id -> call_data
        self.active_bridges = {}  # bridge_id -> bridge_data
        
    async def connect(self):
        """Connect to ARI WebSocket"""
        # Asterisk ARI WebSocket requires auth in URL, not headers
        url = f"ws://{self.server.ari_host}:{self.server.ari_port}/ari/events?app=autodialer&api_key={self.server.ari_username}:{self.server.ari_password}"
        
        logger.info(f"Connecting to ARI: {url.replace(self.server.ari_password, '***')}")
        
        async with websockets.connect(url) as websocket:
            self.running = True
            logger.info("Connected to Asterisk ARI")
            
            async for message in websocket:
                try:
                    logger.debug(f"Received ARI event: {message[:200]}...")  # Log first 200 chars
                    event = json.loads(message)
                    await self.handle_event(event)
                except Exception as e:
                    logger.error(f"Error processing event: {e}", exc_info=True)
    
    def _encode_auth(self, auth):
        """Encode basic auth"""
        import base64
        credentials = f"{auth[0]}:{auth[1]}"
        return base64.b64encode(credentials.encode()).decode()
    
    async def handle_event(self, event):
        """Route events to appropriate handlers"""
        event_type = event.get('type')
        
        handlers = {
            'StasisStart': self.handle_stasis_start,
            'ChannelStateChange': self.handle_channel_state_change,
            'ChannelDestroyed': self.handle_channel_destroyed,
            'BridgeCreated': self.handle_bridge_created,
            'BridgeDestroyed': self.handle_bridge_destroyed,
            'ChannelEnteredBridge': self.handle_channel_entered_bridge,
            'ChannelLeftBridge': self.handle_channel_left_bridge,
            'EndpointStateChange': self.handle_endpoint_state_change,
        }
        
        handler = handlers.get(event_type)
        if handler:
            logger.info(f"Handling event: {event_type}")
            await handler(event)
        else:
            logger.info(f"Unhandled event type: {event_type}")
    
    async def handle_stasis_start(self, event):
        """Handle new channel entering Stasis app"""
        channel = event.get('channel', {})
        channel_id = channel.get('id')
        args = event.get('args', [])
        
        logger.info(f"StasisStart: {channel_id}")
        
        # Get channel variables
        variables = await sync_to_async(self._get_channel_variables)(channel_id)
        call_type = variables.get('CALL_TYPE')
        
        if call_type == 'autodial':
            # This is a customer call from predictive dialer
            await self.handle_customer_call(channel_id, variables)
        elif call_type == 'agent_leg':
            # This is an agent leg for persistent session
            await self.handle_agent_leg(channel_id, variables)
        elif call_type == 'customer_leg':
            # Customer leg for persistent agent session
            await self.handle_customer_leg_for_session(channel_id, variables)
    
    async def handle_customer_call(self, channel_id, variables):
        """Handle customer call from predictive dialer"""
        campaign_id = variables.get('CAMPAIGN_ID')
        lead_id = variables.get('LEAD_ID')
        phone_number = variables.get('CUSTOMER_NUMBER')
        
        logger.info(f"Customer call: {channel_id} for lead {lead_id}")
        
        # Store call data
        self.active_calls[channel_id] = {
            'type': 'customer',
            'campaign_id': campaign_id,
            'lead_id': lead_id,
            'phone_number': phone_number,
            'state': 'initiated',
            'started_at': timezone.now()
        }
        
        # Update call log
        await sync_to_async(self._update_call_log)(
            channel_id, 
            call_status='ringing'
        )
    
    async def handle_channel_state_change(self, event):
        """Handle channel state changes (ringing, answered, etc.)"""
        channel = event.get('channel', {})
        channel_id = channel.get('id')
        state = channel.get('state')
        
        logger.info(f"Channel state change: {channel_id} -> {state}")
        
        if channel_id not in self.active_calls:
            return
        
        call_data = self.active_calls[channel_id]
        
        if state == 'Up':
            # Channel answered
            await self.handle_channel_answered(channel_id, call_data)
        elif state == 'Ringing':
            call_data['state'] = 'ringing'
    
    async def handle_channel_answered(self, channel_id, call_data):
        """Handle when a channel is answered"""
        logger.info(f"Channel answered: {channel_id}")
        
        call_data['state'] = 'answered'
        call_data['answered_at'] = timezone.now()
        
        if call_data['type'] == 'customer':
            # Customer answered - find available agent and bridge
            await self.bridge_to_agent(channel_id, call_data)
        
        # Update call log
        await sync_to_async(self._update_call_log)(
            channel_id,
            call_status='answered',
            answer_time=timezone.now()
        )
    
    async def bridge_to_agent(self, customer_channel_id, call_data):
        """Find available agent and bridge the call"""
        campaign_id = call_data['campaign_id']
        lead_id = call_data['lead_id']
        
        logger.info(f"Finding agent for call {customer_channel_id}")
        
        # Find available agent
        agent_session = await sync_to_async(self._find_available_agent)(campaign_id)
        
        if not agent_session:
            logger.warning(f"No available agent for call {customer_channel_id}")
            # This is a dropped call - customer answered but no agent
            await self.handle_dropped_call(customer_channel_id, call_data)
            return
        
        logger.info(f"Bridging call to agent {agent_session.agent.username}")
        
        # Create bridge
        bridge_result = await sync_to_async(self.service.create_bridge)('mixing')
        if not bridge_result.get('success'):
            logger.error(f"Failed to create bridge: {bridge_result.get('error')}")
            await self.handle_dropped_call(customer_channel_id, call_data)
            return
        
        bridge_id = bridge_result['bridge_id']
        
        # Add customer to bridge
        await sync_to_async(self.service.add_channel_to_bridge)(
            bridge_id, customer_channel_id
        )
        
        # Add agent to bridge (agent should already be in their persistent bridge)
        # For now, originate agent channel
        agent_result = await sync_to_async(self._originate_agent_channel)(
            agent_session, bridge_id, call_data
        )
        
        if not agent_result.get('success'):
            logger.error(f"Failed to originate agent: {agent_result.get('error')}")
            await sync_to_async(self.service.destroy_bridge)(bridge_id)
            await self.handle_dropped_call(customer_channel_id, call_data)
            return
        
        agent_channel_id = agent_result['channel_id']
        
        # Update call data
        call_data['agent_session_id'] = agent_session.id
        call_data['agent_channel_id'] = agent_channel_id
        call_data['bridge_id'] = bridge_id
        call_data['state'] = 'bridged'
        
        # Update database
        await sync_to_async(self._update_call_with_agent)(
            customer_channel_id,
            agent_session.agent,
            agent_channel_id,
            bridge_id,
            lead_id
        )
        
        # Update agent status
        await sync_to_async(self._set_agent_busy)(agent_session.agent, customer_channel_id)
        
        # Notify agent UI
        await self._notify_agent_call_connected(
            agent_session.agent.id,
            customer_channel_id,
            call_data
        )
        
        # Unregister from dialing set
        await sync_to_async(HopperService.unregister_dialing)(campaign_id, lead_id)
    
    async def handle_dropped_call(self, channel_id, call_data):
        """Handle dropped call (customer answered but no agent available)"""
        logger.warning(f"Dropped call: {channel_id}")
        
        # Hangup customer
        await sync_to_async(self.service.hangup_channel)(channel_id)
        
        # Update call log
        await sync_to_async(self._update_call_log)(
            channel_id,
            call_status='dropped',
            end_time=timezone.now()
        )
        
        # Unregister from dialing
        campaign_id = call_data.get('campaign_id')
        lead_id = call_data.get('lead_id')
        if campaign_id and lead_id:
            await sync_to_async(HopperService.unregister_dialing)(campaign_id, lead_id)
    
    async def handle_channel_destroyed(self, event):
        """Handle channel hangup"""
        channel = event.get('channel', {})
        channel_id = channel.get('id')
        cause_txt = channel.get('dialplan', {}).get('exten', 'unknown')
        
        logger.info(f"Channel destroyed: {channel_id}")
        
        if channel_id not in self.active_calls:
            return
        
        call_data = self.active_calls[channel_id]
        
        # Update call log
        await sync_to_async(self._update_call_log)(
            channel_id,
            call_status='completed',
            end_time=timezone.now(),
            hangup_cause_text=cause_txt
        )
        
        # If agent was on call, set to wrapup
        agent_session_id = call_data.get('agent_session_id')
        if agent_session_id:
            await sync_to_async(self._set_agent_wrapup)(agent_session_id)
        
        # Notify agent UI
        if call_data.get('agent_session_id'):
            agent_session = await sync_to_async(
                lambda: AgentDialerSession.objects.get(id=agent_session_id)
            )()
            await self._notify_agent_call_ended(agent_session.agent.id, channel_id)
        
        # Unregister from dialing
        campaign_id = call_data.get('campaign_id')
        lead_id = call_data.get('lead_id')
        if campaign_id and lead_id:
            await sync_to_async(HopperService.unregister_dialing)(campaign_id, lead_id)
        
        # Clean up
        del self.active_calls[channel_id]
    
    async def handle_bridge_created(self, event):
        """Handle bridge creation"""
        bridge = event.get('bridge', {})
        bridge_id = bridge.get('id')
        
        logger.info(f"Bridge created: {bridge_id}")
        
        self.active_bridges[bridge_id] = {
            'created_at': timezone.now(),
            'channels': []
        }
    
    async def handle_bridge_destroyed(self, event):
        """Handle bridge destruction"""
        bridge = event.get('bridge', {})
        bridge_id = bridge.get('id')
        
        logger.info(f"Bridge destroyed: {bridge_id}")
        
        if bridge_id in self.active_bridges:
            del self.active_bridges[bridge_id]
    
    async def handle_channel_entered_bridge(self, event):
        """Handle channel entering bridge"""
        channel = event.get('channel', {})
        bridge = event.get('bridge', {})
        channel_id = channel.get('id')
        bridge_id = bridge.get('id')
        
        logger.info(f"Channel {channel_id} entered bridge {bridge_id}")
        
        if bridge_id in self.active_bridges:
            self.active_bridges[bridge_id]['channels'].append(channel_id)
    
    async def handle_channel_left_bridge(self, event):
        """Handle channel leaving bridge"""
        channel = event.get('channel', {})
        bridge = event.get('bridge', {})
        channel_id = channel.get('id')
        bridge_id = bridge.get('id')
        
        logger.info(f"Channel {channel_id} left bridge {bridge_id}")
        
        if bridge_id in self.active_bridges:
            if channel_id in self.active_bridges[bridge_id]['channels']:
                self.active_bridges[bridge_id]['channels'].remove(channel_id)
    
    async def handle_agent_leg(self, channel_id, variables):
        """Handle agent leg for persistent session"""
        bridge_id = variables.get('BRIDGE_ID')
        
        logger.info(f"Agent leg: {channel_id} for bridge {bridge_id}")
        
        # Add to bridge when answered
        # This will be handled by ChannelStateChange
    
    async def handle_customer_leg_for_session(self, channel_id, variables):
        """Handle customer leg for persistent agent session"""
        bridge_id = variables.get('BRIDGE_ID')
        campaign_id = variables.get('CAMPAIGN_ID')
        
        logger.info(f"Customer leg for session: {channel_id}")
        
        self.active_calls[channel_id] = {
            'type': 'customer_session',
            'bridge_id': bridge_id,
            'campaign_id': campaign_id,
            'state': 'initiated',
            'started_at': timezone.now()
        }

    
    async def handle_endpoint_state_change(self, event):
        """Handle endpoint state changes (registration/break)"""
        endpoint = event.get('endpoint', {})
        resource = endpoint.get('resource')  # Extension, e.g. "101"
        state = (endpoint.get('state') or '').lower()
        tech = endpoint.get('technology')
        
        # We only care about PJSIP extensions
        if tech != 'PJSIP' or not resource:
            return
            
        logger.info(f"Endpoint state change: {tech}/{resource} -> {state}")
        
        # Determine if registered/online
        is_online = state in ('online', 'reachable', 'available', 'ready')
        
        # Verify this extension belongs to an agent
        # We need to find which user has this extension
        # Since this is async/realtime, avoiding complex queries is best
        # querying UserProfile -> User -> AgentStatus
        
        await sync_to_async(self._update_agent_status_from_endpoint)(resource, is_online)

    
    # Helper methods (sync)
    
    def _update_agent_status_from_endpoint(self, extension, is_online):
        """Update agent status based on endpoint state"""
        from users.models import UserProfile, AgentStatus
        
        try:
            # Find user with this extension
            profile = UserProfile.objects.filter(extension=extension).select_related('user').first()
            if not profile:
                return
                
            agent_status = AgentStatus.objects.filter(user=profile.user).first()
            if not agent_status:
                return
                
            current_status = agent_status.status
            
            if is_online:
                # Agent became reachable
                if current_status == 'offline':
                    # Only auto-set to available if they were offline
                    logger.info(f"Agent {profile.user.username} (Ext {extension}) came online. Setting to Available.")
                    agent_status.status = 'available'
                    agent_status.status_changed_at = timezone.now()
                    agent_status.save()
                    
                    # Notify dashboard
                    # (In a real app, we'd fire a websocket event here)
            else:
                # Agent became unreachable
                if current_status != 'offline':
                    logger.info(f"Agent {profile.user.username} (Ext {extension}) lost connection. Setting to Offline.")
                    agent_status.status = 'offline'
                    agent_status.status_changed_at = timezone.now()
                    agent_status.save()
                    
                    # Cleanup sessions
                    AgentDialerSession.objects.filter(
                        agent=profile.user, 
                        status__in=['ready', 'connecting', 'incall']
                    ).delete()

        except Exception as e:
            logger.error(f"Error updating agent status from endpoint: {e}")

    
    def _get_channel_variables(self, channel_id):
        """Get channel variables from Asterisk"""
        try:
            # Get channel info with variables from ARI
            result = self.service.get_channel_variables(channel_id)
            if not result.get('success'):
                logger.warning(f"Failed to get channel variables for {channel_id}")
                return {}
            
            channel_vars = result.get('channelvars', {})
            
            # Extract the variables we need
            variables = {
                'CALL_TYPE': channel_vars.get('CALL_TYPE', ''),
                'CAMPAIGN_ID': channel_vars.get('CAMPAIGN_ID', ''),
                'LEAD_ID': channel_vars.get('LEAD_ID', ''),
                'CUSTOMER_NUMBER': channel_vars.get('CUSTOMER_NUMBER', ''),
                'BRIDGE_ID': channel_vars.get('BRIDGE_ID', ''),
            }
            
            logger.info(f"Channel {channel_id} variables: {variables}")
            return variables
        except Exception as e:
            logger.error(f"Error getting channel variables: {e}")
            return {}
    
    def _find_available_agent(self, campaign_id):
        """Find available agent for campaign"""
        return AgentDialerSession.objects.filter(
            campaign_id=campaign_id,
            status='ready'
        ).first()
    
    def _originate_agent_channel(self, agent_session, bridge_id, call_data):
        """Originate channel to agent"""
        result = self.service.originate_pjsip_channel(
            endpoint=agent_session.agent_extension,
            app='autodialer',
            callerid=f"Campaign Call",
            variables={
                'CALL_TYPE': 'agent_answer',
                'BRIDGE_ID': bridge_id,
                'LEAD_ID': call_data.get('lead_id', ''),
                'CAMPAIGN_ID': call_data.get('campaign_id', '')
            }
        )
        return result
    
    def _update_call_log(self, channel_id, **kwargs):
        """Update call log"""
        try:
            call_log = CallLog.objects.filter(channel=channel_id).first()
            if call_log:
                for key, value in kwargs.items():
                    setattr(call_log, key, value)
                call_log.save()
        except Exception as e:
            logger.error(f"Error updating call log: {e}")
    
    def _update_call_with_agent(self, channel_id, agent, agent_channel_id, bridge_id, lead_id):
        """Update call log with agent info"""
        try:
            call_log = CallLog.objects.filter(channel=channel_id).first()
            if call_log:
                call_log.agent = agent
                call_log.agent_channel = agent_channel_id
                call_log.bridge_id = bridge_id
                if lead_id:
                    call_log.lead_id = lead_id
                call_log.save()
        except Exception as e:
            logger.error(f"Error updating call with agent: {e}")
    
    def _set_agent_busy(self, agent, call_id):
        """Set agent status to busy"""
        try:
            agent_status = AgentStatus.objects.filter(user=agent).first()
            if agent_status:
                agent_status.status = 'busy'
                agent_status.current_call_id = str(call_id)
                agent_status.call_start_time = timezone.now()
                agent_status.save()
        except Exception as e:
            logger.error(f"Error setting agent busy: {e}")
    
    def _set_agent_wrapup(self, agent_session_id):
        """Set agent to wrapup status"""
        try:
            session = AgentDialerSession.objects.get(id=agent_session_id)
            agent_status = AgentStatus.objects.filter(user=session.agent).first()
            if agent_status:
                agent_status.status = 'wrapup'
                agent_status.current_call_id = ''
                agent_status.call_start_time = None
                agent_status.save()
        except Exception as e:
            logger.error(f"Error setting agent wrapup: {e}")
    
    async def _notify_agent_call_connected(self, agent_id, channel_id, call_data):
        """Notify agent via WebSocket that call is connected"""
        if not self.channel_layer:
            return
        
        try:
            # Get lead info
            lead = None
            if call_data.get('lead_id'):
                lead = await sync_to_async(
                    lambda: Lead.objects.get(id=call_data['lead_id'])
                )()
            
            await self.channel_layer.group_send(
                f"agent_{agent_id}",
                {
                    'type': 'call.event',
                    'data': {
                        'type': 'call_connected',
                        'call_id': channel_id,
                        'phone_number': call_data.get('phone_number'),
                        'lead': {
                            'id': lead.id if lead else None,
                            'first_name': lead.first_name if lead else '',
                            'last_name': lead.last_name if lead else '',
                            'company': lead.company if lead else '',
                            'email': lead.email if lead else '',
                        } if lead else None
                    }
                }
            )
        except Exception as e:
            logger.error(f"Error notifying agent: {e}")
    
    async def _notify_agent_call_ended(self, agent_id, channel_id):
        """Notify agent that call ended"""
        if not self.channel_layer:
            return
        
        try:
            await self.channel_layer.group_send(
                f"agent_{agent_id}",
                {
                    'type': 'call.event',
                    'data': {
                        'type': 'call_ended',
                        'call_id': channel_id
                    }
                }
            )
        except Exception as e:
            logger.error(f"Error notifying agent: {e}")


class Command(BaseCommand):
    help = 'Start ARI event worker for real-time call handling'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--server-id',
            type=int,
            help='Asterisk server ID (default: first active server)'
        )
    
    def handle(self, *args, **options):
        server_id = options.get('server_id')
        
        if server_id:
            server = AsteriskServer.objects.filter(id=server_id, is_active=True).first()
        else:
            server = AsteriskServer.objects.filter(is_active=True).first()
        
        if not server:
            self.stdout.write(self.style.ERROR('No active Asterisk server found'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'Starting ARI Event Worker for {server.name}'))
        
        worker = ARIEventWorker(server)
        
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Run the worker connection
            loop.run_until_complete(worker.connect())
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nStopping ARI Event Worker'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            logger.error(f'ARI Worker error: {e}', exc_info=True)
        finally:
            loop.close()
