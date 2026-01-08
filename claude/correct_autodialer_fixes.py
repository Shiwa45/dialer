#!/usr/bin/env python
"""
CORRECT Autodialer Fixes - Preserving Your Existing Workflow
============================================================

Based on Asterisk logs and existing code analysis, here are the REAL issues to fix:

ISSUES IDENTIFIED:
1. "Inactive Stasis app 'autodialer' missed message" - ARI worker not running
2. Agent assignment happens but call not delivered to agent softphone  
3. Call answered but not connected to waiting agent
4. Agent ready status workflow should be preserved (not Vicidial conference approach)

YOUR EXISTING WORKFLOW (CORRECT):
- Agent logs in → creates AgentDialerSession with status 'connecting'
- Agent softphone registers → AgentDialerSession status becomes 'ready'  
- Only when agent is 'ready' → predictive dialer starts making calls
- Call answered → should be assigned to longest-waiting ready agent
- Agent sees call in softphone AND agent panel

FIXES NEEDED:
1. Fix ARI worker startup and connection
2. Fix agent assignment logic in answered call handler
3. Preserve existing UI design
4. Fix disposition handling without changing core workflow
"""

import os
import sys
import django

if __name__ == "__main__":
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
    django.setup()

# ============================================================================
# FIX 1: Corrected ARI Worker That Respects Your Existing Workflow  
# ============================================================================

def get_corrected_ari_worker():
    """
    Fixed ARI worker that works with your existing agent session workflow
    Replace your telephony/management/commands/ari_worker.py with this
    """
    return '''
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
    help = 'ARI Worker for your existing autodialer workflow'
    
    def add_arguments(self, parser):
        parser.add_argument('--debug', action='store_true', help='Enable debug logging')
        
    def handle(self, *args, **options):
        if options['debug']:
            logging.getLogger().setLevel(logging.DEBUG)
            
        self.channel_layer = get_channel_layer()
        
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting ARI Worker (Your Existing Workflow)...')
        )
        
        try:
            asyncio.run(self.run_ari_worker())
        except KeyboardInterrupt:
            self.stdout.write('✋ ARI Worker stopped')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'💥 ARI Worker error: {e}'))
            logger.exception("ARI Worker crashed")
            
    async def run_ari_worker(self):
        """Main ARI worker loop"""
        from telephony.models import AsteriskServer
        
        # Get active server
        server = await sync_to_async(AsteriskServer.objects.filter)(is_active=True)
        server = await sync_to_async(server.first)()
        
        if not server:
            logger.error("❌ No active Asterisk server found")
            return
            
        logger.info(f"🖥️ Using Asterisk server: {server.server_ip}")
        
        # Connect to ARI with proper error handling
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
            
            logger.info("✅ ARI connected - autodialer app is now ACTIVE")
            
            # Process events
            await self.process_ari_events(ws, server)
            
        except Exception as e:
            logger.error(f"❌ ARI connection failed: {e}")
            
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
        Handle Stasis start - KEY FIX for your workflow
        """
        variables = channel.get('channelvars', {})
        call_type = variables.get('CALL_TYPE')
        campaign_id = variables.get('CAMPAIGN_ID')
        lead_id = variables.get('LEAD_ID')
        
        logger.info(f"📞 Stasis Start: {call_type} call, channel: {channel_id}")
        
        if call_type == 'autodial':
            # This is YOUR workflow - customer answered, assign to agent
            await self.handle_autodial_answered_your_way(
                channel_id, campaign_id, lead_id, server
            )
        elif call_type == 'agent_leg':
            # Agent leg connected for persistent session (your existing flow)
            await self.handle_agent_leg_connected(channel_id, variables, server)
        elif call_type == 'customer_leg':
            # Customer leg for existing agent session (your existing flow)
            await self.handle_customer_leg_your_way(channel_id, variables, server)
            
    async def handle_autodial_answered_your_way(self, channel_id, campaign_id, lead_id, server):
        """
        CRITICAL FIX: Handle autodial answer with YOUR existing workflow
        
        Your workflow:
        1. Customer call answered
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
            
            # Add customer channel to agent's bridge (YOUR existing approach)
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

if __name__ == "__main__":
    print("Fixed ARI Worker for Your Existing Workflow")
    print("=" * 50)
    print("✅ Preserves your AgentDialerSession approach")
    print("✅ Respects 'ready' status requirement")  
    print("✅ Uses existing bridge assignment logic")
    print("✅ Maintains your WebSocket event structure")
    print("✅ Fixes the 'Inactive Stasis app' error")
'''

# ============================================================================
# FIX 2: Simple Disposition Fix (Keeping Your UI)
# ============================================================================

def get_simple_disposition_fix():
    """
    Simple disposition fix that works with your existing UI
    Just adds the missing API endpoints without changing design
    """
    return '''
# Add these to your agents/views_simple.py (keeping your existing views)

@login_required
@agent_required
@require_http_methods(["POST"])
@csrf_exempt
def submit_disposition(request):
    """Simple disposition submission for your existing workflow"""
    try:
        data = json.loads(request.body)
        call_id = data.get('call_id')
        disposition_id = data.get('disposition_id')
        notes = data.get('notes', '')
        
        if not call_id or not disposition_id:
            return JsonResponse({
                'success': False,
                'error': 'Call ID and disposition required'
            })
        
        from telephony.models import CallLog
        from campaigns.models import Disposition
        
        # Get call log
        call_log = CallLog.objects.filter(
            id=call_id,
            agent=request.user
        ).first()
        
        if not call_log:
            return JsonResponse({
                'success': False,
                'error': 'Call not found'
            })
            
        # Get disposition
        disposition = Disposition.objects.filter(id=disposition_id).first()
        if not disposition:
            return JsonResponse({
                'success': False,
                'error': 'Invalid disposition'
            })
        
        # Update call log
        call_log.disposition = disposition
        call_log.disposition_time = timezone.now()
        call_log.agent_notes = notes
        call_log.call_status = 'dispositioned'
        call_log.save()
        
        # Update lead if exists
        if call_log.lead_id:
            from leads.models import Lead
            lead = Lead.objects.filter(id=call_log.lead_id).first()
            if lead:
                if disposition.is_sale:
                    lead.status = 'sale'
                elif disposition.schedule_callback:
                    lead.status = 'callback' 
                else:
                    lead.status = disposition.category
                lead.last_contact_date = timezone.now()
                lead.save()
        
        # Update agent to available if auto_available
        if disposition.auto_available:
            from users.models import AgentStatus
            AgentStatus.objects.filter(user=request.user).update(
                status='available'
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Disposition submitted successfully'
        })
        
    except Exception as e:
        logger.error(f"Disposition error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required 
@agent_required
@require_http_methods(["GET"])
def get_dispositions(request):
    """Get available dispositions for current campaign"""
    try:
        from campaigns.models import Disposition
        
        # Get dispositions (you can filter by campaign if needed)
        dispositions = Disposition.objects.filter(is_active=True).order_by('sort_order')
        
        disposition_data = []
        for disp in dispositions:
            disposition_data.append({
                'id': disp.id,
                'name': disp.name,
                'category': disp.category,
                'is_sale': disp.is_sale,
                'schedule_callback': disp.schedule_callback,
                'auto_available': disp.auto_available
            })
        
        return JsonResponse({
            'success': True,
            'dispositions': disposition_data
        })
        
    except Exception as e:
        logger.error(f"Get dispositions error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

# Add these URLs to your agents/urls.py:
path('api/submit-disposition/', views_simple.submit_disposition, name='submit_disposition'),
path('api/dispositions/', views_simple.get_dispositions, name='get_dispositions'),
'''

# ============================================================================
# FIX 3: Minimal JavaScript Fix (Preserves Your UI)
# ============================================================================

def get_minimal_js_fix():
    """
    Minimal JavaScript that adds real-time updates to your existing UI
    without changing the design
    """
    return '''
<script>
// Minimal fix for your existing simple_dashboard.html - ADD this before </body>

(function() {
    // WebSocket connection for real-time updates
    let socket = null;
    let currentCall = null;
    let dispositionModal = null;
    
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/agent/`;
        
        socket = new WebSocket(wsUrl);
        
        socket.onopen = function() {
            console.log('✅ WebSocket connected');
            updateConnectionStatus(true);
        };
        
        socket.onclose = function() {
            console.log('🔌 WebSocket disconnected');
            updateConnectionStatus(false);
            // Reconnect after 3 seconds
            setTimeout(connectWebSocket, 3000);
        };
        
        socket.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (e) {
                console.error('WebSocket message error:', e);
            }
        };
    }
    
    function handleWebSocketMessage(data) {
        console.log('📨 Received:', data.type);
        
        if (data.type === 'call_connected') {
            handleCallConnected(data.data);
        } else if (data.type === 'call_ended') {
            handleCallEnded(data.data);
        } else if (data.type === 'status_update') {
            handleStatusUpdate(data.data);
        }
    }
    
    function handleCallConnected(callData) {
        console.log('📞 Call connected');
        currentCall = callData;
        
        // Update your existing UI elements
        const callPanel = document.querySelector('[data-call-panel]');
        const callPlaceholder = document.querySelector('[data-call-placeholder]');
        const callDetails = document.querySelector('[data-call-details]');
        
        if (callPlaceholder) callPlaceholder.style.display = 'none';
        if (callDetails) callDetails.hidden = false;
        
        // Update call information in your existing elements
        const numberEl = document.querySelector('[data-call-number]');
        const stateEl = document.querySelector('[data-call-state]');
        
        if (numberEl) numberEl.textContent = callData.lead?.phone_number || '';
        if (stateEl) {
            stateEl.textContent = 'Connected';
            stateEl.setAttribute('data-state', 'connected');
        }
        
        // Show lead information in your existing lead card
        if (callData.lead) {
            showLeadInfo(callData.lead);
        }
        
        // Enable disposition button
        const dispBtn = document.querySelector('[data-open-disposition]');
        if (dispBtn) dispBtn.disabled = false;
        
        startCallTimer();
    }
    
    function handleCallEnded(callData) {
        console.log('📴 Call ended');
        
        // Show disposition modal after short delay
        if (callData.disposition_required && currentCall) {
            setTimeout(() => {
                showDispositionModal(callData.call_id);
            }, 500);
        }
        
        stopCallTimer();
    }
    
    function showLeadInfo(lead) {
        // Update your existing lead card elements
        const leadCard = document.querySelector('[data-lead-card]');
        if (leadCard) leadCard.hidden = false;
        
        const nameEl = document.querySelector('[data-lead-name]');
        const phoneEl = document.querySelector('[data-lead-phone]');
        const emailEl = document.querySelector('[data-lead-email]');
        const companyEl = document.querySelector('[data-lead-company]');
        
        if (nameEl) nameEl.textContent = `${lead.first_name || ''} ${lead.last_name || ''}`.trim();
        if (phoneEl) phoneEl.textContent = lead.phone_number || '—';
        if (emailEl) emailEl.textContent = lead.email || '—';
        if (companyEl) companyEl.textContent = lead.company || '—';
    }
    
    function showDispositionModal(callId) {
        if (!dispositionModal) {
            createDispositionModal();
        }
        
        document.getElementById('modalCallId').value = callId;
        loadDispositions();
        dispositionModal.style.display = 'flex';
    }
    
    function createDispositionModal() {
        // Create minimal modal that matches your theme
        const modalHTML = `
            <div id="dispositionModal" style="
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(0,0,0,0.7);
                display: none;
                align-items: center;
                justify-content: center;
                z-index: 1000;
            ">
                <div style="
                    background: var(--card, #ffffff);
                    border: 1px solid var(--border, #e2e8f0);
                    border-radius: 8px;
                    padding: 2rem;
                    width: 90%;
                    max-width: 500px;
                ">
                    <h3 style="margin: 0 0 1rem; color: var(--text, #1e293b);">Call Disposition</h3>
                    
                    <form id="dispositionForm">
                        <div style="margin-bottom: 1rem;">
                            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">
                                Disposition *
                            </label>
                            <select id="dispositionSelect" required style="
                                width: 100%;
                                padding: 0.75rem;
                                border: 1px solid var(--border, #e2e8f0);
                                border-radius: 6px;
                                background: var(--card, #ffffff);
                            ">
                                <option value="">Select disposition...</option>
                            </select>
                        </div>
                        
                        <div style="margin-bottom: 1rem;">
                            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">
                                Notes
                            </label>
                            <textarea id="dispositionNotes" rows="3" style="
                                width: 100%;
                                padding: 0.75rem;
                                border: 1px solid var(--border, #e2e8f0);
                                border-radius: 6px;
                                background: var(--card, #ffffff);
                                resize: vertical;
                            "></textarea>
                        </div>
                        
                        <input type="hidden" id="modalCallId">
                        
                        <div style="display: flex; gap: 0.75rem; justify-content: flex-end;">
                            <button type="button" onclick="closeDispositionModal()" style="
                                padding: 0.75rem 1.5rem;
                                border: 1px solid var(--border, #e2e8f0);
                                background: transparent;
                                border-radius: 6px;
                                cursor: pointer;
                            ">Cancel</button>
                            <button type="submit" style="
                                padding: 0.75rem 1.5rem;
                                border: none;
                                background: var(--accent, #dc2626);
                                color: white;
                                border-radius: 6px;
                                cursor: pointer;
                            ">Submit</button>
                        </div>
                    </form>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        dispositionModal = document.getElementById('dispositionModal');
        
        document.getElementById('dispositionForm').addEventListener('submit', submitDisposition);
    }
    
    async function loadDispositions() {
        try {
            const response = await fetch('/agents/api/dispositions/');
            const data = await response.json();
            
            if (data.success) {
                const select = document.getElementById('dispositionSelect');
                select.innerHTML = '<option value="">Select disposition...</option>';
                
                data.dispositions.forEach(disp => {
                    const option = document.createElement('option');
                    option.value = disp.id;
                    option.textContent = disp.name;
                    select.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Failed to load dispositions:', error);
        }
    }
    
    async function submitDisposition(e) {
        e.preventDefault();
        
        const callId = document.getElementById('modalCallId').value;
        const dispositionId = document.getElementById('dispositionSelect').value;
        const notes = document.getElementById('dispositionNotes').value;
        
        if (!dispositionId) {
            alert('Please select a disposition');
            return;
        }
        
        try {
            const response = await fetch('/agents/api/submit-disposition/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({
                    call_id: callId,
                    disposition_id: dispositionId,
                    notes: notes
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                closeDispositionModal();
                clearCallDisplay();
                alert('Disposition submitted successfully');
            } else {
                alert('Error: ' + data.error);
            }
            
        } catch (error) {
            console.error('Disposition submission error:', error);
            alert('Failed to submit disposition');
        }
    }
    
    window.closeDispositionModal = function() {
        if (dispositionModal) {
            dispositionModal.style.display = 'none';
            document.getElementById('dispositionForm').reset();
        }
    };
    
    function clearCallDisplay() {
        currentCall = null;
        
        const callPlaceholder = document.querySelector('[data-call-placeholder]');
        const callDetails = document.querySelector('[data-call-details]');
        const leadCard = document.querySelector('[data-lead-card]');
        const dispBtn = document.querySelector('[data-open-disposition]');
        
        if (callPlaceholder) callPlaceholder.style.display = 'block';
        if (callDetails) callDetails.hidden = true;
        if (leadCard) leadCard.hidden = true;
        if (dispBtn) dispBtn.disabled = true;
        
        stopCallTimer();
    }
    
    let timerInterval = null;
    function startCallTimer() {
        stopCallTimer();
        const timerEl = document.querySelector('[data-call-duration]');
        if (!timerEl) return;
        
        let seconds = 0;
        timerInterval = setInterval(() => {
            seconds++;
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            timerEl.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }, 1000);
    }
    
    function stopCallTimer() {
        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
        }
    }
    
    function updateConnectionStatus(connected) {
        // Update any connection indicator in your UI
        console.log(connected ? 'Connected' : 'Disconnected');
    }
    
    function getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    }
    
    function handleStatusUpdate(data) {
        console.log('Status update:', data);
        // Update status displays in your UI if needed
    }
    
    // Initialize when page loads
    document.addEventListener('DOMContentLoaded', function() {
        connectWebSocket();
        
        // Add click handler for disposition button
        const dispBtn = document.querySelector('[data-open-disposition]');
        if (dispBtn) {
            dispBtn.addEventListener('click', function() {
                if (currentCall) {
                    showDispositionModal(currentCall.call_id || 'manual');
                }
            });
        }
    });
})();
</script>
'''

print("🎯 CORRECTED FIXES for Your Existing Workflow")
print("=" * 60)
print()
print("✅ ISSUES IDENTIFIED FROM YOUR LOGS:")
print("1. 'Inactive Stasis app autodialer missed message' - ARI worker not connected")
print("2. Calls answered but not assigned to agents - missing assignment logic")
print("3. Agent ready workflow being changed - should preserve your approach")
print()
print("✅ FIXES PROVIDED:")
print("1. Corrected ARI Worker that connects properly and preserves your workflow")
print("2. Simple disposition API that works with your existing UI")
print("3. Minimal JavaScript that adds real-time updates without changing design")
print()
print("✅ YOUR WORKFLOW PRESERVED:")
print("- Agent logs in → AgentDialerSession created")
print("- Softphone registers → Session becomes 'ready'")  
print("- Predictive dialer only works when agents are 'ready'")
print("- Answered calls assigned to longest-waiting ready agent")
print("- Call connected to agent's existing bridge")
print("- Agent sees call in softphone AND panel")
print()
print("🚀 NEXT STEPS:")
print("1. Replace ari_worker.py with the corrected version")
print("2. Add the simple disposition views to your views_simple.py")
print("3. Add the minimal JavaScript to your simple_dashboard.html")
print("4. Ensure ARI worker is running: python manage.py ari_worker")
