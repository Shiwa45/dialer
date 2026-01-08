import json
import logging
import asyncio
import time
from datetime import datetime, timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.db import transaction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync, sync_to_async

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Corrected ARI Worker for your existing autodialer workflow'
    
    def add_arguments(self, parser):
        parser.add_argument('--debug', action='store_true', help='Enable debug logging')
        
    def handle(self, *args, **options):
        if options['debug']:
            logging.getLogger().setLevel(logging.DEBUG)
            
        self.channel_layer = get_channel_layer()
        
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting CORRECTED ARI Worker (Your Workflow)...')
        )
        
        try:
            asyncio.run(self.run_ari_worker())
        except KeyboardInterrupt:
            self.stdout.write('✋ ARI Worker stopped')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'💥 ARI Worker error: {e}'))
            logger.exception("ARI Worker crashed")
            
    async def run_ari_worker(self):
        """Main ARI worker loop - FIXES the 'Inactive Stasis app' error"""
        from telephony.models import AsteriskServer
        
        # Get active server
        server = await sync_to_async(AsteriskServer.objects.filter)(is_active=True)
        server = await sync_to_async(server.first)()
        
        if not server:
            logger.error("❌ No active Asterisk server found")
            return
            
        logger.info(f"🖥️ Using Asterisk server: {server.server_ip}")
        
        # CRITICAL FIX: Connect to ARI properly to activate Stasis app
        try:
            import aiohttp
            
            connector = aiohttp.TCPConnector(
                limit=100, 
                limit_per_host=10,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            session = aiohttp.ClientSession(connector=connector)
            
            # Build WebSocket URL for your autodialer app
            ws_url = (f"ws://{server.server_ip}:8088/ari/events"
                     f"?api_key={server.ari_username}:{server.ari_password}"
                     f"&app=autodialer")
            
            logger.info(f"🔌 Connecting to ARI: {ws_url}")
            
            # Connect with timeout
            ws = await asyncio.wait_for(session.ws_connect(ws_url), timeout=10)
            
            logger.info("✅ ARI connected - 'autodialer' Stasis app is now ACTIVE")
            self.stdout.write(
                self.style.SUCCESS("✅ Fixed: No more 'Inactive Stasis app autodialer missed message'")
            )
            
            # Process events
            await self.process_ari_events(ws, server)
            
        except Exception as e:
            logger.error(f"❌ ARI connection failed: {e}")
            self.stdout.write(
                self.style.ERROR(f"❌ ARI connection failed: {e}")
            )
            
    async def process_ari_events(self, ws, server):
        """Process ARI events - respecting your existing workflow"""
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    event = json.loads(msg.data)
                    await self.handle_ari_event(event, server)
                except Exception as e:
                    logger.error(f"❌ Event handling error: {e}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"❌ WebSocket error: {ws.exception()}")
                break
                
    async def handle_ari_event(self, event, server):
        """Handle ARI events with your existing workflow logic"""
        event_type = event.get('type')
        channel = event.get('channel', {})
        channel_id = channel.get('id')
        
        if not channel_id:
            return
            
        logger.debug(f"📨 ARI Event: {event_type} for {channel_id}")
        
        try:
            if event_type == 'StasisStart':
                await self.handle_stasis_start(event, channel, channel_id, server)
            elif event_type == 'ChannelStateChange':
                await self.handle_channel_state_change(event, channel, channel_id, server)  
            elif event_type == 'ChannelDestroyed':
                await self.handle_channel_destroyed(event, channel, channel_id, server)
                
        except Exception as e:
            logger.error(f"❌ Error in {event_type} handler: {e}")
            
    async def handle_stasis_start(self, event, channel, channel_id, server):
        """
        CRITICAL FIX: Handle Stasis start respecting YOUR workflow
        """
        variables = channel.get('channelvars', {})
        call_type = variables.get('CALL_TYPE')
        campaign_id = variables.get('CAMPAIGN_ID')
        lead_id = variables.get('LEAD_ID')
        
        logger.info(f"📞 Stasis Start: {call_type} call, channel: {channel_id}")
        
        if call_type == 'autodial':
            # MAIN FIX: Customer answered, assign to ready agent (YOUR way)
            await self.handle_autodial_answered_your_way(
                channel_id, campaign_id, lead_id, server
            )
        elif call_type == 'agent_leg':
            # Agent leg connected for persistent session (preserve your existing flow)
            await self.handle_agent_leg_connected(channel_id, variables, server)
        elif call_type == 'customer_leg':
            # Customer leg for existing agent session (preserve your existing flow)
            await self.handle_customer_leg_your_way(channel_id, variables, server)
            
    async def handle_autodial_answered_your_way(self, channel_id, campaign_id, lead_id, server):
        """
        CRITICAL FIX: Handle autodial answer preserving YOUR existing workflow
        
        Your workflow:
        1. Customer call answered (came from predictive_dialer.py)
        2. Find ready agent (AgentDialerSession with status='ready') 
        3. Add customer channel to agent's existing bridge
        4. Notify agent via WebSocket for screen pop
        """
        from agents.models import AgentDialerSession
        from campaigns.models import Campaign  
        from telephony.models import CallLog
        from telephony.services import AsteriskService
        from leads.models import Lead
        
        try:
            logger.info(f"🎯 Autodial answered: {channel_id}, finding ready agent...")
            
            # Get campaign
            campaign = await sync_to_async(Campaign.objects.get)(id=campaign_id)
            
            # FIND READY AGENT using YOUR existing logic
            ready_agent_session = await self.find_ready_agent_your_way(campaign)
            
            if not ready_agent_session:
                logger.warning(f"⚠️ No ready agents for {campaign.name} - hanging up")
                service = AsteriskService(server)
                await sync_to_async(service.hangup_channel)(channel_id)
                return
                
            agent = ready_agent_session.agent
            logger.info(f"✅ Assigning to agent: {agent.username}")
            
            # Update agent session status (YOUR way)
            ready_agent_session.status = 'on_call'  
            ready_agent_session.current_call_channel_id = channel_id
            ready_agent_session.last_call_start = timezone.now()
            await sync_to_async(ready_agent_session.save)()
            
            # CRITICAL FIX: Add customer channel to agent's bridge (YOUR existing approach)
            service = AsteriskService(server)
            
            if ready_agent_session.agent_bridge_id:
                logger.info(f"🔗 Adding {channel_id} to bridge {ready_agent_session.agent_bridge_id}")
                result = await sync_to_async(service.add_channel_to_bridge)(
                    ready_agent_session.agent_bridge_id, channel_id
                )
                
                if result.get('success'):
                    logger.info("✅ Customer connected to agent bridge")
                    
                    # Create/update call log
                    await self.create_call_log_your_way(
                        channel_id, agent, campaign, lead_id
                    )
                    
                    # Get lead info for screen pop
                    lead_info = await self.get_lead_info(lead_id)
                    
                    # Notify agent (YOUR existing WebSocket approach) 
                    await self.notify_agent_call_connected(
                        agent, channel_id, lead_info, campaign
                    )
                    
                    # Clean up Redis
                    await self.cleanup_redis_dialing(campaign_id, lead_id)
                    
                else:
                    logger.error(f"❌ Failed to add to bridge: {result.get('error')}")
                    await self.handle_assignment_failure(
                        ready_agent_session, channel_id, server
                    )
            else:
                logger.error(f"❌ Agent {agent.username} has no bridge - check session creation")
                await self.handle_assignment_failure(ready_agent_session, channel_id, server)
                
        except Exception as e:
            logger.error(f"💥 Error in autodial answer handler: {e}")
            # Cleanup on error
            try:
                service = AsteriskService(server)
                await sync_to_async(service.hangup_channel)(channel_id)
            except:
                pass
                
    async def find_ready_agent_your_way(self, campaign):
        """
        Find ready agent using YOUR existing workflow logic
        
        Agent must be:
        1. Have AgentDialerSession for this campaign  
        2. Session status = 'ready'
        3. Softphone registered
        4. Not in wrapup timeout
        """
        from agents.models import AgentDialerSession
        from users.models import AgentStatus
        from agents.telephony_service import AgentTelephonyService
        
        # Get ready sessions for campaign (YOUR approach)
        ready_sessions = AgentDialerSession.objects.filter(
            campaign=campaign,
            status='ready'  # This is YOUR key status check
        ).select_related('agent').order_by('last_call_end', 'login_time')
        
        ready_sessions_list = await sync_to_async(list)(ready_sessions)
        logger.debug(f"🔍 Found {len(ready_sessions_list)} ready sessions")
        
        for session in ready_sessions_list:
            agent = session.agent
            
            # Check agent overall status (YOUR logic)
            try:
                agent_status = await sync_to_async(
                    lambda: getattr(agent, 'agent_status', None)
                )()
                
                if not agent_status or agent_status.status != 'available':
                    logger.debug(f"❌ {agent.username} not available: {agent_status.status if agent_status else None}")
                    continue
                    
            except Exception as e:
                logger.warning(f"⚠️ Status check error for {agent.username}: {e}")
                continue
                
            # Check softphone registration (YOUR requirement) 
            try:
                telephony_service = AgentTelephonyService(agent)
                is_registered = await sync_to_async(
                    telephony_service.is_extension_registered
                )()
                
                if not is_registered:
                    logger.warning(f"📞 {agent.username} softphone not registered")
                    continue
                    
            except Exception as e:
                logger.warning(f"⚠️ Registration check error for {agent.username}: {e}")
                continue
                
            # Check wrapup timeout (YOUR logic)
            if session.last_call_end and campaign.wrapup_timeout > 0:
                wrapup_end = session.last_call_end + timedelta(seconds=campaign.wrapup_timeout)
                if timezone.now() < wrapup_end:
                    logger.debug(f"⏳ {agent.username} still in wrapup")
                    continue
                    
            # Check has bridge (YOUR session approach)
            if not session.agent_bridge_id:
                logger.warning(f"🌉 {agent.username} session has no bridge")
                continue
                
            # This agent passes all checks
            logger.info(f"🎯 Selected agent: {agent.username}")
            return session
            
        logger.warning("❌ No ready agents found after all checks")
        return None
        
    async def handle_channel_state_change(self, event, channel, channel_id, server):
        """Handle channel state changes"""
        state = channel.get('state')
        
        if state == 'Up':
            await self.handle_channel_up(channel_id)
        elif state == 'Ringing':
            await self.handle_channel_ringing(channel_id)
            
    async def handle_channel_up(self, channel_id):
        """Handle when channel goes up (answered)"""
        from telephony.models import CallLog
        
        # Update call log
        call_log = await sync_to_async(CallLog.objects.filter)(channel=channel_id)
        call_log = await sync_to_async(call_log.first)()
        
        if call_log and not call_log.answer_time:
            call_log.answer_time = timezone.now()
            call_log.call_status = 'answered'
            await sync_to_async(call_log.save)()
            
    async def handle_channel_destroyed(self, event, channel, channel_id, server):
        """Handle channel hangup - YOUR existing cleanup"""
        from telephony.models import CallLog
        from agents.models import AgentDialerSession
        
        # Update call log
        call_log = await sync_to_async(CallLog.objects.filter)(channel=channel_id)
        call_log = await sync_to_async(call_log.first)()
        
        if call_log and not call_log.end_time:
            call_log.end_time = timezone.now()
            call_log.call_status = 'completed'
            
            # Calculate talk time
            if call_log.answer_time:
                talk_duration = (call_log.end_time - call_log.answer_time).total_seconds()
                call_log.talk_duration = int(talk_duration)
                
            await sync_to_async(call_log.save)()
            
            # Update agent session (YOUR way)
            if call_log.agent:
                session = await sync_to_async(AgentDialerSession.objects.filter)(
                    agent=call_log.agent,
                    current_call_channel_id=channel_id
                )
                session_obj = await sync_to_async(session.first)()
                
                if session_obj:
                    session_obj.status = 'ready'  # Back to ready (YOUR workflow)
                    session_obj.current_call_channel_id = None
                    session_obj.last_call_end = timezone.now()
                    await sync_to_async(session_obj.save)()
                
                # Notify agent call ended (YOUR WebSocket approach)
                await self.notify_agent_call_ended(call_log)
                
    # Helper methods for YOUR workflow
    
    async def create_call_log_your_way(self, channel_id, agent, campaign, lead_id):
        """Create call log the way YOUR system expects"""
        from telephony.models import CallLog
        
        call_log, created = await sync_to_async(CallLog.objects.get_or_create)(
            channel=channel_id,
            defaults={
                'agent': agent,
                'campaign': campaign, 
                'lead_id': lead_id,
                'call_type': 'outbound',
                'call_status': 'answered',
                'start_time': timezone.now(),
                'answer_time': timezone.now(),
            }
        )
        
        if not created:
            # Update existing 
            call_log.agent = agent
            call_log.campaign = campaign
            call_log.call_status = 'answered'
            call_log.answer_time = timezone.now()
            await sync_to_async(call_log.save)()
            
        return call_log
        
    async def get_lead_info(self, lead_id):
        """Get lead info for screen pop"""
        if not lead_id:
            return {}
            
        try:
            from leads.models import Lead
            lead = await sync_to_async(Lead.objects.get)(id=lead_id)
            
            return {
                'id': lead.id,
                'first_name': lead.first_name,
                'last_name': lead.last_name,
                'phone_number': lead.phone_number,
                'email': lead.email,
                'company': lead.company,
                'city': lead.city,
                'state': lead.state,
                'status': lead.status,
                'notes': lead.notes or ''
            }
        except Exception as e:
            logger.error(f"❌ Error getting lead {lead_id}: {e}")
            return {}
            
    async def notify_agent_call_connected(self, agent, channel_id, lead_info, campaign):
        """Send notification to agent using YOUR WebSocket approach"""
        try:
            await self.channel_layer.group_send(
                f"agent_{agent.id}",
                {
                    'type': 'call_event',  # YOUR event type
                    'data': {
                        'type': 'call_connected',
                        'channel_id': channel_id,
                        'lead': lead_info,
                        'campaign': campaign.name,
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
            logger.debug(f"📨 Notified agent {agent.username}")
        except Exception as e:
            logger.error(f"❌ Notification error: {e}")
            
    async def notify_agent_call_ended(self, call_log):
        """Notify agent call ended using YOUR approach"""
        try:
            await self.channel_layer.group_send(
                f"agent_{call_log.agent.id}",
                {
                    'type': 'call_event',
                    'data': {
                        'type': 'call_ended',
                        'call_id': call_log.id,
                        'duration': call_log.talk_duration,
                        'disposition_required': True,
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
        except Exception as e:
            logger.error(f"❌ End notification error: {e}")
            
    async def cleanup_redis_dialing(self, campaign_id, lead_id):
        """Clean up Redis dialing state"""
        try:
            from campaigns.services import HopperService
            await sync_to_async(HopperService.unregister_dialing)(campaign_id, lead_id)
        except Exception as e:
            logger.error(f"❌ Redis cleanup error: {e}")
            
    async def handle_assignment_failure(self, agent_session, channel_id, server):
        """Handle when agent assignment fails"""
        # Reset agent session
        agent_session.status = 'ready'
        agent_session.current_call_channel_id = None
        await sync_to_async(agent_session.save)()
        
        # Hang up customer call
        try:
            service = AsteriskService(server) 
            await sync_to_async(service.hangup_channel)(channel_id)
        except:
            pass
            
    async def handle_agent_leg_connected(self, channel_id, variables, server):
        """Handle agent leg connection (YOUR existing flow)"""
        agent_id = variables.get('AGENT_ID')
        if not agent_id:
            return
            
        try:
            from agents.models import AgentDialerSession
            from users.models import User
            
            agent = await sync_to_async(User.objects.get)(id=agent_id)
            
            # Update session with agent channel (YOUR approach)
            session = await sync_to_async(AgentDialerSession.objects.filter)(
                agent=agent,
                status='connecting'
            )
            session_obj = await sync_to_async(session.first)()
            
            if session_obj:
                session_obj.agent_channel_id = channel_id
                session_obj.status = 'ready'  # Now ready to take calls
                await sync_to_async(session_obj.save)()
                
                logger.info(f"✅ Agent {agent.username} leg connected and ready")
                
        except Exception as e:
            logger.error(f"❌ Agent leg error: {e}")
            
    async def handle_customer_leg_your_way(self, channel_id, variables, server):
        """Handle customer leg (YOUR existing manual dial flow)"""
        # This preserves your existing manual dial approach
        agent_id = variables.get('AGENT_ID')
        if agent_id:
            try:
                from telephony.models import CallLog
                
                # Create call log for manual call
                await sync_to_async(CallLog.objects.create)(
                    channel=channel_id,
                    agent_id=agent_id,
                    call_type='outbound',
                    call_status='ringing', 
                    start_time=timezone.now()
                )
                
            except Exception as e:
                logger.error(f"❌ Manual call log error: {e}")

    async def handle_channel_ringing(self, channel_id):
        """Handle when channel starts ringing"""
        logger.debug(f"📞 Channel ringing: {channel_id}")
