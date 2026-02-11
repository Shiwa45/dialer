"""
ARI Worker - Real-time Asterisk ARI Event Handler (IMPROVED)

Phase 1 Fixes Applied:
- 1.1: Immediate call notification on StasisStart (before bridging)
- 1.3: Force cleanup of agent sessions on disposition/hangup

This worker connects to Asterisk ARI WebSocket and handles:
- Call state changes
- Agent session management
- Real-time WebSocket notifications to agents
"""

import asyncio
import json
import logging
import websockets
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from telephony.models import AsteriskServer
from calls.models import CallLog
from campaigns.models import OutboundQueue, DialerHopper
from agents.models import AgentDialerSession
from users.models import AgentStatus
from telephony.services import AsteriskService
from users.tracking import get_tracker

logger = logging.getLogger(__name__)


def _normalize_id(value):
    """Convert string ID to int, return None if invalid"""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


class Command(BaseCommand):
    help = 'Run ARI event worker to manage agent/customer channels and bridges'

    def handle(self, *args, **options):
        self.tracker = get_tracker()
        server = AsteriskServer.objects.filter(is_active=True).first()
        if not server:
            self.stderr.write('No active AsteriskServer found')
            return

        ari_url = f"ws://{server.ari_host}:{server.ari_port}/ari/events?app={server.ari_application}&api_key={server.ari_username}:{server.ari_password}"
        self.stdout.write(self.style.SUCCESS(f"Connecting to ARI: {ari_url.replace(server.ari_password, '***')}"))
        self.channel_layer = get_channel_layer()

        async def run():
            while True:
                try:
                    async with websockets.connect(ari_url, ping_interval=10, ping_timeout=10) as ws:
                        logger.info("Connected to Asterisk ARI")
                        self.stdout.write(self.style.SUCCESS("Connected to Asterisk ARI WebSocket"))
                        async for message in ws:
                            await asyncio.get_event_loop().run_in_executor(
                                None, self.process_event, server, message
                            )
                except websockets.ConnectionClosed:
                    logger.warning("ARI WebSocket connection closed, reconnecting in 5s...")
                    self.stdout.write(self.style.WARNING("Connection closed, reconnecting..."))
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"ARI WebSocket error: {e}", exc_info=True)
                    self.stdout.write(self.style.ERROR(f"Error: {e}"))
                    await asyncio.sleep(5)

        asyncio.run(run())

    def process_event(self, server, message):
        """Process incoming ARI event"""
        try:
            event = json.loads(message)
            etype = event.get('type')
            
            if etype in ['StasisStart', 'ChannelStateChange', 'ChannelDestroyed']:
                logger.info(f"Processing ARI event: {etype}")
                self._handle_event(server, event)
            
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from ARI: {message[:100]}")
        except Exception as e:
            logger.error(f"Error processing ARI event: {e}", exc_info=True)

    def _handle_event(self, server, event):
        """Route event to appropriate handler"""
        etype = event.get('type')
        channel = event.get('channel', {})
        chan_id = channel.get('id')
        chan_state = channel.get('state', '').lower()
        
        # Extract variables from channel and args
        chan_vars = channel.get('channelvars', {})
        args = event.get('args', [])
        
        # Parse variables
        call_type = chan_vars.get('CALL_TYPE')
        campaign_id = chan_vars.get('CAMPAIGN_ID')
        lead_id = chan_vars.get('LEAD_ID')
        hopper_id = chan_vars.get('HOPPER_ID')
        customer_number = chan_vars.get('CUSTOMER_NUMBER')
        bridge_id = chan_vars.get('BRIDGE_ID')
        agent_id = chan_vars.get('AGENT_ID')
        queue_id = chan_vars.get('QUEUE_ID')
        target_agent_id = chan_vars.get('TARGET_AGENT_ID')

        # Also parse from args (Stasis application arguments)
        for a in args:
            if isinstance(a, str) and '=' in a:
                k, v = a.split('=', 1)
                if k == 'BRIDGE_ID': bridge_id = bridge_id or v
                elif k == 'CALL_TYPE': call_type = call_type or v
                elif k == 'AGENT_ID': agent_id = agent_id or v
                elif k == 'QUEUE_ID': queue_id = queue_id or v
                elif k == 'CAMPAIGN_ID': campaign_id = campaign_id or v
                elif k == 'CUSTOMER_NUMBER': customer_number = customer_number or v
                elif k == 'LEAD_ID': lead_id = lead_id or v
                elif k == 'HOPPER_ID': hopper_id = hopper_id or v
                elif k == 'TARGET_AGENT_ID': target_agent_id = target_agent_id or v

        # Support positional args: call_type, campaign_id, lead_id, hopper_id
        if args and isinstance(args, list):
            if not call_type and len(args) > 0: call_type = args[0]
            if not campaign_id and len(args) > 1: campaign_id = args[1]
            if not lead_id and len(args) > 2: lead_id = args[2]
            if not hopper_id and len(args) > 3: hopper_id = args[3]

        # Normalize IDs
        campaign_id = _normalize_id(campaign_id)
        lead_id = _normalize_id(lead_id)
        hopper_id = _normalize_id(hopper_id)
        agent_id = _normalize_id(agent_id)
        target_agent_id = _normalize_id(target_agent_id)
        queue_id = _normalize_id(queue_id)

        amd_status = chan_vars.get('AMDSTATUS')

        if etype == 'StasisStart':
            self._handle_stasis_start(
                server, chan_id, bridge_id, call_type, agent_id, target_agent_id,
                campaign_id, lead_id, hopper_id, customer_number, queue_id, amd_status
            )
        
        elif etype == 'ChannelStateChange':
            self._handle_channel_state_change(
                server, chan_id, chan_state, call_type, agent_id, target_agent_id,
                campaign_id, lead_id, customer_number, queue_id
            )
        
        elif etype == 'ChannelLeftBridge':
            # CRITICAL: This event fires when customer hangs up while in bridge
            logger.info(f"ChannelLeftBridge: channel={chan_id}")
            self._handle_channel_destroyed(
                server, chan_id, call_type, agent_id, target_agent_id,
                campaign_id, lead_id, queue_id
            )
        
        elif etype == 'ChannelDestroyed':
            self._handle_channel_destroyed(
                server, chan_id, call_type, agent_id, target_agent_id,
                campaign_id, lead_id, queue_id
            )

    def _handle_stasis_start(self, server, chan_id, bridge_id, call_type, agent_id, 
                             target_agent_id, campaign_id, lead_id, hopper_id, 
                             customer_number, queue_id, amd_status=None):
        """
        Handle StasisStart event - Channel entered Stasis application
        
        PHASE 1.1 FIX: Send immediate notification when autodial call starts
        PHASE 4.1: Handle AMD results
        """
        logger.info(f"StasisStart: channel={chan_id}, call_type={call_type}, lead={lead_id}")

        # Phase 4.1: AMD Handling
        if amd_status:
            from campaigns.amd_service import AMDService
            amd_service = AMDService()
            result = amd_service.parse_amd_result(amd_status)
            
            # Log the result
            logger.info(f"AMD Result for {chan_id}: {amd_status} -> {result}")
            
            if not amd_service.should_connect_to_agent(result):
                logger.info(f"AMD blocked call {chan_id} (Machine detected)")
                AsteriskService(server).hangup_channel(chan_id)
                return

        # Add to bridge if specified
        if bridge_id and chan_id:
            AsteriskService(server).add_channel_to_bridge(bridge_id, chan_id)

        # 1. AGENT LEG - Agent's softphone connected
        if call_type == 'agent_leg' and agent_id:
            AgentDialerSession.objects.filter(
                agent_id=agent_id, 
                status='connecting'
            ).update(status='ready', agent_channel_id=chan_id)
            
            self.broadcast_message(agent_id, {
                'type': 'status_update',
                'status': 'ready',
                'message': 'Softphone Connected'
            })

        # 2. AUTODIAL - Predictive dialer placing call
        elif call_type == 'autodial':
            # Check if this is an agent channel that needs to be bridged
            if hasattr(self, 'pending_bridges') and chan_id in self.pending_bridges:
                bridge_info = self.pending_bridges.pop(chan_id)
                customer_channel = bridge_info['customer_channel']
                
                logger.info(f"Agent answered! Bridging {chan_id} to customer {customer_channel}")
                
                # Create ARI bridge and add both channels
                try:
                    asterisk_service = AsteriskService(server)
                    bridge_result = asterisk_service.create_bridge_and_add_channels(
                        channel1=chan_id,
                        channel2=customer_channel
                    )
                    
                    if bridge_result.get('success'):
                        logger.info(f"Successfully bridged agent to customer")
                        
                        # Notify agent that call is connected
                        self.broadcast_message(bridge_info['agent_id'], {
                            'type': 'call_connected',
                            'call': {
                                'id': customer_channel,
                                'status': 'connected',
                                'lead_id': bridge_info['lead_id']
                            }
                        })
                    else:
                        logger.error(f"Failed to create bridge: {bridge_result.get('error')}")
                        
                except Exception as e:
                    logger.error(f"Error creating bridge: {e}")
                    
            # PHASE 1.1: Send IMMEDIATE notification that call is being placed
            # This fires BEFORE the call is answered, reducing perceived delay
            elif campaign_id and lead_id:
                self._send_call_incoming_notification(
                    server, campaign_id, lead_id, customer_number, chan_id
                )
        
        # 3. AGENT_ANSWER - Agent's softphone answered (for bridging)
        elif call_type == 'agent_answer':
            # Check if this is an agent channel that needs to be bridged
            if hasattr(self, 'pending_bridges') and chan_id in self.pending_bridges:
                bridge_info = self.pending_bridges.pop(chan_id)
                customer_channel = bridge_info['customer_channel']
                
                logger.info(f"Agent answered! Bridging {chan_id} to customer {customer_channel}")
                
                # Create ARI bridge and add both channels
                try:
                    asterisk_service = AsteriskService(server)
                    bridge_result = asterisk_service.create_bridge_and_add_channels(
                        channel1=chan_id,
                        channel2=customer_channel
                    )
                    
                    if bridge_result.get('success'):
                        logger.info(f"Successfully bridged agent to customer")
                        
                        # CRITICAL FIX: Subscribe to customer channel events to detect hangup
                        try:
                            import requests
                            ari_base_url = f"http://{server.ari_host}:{server.ari_port}/ari"
                            
                            # Subscribe to customer channel events
                            subscribe_response = requests.post(
                                f"{ari_base_url}/applications/autodialer/subscription",
                                auth=(server.ari_username, server.ari_password),
                                json={"eventSource": f"channel:{customer_channel}"},
                                timeout=5
                            )
                            logger.info(f"Subscribed to customer channel {customer_channel} events: {subscribe_response.status_code}")
                            
                            # Subscribe to agent channel events
                            subscribe_response2 = requests.post(
                                f"{ari_base_url}/applications/autodialer/subscription",
                                auth=(server.ari_username, server.ari_password),
                                json={"eventSource": f"channel:{chan_id}"},
                                timeout=5
                            )
                            logger.info(f"Subscribed to agent channel {chan_id} events: {subscribe_response2.status_code}")
                            
                            # Subscribe to bridge events
                            bridge_id = bridge_result.get('bridge_id')
                            if bridge_id:
                                subscribe_response3 = requests.post(
                                    f"{ari_base_url}/applications/autodialer/subscription",
                                    auth=(server.ari_username, server.ari_password),
                                    json={"eventSource": f"bridge:{bridge_id}"},
                                    timeout=5
                                )
                                logger.info(f"Subscribed to bridge {bridge_id} events: {subscribe_response3.status_code}")
                        except Exception as e:
                            logger.error(f"Error subscribing to channel events: {e}")
                        
                        # CRITICAL: Store agent channel ID in session for later disconnect
                        try:
                            from agents.models import AgentDialerSession
                            session = AgentDialerSession.objects.filter(agent_id=bridge_info['agent_id']).first()
                            if session:
                                session.agent_channel_id = chan_id  # Store agent channel
                                session.customer_channel_id = customer_channel
                                session.bridge_id = bridge_result.get('bridge_id')
                                session.status = 'busy'
                                session.save()
                                logger.info(f"Stored agent_channel_id={chan_id} in AgentDialerSession")
                            else:
                                logger.warning(f"AgentDialerSession not found for agent {bridge_info['agent_id']}")
                        except Exception as e:
                            logger.error(f"Error storing agent channel in session: {e}")

                        # Get the CallLog entry for the customer channel
                        call_log = CallLog.objects.filter(channel=customer_channel).first()
                        
                        # Check for recording filename from dialplan variables
                        recording_filename = AsteriskService(server).get_channel_variable(customer_channel, 'RECORDING_FILENAME')
                        
                        if recording_filename:
                            logger.info(f"Using dialplan recording: {recording_filename}")
                            if call_log:
                                call_log.recording_filename = recording_filename
                                call_log.save(update_fields=['recording_filename'])
                                
                                # Create recording entry
                                try:
                                    from telephony.recording_service import RecordingService
                                    recording_service = RecordingService()
                                    recording_service.create_recording_entry(call_log, filename=recording_filename)
                                except Exception as e:
                                    logger.error(f"Error creating recording entry: {e}")
                        else:
                            # Fallback to ARI recording if dialplan didn't set variable
                            logger.warning("RECORDING_FILENAME variable not found, starting ARI recording fallback")
                            
                            from telephony.recording_service import RecordingService
                            recording_service = RecordingService()
                            recording_filename = f"campaign_{bridge_info['campaign_id']}_lead_{bridge_info['lead_id']}_{customer_channel}"
                            
                            # Start ARI recording on customer channel
                            import requests
                            ari_base_url = f"http://{server.ari_host}:{server.ari_port}/ari"
                            recording_data = {
                                'name': recording_filename,
                                'format': 'wav',
                                'maxDurationSeconds': 3600,
                                'ifExists': 'overwrite'
                            }
                            
                            try:
                                response = requests.post(
                                    f"{ari_base_url}/channels/{customer_channel}/record",
                                    auth=(server.ari_username, server.ari_password),
                                    json=recording_data,
                                    timeout=10
                                )
                                
                                if response.status_code in [200, 201]:
                                    logger.info(f"Started ARI recording: {recording_filename}")
                                    # Update CallLog with recording info
                                    if call_log:
                                        call_log.recording_filename = recording_filename
                                        call_log.save(update_fields=['recording_filename'])
                                        
                                        # Create recording entry
                                        try:
                                            # Assuming RecordingService handles server lookup internally or requires passing
                                            recording_service.create_recording_entry(call_log, filename=recording_filename)
                                        except Exception as e:
                                            logger.error(f"Error creating recording entry DB record: {e}")
                                else:
                                    logger.error(f"Failed to start ARI recording: {response.text}")
                            except Exception as e:
                                logger.error(f"Error starting ARI recording request: {e}", exc_info=True)

                        # Notify agent that call is connected
                        self.broadcast_message(bridge_info['agent_id'], {
                            'type': 'call_connected',
                            'call': {
                                'id': call_log.id if call_log else customer_channel,
                                'call_id': str(call_log.call_id) if call_log else None,  # Convert UUID to string
                                'channel_id': customer_channel,
                                'status': 'connected',
                                'lead_id': bridge_info['lead_id']
                            }
                        })
                    else:
                        logger.error(f"Failed to create bridge: {bridge_result.get('error')}")
                        
                except Exception as e:
                    logger.error(f"Error creating bridge: {e}")

        # 3. CUSTOMER LEG - Customer being connected to agent
        elif call_type == 'customer_leg' and target_agent_id:
            # Pre-notify agent that customer leg is being connected
            self.broadcast_message(target_agent_id, {
                'type': 'call_connecting',
                'call': {
                    'id': queue_id or chan_id,
                    'number': customer_number,
                    'status': 'connecting',
                    'lead_id': lead_id
                }
            })
            
            # Phase 3.3: Track call start
            if target_agent_id:
                try:
                    self.tracker.start_call(
                        agent_id=target_agent_id,
                        call_id=queue_id or chan_id,
                        phone_number=customer_number,
                        lead_id=lead_id
                    )
                except Exception as e:
                    logger.error(f"Tracker error in stasis_start: {e}")

    def _send_call_incoming_notification(self, server, campaign_id, lead_id, phone_number, channel_id):
        """
        PHASE 1.1: Send immediate call_incoming notification to available agent
        AND originate call to agent's softphone
        """
        try:
            # Find available agent for this campaign
            agent_status = AgentStatus.objects.filter(
                Q(current_campaign_id=campaign_id) | Q(user__assigned_campaigns__id=campaign_id),
                status='available'
            ).select_related('user', 'user__profile').order_by('status_changed_at').first()

            if not agent_status:
                logger.info(f"No available agent for campaign {campaign_id}")
                return

            # Get agent extension
            agent_extension = agent_status.user.profile.extension if hasattr(agent_status.user, 'profile') else None
            if not agent_extension:
                logger.error(f"Agent {agent_status.user_id} has no extension assigned")
                return

            # Get lead info for screen pop
            lead_info = self._get_lead_info(lead_id)
            
            # Create CallLog record for this call
            from campaigns.models import Campaign
            from django.utils import timezone
            
            call_log = None
            try:
                campaign = Campaign.objects.get(id=campaign_id)
                call_log = CallLog.objects.create(
                    caller_id=phone_number or 'Unknown',
                    called_number=phone_number or '',
                    campaign=campaign,
                    asterisk_server=server,
                    call_type='inbound',
                    call_status='ringing',
                    start_time=timezone.now(),
                    channel=channel_id,
                    agent=agent_status.user,
                    lead_id=lead_id
                )
                logger.info(f"Created CallLog ID {call_log.id} for channel {channel_id}")
            except Exception as e:
                logger.error(f"Failed to create CallLog: {e}")

            # Send IMMEDIATE notification - before call is answered
            self.broadcast_message(agent_status.user_id, {
                'type': 'call_incoming',  # NEW event type for immediate notification
                'call': {
                    'id': call_log.id if call_log else channel_id,  # Use database ID
                    'call_id': str(call_log.call_id) if call_log else None,  # Convert UUID to string
                    'channel_id': channel_id,  # Asterisk channel ID
                    'number': phone_number,
                    'status': 'ringing',
                    'lead_id': lead_id,
                    'campaign_id': campaign_id
                },
                'lead': lead_info
            })

            logger.info(f"Sent call_incoming to agent {agent_status.user_id} for lead {lead_id}")

            # CRITICAL: Originate call to agent's softphone
            # Use ARI directly to send agent channel to Stasis app
            try:
                import requests
                from telephony.models import AsteriskServer
                
                # Get ARI credentials
                ari_base_url = f"http://{server.ari_host}:{server.ari_port}/ari"
                
                # Originate call to agent extension and send to Stasis app
                originate_data = {
                    'endpoint': f'PJSIP/{agent_extension}',
                    'app': 'autodialer',  # Send directly to Stasis app
                    'appArgs': 'agent_answer',  # Custom call type for agent
                    'callerId': phone_number or 'Customer',
                    'timeout': 30,
                    'variables': {
                        'CALL_TYPE': 'agent_answer',
                        'CUSTOMER_CHANNEL': channel_id,
                        'LEAD_ID': str(lead_id) if lead_id else '',
                        'CAMPAIGN_ID': str(campaign_id),
                        'AGENT_ID': str(agent_status.user_id)
                    }
                }
                
                response = requests.post(
                    f"{ari_base_url}/channels",
                    auth=(server.ari_username, server.ari_password),
                    json=originate_data,
                    timeout=10
                )
                
                if response.status_code in [200, 201]:
                    agent_channel_data = response.json()
                    agent_channel_id = agent_channel_data.get('id')
                    logger.info(f"Originated call to agent {agent_extension}, channel: {agent_channel_id}")
                    
                    # Store mapping so we can bridge when agent answers
                    if not hasattr(self, 'pending_bridges'):
                        self.pending_bridges = {}
                    
                    self.pending_bridges[agent_channel_id] = {
                        'customer_channel': channel_id,
                        'agent_id': agent_status.user_id,
                        'lead_id': lead_id,
                        'campaign_id': campaign_id
                    }
                    
                    # Update agent status to busy
                    agent_status.set_status('busy')
                else:
                    logger.error(f"Failed to originate call to agent {agent_extension}: {response.text}")
                
            except Exception as e:
                logger.error(f"Failed to originate call to agent {agent_extension}: {e}")

        except Exception as e:
            logger.error(f"Error sending call_incoming notification: {e}")

    def _handle_channel_state_change(self, server, chan_id, chan_state, call_type, 
                                      agent_id, target_agent_id, campaign_id, 
                                      lead_id, customer_number, queue_id):
        """
        Handle ChannelStateChange event - Call answered, ringing, etc.
        """
        logger.info(f"ChannelStateChange: channel={chan_id}, state={chan_state}")

        # Get call log for this channel
        cl = CallLog.objects.filter(channel=chan_id).first()

        if chan_state == 'up':  # Call answered
            # Update call log
            if cl and not cl.answer_time:
                cl.answer_time = timezone.now()
                cl.call_status = 'answered'
                cl.save(update_fields=['answer_time', 'call_status'])

            # Handle different call types
            if call_type == 'autodial':
                # Autodial answered - now assign to agent
                self._assign_autodial_answer(
                    server, chan_id, campaign_id, lead_id, 
                    None, customer_number  # hopper_id handled separately
                )

            elif call_type == 'customer_leg' and target_agent_id:
                # Customer leg answered - notify agent and mark busy
                AgentStatus.objects.filter(user_id=target_agent_id).update(
                    status='busy',
                    current_call_id=str(queue_id or (cl.id if cl else chan_id)),
                    call_start_time=timezone.now(),
                    current_campaign_id=campaign_id,
                    status_changed_at=timezone.now()
                )

                # Get full lead details for screen pop
                lead_info = self._get_lead_info(cl.lead_id if cl else lead_id)

                # Send call_connected event with full details
                self.broadcast_message(target_agent_id, {
                    'type': 'call_connected',
                    'call': {
                        'id': queue_id or (cl.id if cl else chan_id),
                        'number': cl.called_number if cl else customer_number,
                        'status': 'answered',
                        'duration': 0,
                        'lead_id': cl.lead_id if cl else lead_id,
                        'call_type': call_type
                    },
                    'lead': lead_info
                })

            elif call_type == 'agent_leg' and agent_id:
                # Agent leg answered - mark session ready
                AgentDialerSession.objects.filter(
                    agent_id=agent_id
                ).update(status='ready')

                self.broadcast_message(agent_id, {
                    'type': 'status_update',
                    'status': 'available',
                    'message': 'Ready for calls'
                })

    def _handle_channel_destroyed(self, server, chan_id, call_type, agent_id, 
                                   target_agent_id, campaign_id, lead_id, queue_id):
        """
        Handle ChannelDestroyed event - Call ended
        
        PHASE 1.3 FIX: Ensure proper cleanup of agent sessions
        """
        logger.info(f"ChannelDestroyed: channel={chan_id}, call_type={call_type}")

        # Get call log
        cl = CallLog.objects.filter(channel=chan_id).first()
        
        # DEBUG: Log what we found
        if cl:
            logger.info(f"Found CallLog ID {cl.id} for channel {chan_id}: call_type={cl.call_type}, agent_id={cl.agent_id}, end_time={cl.end_time}")
        else:
            logger.info(f"No CallLog found for channel {chan_id}")

        # Unregister from dialing set
        if cl and cl.call_type == 'outbound' and cl.campaign_id and cl.lead_id:
            from campaigns.services import HopperService
            HopperService.unregister_dialing(cl.campaign_id, cl.lead_id)

        # Update call log
        if cl and not cl.end_time:
            cl.end_time = timezone.now()
            cl.call_status = 'completed'
            if cl.answer_time:
                cl.talk_duration = int((cl.end_time - cl.answer_time).total_seconds())
            cl.save()

            # Send disposition prompt to agent
            if cl.agent_id:
                # IMPROVED: Detect customer calls even when call_type parameter is None
                # Rely primarily on CallLog data which is more reliable
                is_customer_call = (
                    # Check CallLog type first (most reliable)
                    (cl.call_type == 'outbound' and cl.campaign_id) or
                    (cl.call_type == 'inbound') or
                    # Fallback to parameter if CallLog type not set
                    call_type in ['customer_leg', 'autodial']
                )
                
                logger.info(f"Channel destroyed: call_type_param={call_type}, cl.call_type={cl.call_type}, is_customer_call={is_customer_call}")

                if is_customer_call:
                    # CRITICAL FIX: Update agent status to wrapup immediately
                    from users.models import AgentStatus
                    AgentStatus.objects.filter(user_id=cl.agent_id).update(
                        status='wrapup',
                        status_changed_at=timezone.now()
                    )
                    logger.info(f"Updated agent {cl.agent_id} status to wrapup after customer call ended")
                    
                    # Broadcast status update to UI
                    self.broadcast_message(cl.agent_id, {
                        'type': 'status_update',
                        'status': 'wrapup',
                        'message': 'Call ended - Please select disposition'
                    })
                    
                    # Update AgentDialerSession status
                    try:
                        from agents.models import AgentDialerSession
                        session = AgentDialerSession.objects.filter(agent_id=cl.agent_id).first()
                        if session:
                            session.status = 'wrapup'
                            session.customer_channel_id = None
                            session.bridge_id = None
                            session.save()
                            logger.info(f"Updated AgentDialerSession to wrapup status")
                    except Exception as e:
                        logger.error(f"Error updating AgentDialerSession: {e}")
                    
                    # Send call_ended message with force_disconnect flag
                    self.broadcast_message(cl.agent_id, {
                        'type': 'call_ended',
                        'call_id': cl.id,
                        'disposition_needed': True,
                        'force_disconnect': True,
                        'message': 'Call ended - Please select disposition'
                    })
                    
                    # Phase 1.1: Start auto-wrapup timer if campaign has it enabled
                    try:
                        from campaigns.auto_wrapup_service import get_auto_wrapup_service
                        
                        if cl.campaign_id:
                            service = get_auto_wrapup_service()
                            service.start_wrapup_timer(
                                agent_id=cl.agent_id,
                                call_log_id=cl.id,
                                campaign_id=cl.campaign_id
                            )
                            logger.info(f"Started auto-wrapup timer for agent {cl.agent_id}, call {cl.id}")
                    except Exception as e:
                        logger.error(f"Error starting auto-wrapup timer: {e}")
                    
                    
                    # CLIENT-SIDE DISCONNECT FIX:
                    # If customer hung up, we must auto-disconnect the agent channel
                    # Otherwise agent softphone stays connected to dead air or hungup bridge
                    try:
                        from agents.models import AgentDialerSession
                        from telephony.services import AsteriskService
                        import requests
                        
                        logger.info(f"Customer disconnected. Looking for agent channel to disconnect for agent_id={cl.agent_id}")
                        asterisk_service = AsteriskService(server)
                        
                        # Method 1: Try to find agent channel via AgentDialerSession
                        session = AgentDialerSession.objects.filter(agent_id=cl.agent_id).first()
                        
                        if session and session.agent_channel_id:
                            logger.info(f"Found session: {session.id}, agent_channel_id: {session.agent_channel_id}")
                            # Only hangup if it's not the agent channel itself that died
                            if session.agent_channel_id != chan_id:
                                logger.info(f"Customer hung up. Auto-disconnecting agent channel {session.agent_channel_id}")
                                try:
                                    asterisk_service.hangup_channel(session.agent_channel_id)
                                    logger.info(f"Successfully sent hangup for agent channel {session.agent_channel_id}")
                                except Exception as e:
                                    logger.debug(f"Could not hangup agent channel (may be already gone): {e}")
                            else:
                                logger.info(f"Not hanging up agent channel because destroyed channel {chan_id} IS the agent channel")
                        else:
                            # Method 2: Find agent channel by checking bridges
                            logger.info("Session not found or no agent_channel_id, checking bridges for agent channel")
                            try:
                                ari_base_url = f"http://{server.ari_host}:{server.ari_port}/ari"
                                
                                # Get all bridges
                                response = requests.get(
                                    f"{ari_base_url}/bridges",
                                    auth=(server.ari_username, server.ari_password),
                                    timeout=5
                                )
                                
                                if response.status_code == 200:
                                    bridges = response.json()
                                    for bridge in bridges:
                                        bridge_id = bridge.get('id')
                                        channels = bridge.get('channels', [])
                                        
                                        # If this bridge contains the customer channel that just died
                                        if chan_id in channels:
                                            logger.info(f"Found bridge {bridge_id} containing customer channel {chan_id}")
                                            # Find the other channel (should be agent channel)
                                            for other_channel in channels:
                                                if other_channel != chan_id:
                                                    logger.info(f"Found other channel in bridge: {other_channel}, hanging it up")
                                                    try:
                                                        asterisk_service.hangup_channel(other_channel)
                                                        logger.info(f"Successfully hung up agent channel {other_channel} from bridge")
                                                    except Exception as e:
                                                        logger.debug(f"Could not hangup channel {other_channel}: {e}")
                                            
                                            # Destroy the bridge
                                            try:
                                                asterisk_service.destroy_bridge(bridge_id)
                                                logger.info(f"Destroyed bridge {bridge_id}")
                                            except Exception as e:
                                                logger.debug(f"Could not destroy bridge {bridge_id}: {e}")
                                            break
                            except Exception as e:
                                logger.error(f"Error checking bridges for agent channel: {e}")

                    except Exception as e:
                        logger.error(f"Error in agent auto-disconnect: {e}", exc_info=True)

                else:
                    self.broadcast_message(cl.agent_id, {
                        'type': 'call_ended',
                        'call': {
                            'id': cl.id,
                            'number': cl.called_number,
                            'status': 'completed'
                        }
                    })

        # PHASE 1.3: Clean up agent session if agent leg died
        if call_type == 'agent_leg' and agent_id:
            self._cleanup_agent_session(agent_id)

        # Note: Agent status update to wrapup is now handled earlier in the function
        # (lines 600-632) for all customer calls, ensuring immediate status change

    def _cleanup_agent_session(self, agent_id):
        """
        PHASE 1.3: Force cleanup of agent session and status
        Called when agent leg is destroyed
        """
        try:
            # Update agent dialer sessions
            AgentDialerSession.objects.filter(agent_id=agent_id).update(status='offline')
            
            # Reset agent status
            AgentStatus.objects.filter(user_id=agent_id).update(
                status='available',
                current_call_id='',
                call_start_time=None,
                status_changed_at=timezone.now()
            )
            
            self.broadcast_message(agent_id, {
                'type': 'status_update',
                'status': 'available',
                'message': 'Softphone offline'
            })
            
            logger.info(f"Cleaned up session for agent {agent_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up agent session: {e}")

    def _assign_autodial_answer(self, server, chan_id, campaign_id, lead_id, 
                                 hopper_id, customer_number):
        """
        Assign answered autodial call to an available agent
        """
        logger.info(f"Assigning autodial: channel={chan_id}, campaign={campaign_id}, lead={lead_id}")

        if not campaign_id:
            logger.warning(f"Autodial call {chan_id} missing campaign_id; hanging up")
            AsteriskService(server).hangup_channel(chan_id)
            return

        # Check channel exists
        try:
            channel_info = AsteriskService(server).get_channel(chan_id)
            if not channel_info.get('success'):
                logger.warning(f"Channel {chan_id} no longer exists")
                return
        except Exception:
            logger.warning(f"Failed to verify channel {chan_id}")
            return

        # Find agent with ready session
        agent_session = AgentDialerSession.objects.filter(
            campaign_id=campaign_id,
            status='ready'
        ).select_related('agent', 'agent__agent_status').first()

        if agent_session and agent_session.agent_bridge_id:
            # Add customer to agent's bridge
            result = AsteriskService(server).add_channel_to_bridge(
                agent_session.agent_bridge_id, chan_id
            )

            if result.get('success'):
                # Create/update call log
                call_log, created = CallLog.objects.get_or_create(
                    channel=chan_id,
                    defaults={
                        'campaign_id': campaign_id,
                        'lead_id': lead_id,
                        'agent': agent_session.agent,
                        'called_number': customer_number,
                        'call_status': 'answered',
                        'call_type': 'outbound',
                        'start_time': timezone.now(),
                        'answer_time': timezone.now()
                    }
                )

                if not created:
                    call_log.agent = agent_session.agent
                    call_log.save(update_fields=['agent'])

                # Update hopper
                if hopper_id:
                    DialerHopper.objects.filter(id=hopper_id).update(
                        status='completed',
                        completed_at=timezone.now()
                    )

                # Get lead info
                lead_info = self._get_lead_info(lead_id)

                # Notify agent
                self.broadcast_message(agent_session.agent.id, {
                    'type': 'call_connected',
                    'call': {
                        'id': call_log.id,
                        'number': customer_number,
                        'status': 'answered',
                        'lead_id': lead_id
                    },
                    'lead': lead_info
                })

                # Mark agent busy
                AgentStatus.objects.filter(user=agent_session.agent).update(
                    status='busy',
                    current_call_id=str(call_log.id),
                    call_start_time=timezone.now(),
                    status_changed_at=timezone.now()
                )

                logger.info(f"Connected call to agent {agent_session.agent.username}")
                return

        # No ready agent - try softphone fallback
        self._fallback_to_softphone(server, chan_id, campaign_id, lead_id, customer_number)

    def _fallback_to_softphone(self, server, chan_id, campaign_id, lead_id, customer_number):
        """
        Fallback: Connect call by ringing agent's softphone
        """
        try:
            from agents.telephony_service import AgentTelephonyService

            # Find available agent
            available = AgentStatus.objects.filter(
                Q(current_campaign_id=campaign_id) | Q(user__assigned_campaigns__id=campaign_id),
                status='available'
            ).select_related('user').order_by('status_changed_at').first()

            if not available:
                logger.warning(f"No available agent for campaign {campaign_id}")
                # Play message or drop call
                AsteriskService(server).hangup_channel(chan_id)
                return

            telephony = AgentTelephonyService(available.user)
            phone = telephony.agent_phone

            if not phone:
                logger.warning(f"No phone for agent {available.user.username}")
                return

            # Create bridge and connect
            bridge = AsteriskService(server).create_bridge('mixing')
            if not bridge.get('success'):
                return

            bridge_id = bridge['bridge_id']

            # Add customer to bridge
            AsteriskService(server).add_channel_to_bridge(bridge_id, chan_id)

            # Originate to agent
            orig = AsteriskService(server).originate_pjsip_channel(
                endpoint=phone.extension,
                app='autodialer',
                callerid=customer_number,
                variables={
                    'CALL_TYPE': 'agent_connect',
                    'BRIDGE_ID': bridge_id,
                    'CUSTOMER_CHANNEL': chan_id,
                    'CAMPAIGN_ID': str(campaign_id),
                    'LEAD_ID': str(lead_id) if lead_id else ''
                }
            )

            if orig.get('success'):
                AsteriskService(server).add_channel_to_bridge(bridge_id, orig['channel_id'])

                # Create call log
                call_log = CallLog.objects.create(
                    channel=chan_id,
                    campaign_id=campaign_id,
                    lead_id=lead_id,
                    agent=available.user,
                    called_number=customer_number,
                    call_status='answered',
                    call_type='outbound',
                    start_time=timezone.now(),
                    answer_time=timezone.now()
                )

                # Mark agent busy
                available.status = 'busy'
                available.current_call_id = str(call_log.id)
                available.call_start_time = timezone.now()
                available.save()

                # Notify agent
                lead_info = self._get_lead_info(lead_id)
                self.broadcast_message(available.user_id, {
                    'type': 'call_connected',
                    'call': {
                        'id': call_log.id,
                        'number': customer_number,
                        'status': 'answered',
                        'lead_id': lead_id
                    },
                    'lead': lead_info
                })

                logger.info(f"Fallback: Connected to agent {available.user.username}")

        except Exception as e:
            logger.error(f"Softphone fallback error: {e}", exc_info=True)

    def _get_lead_info(self, lead_id):
        """
        Get lead information for screen pop
        """
        if not lead_id:
            return {}

        try:
            from leads.models import Lead
            lead = Lead.objects.filter(id=lead_id).first()
            if lead:
                return {
                    'id': lead.id,
                    'first_name': lead.first_name,
                    'last_name': lead.last_name,
                    'phone': lead.phone_number,
                    'email': lead.email or '',
                    'company': lead.company or '',
                    'address': lead.address or '',
                    'city': lead.city or '',
                    'state': lead.state or '',
                    'zip_code': lead.zip_code or '',
                    'status': lead.status,
                    'call_count': lead.call_count
                }
        except Exception as e:
            logger.error(f"Error getting lead info: {e}")

        return {}

    def broadcast_message(self, agent_id, payload):
        """
        Broadcast message to agent via WebSocket
        """
        if not agent_id or not self.channel_layer:
            return

        try:
            # Test JSON serialization before sending
            json.dumps(payload)
            
            async_to_sync(self.channel_layer.group_send)(
                f"agent_{agent_id}",
                {
                    'type': 'call_event',
                    'data': payload
                }
            )
            logger.debug(f"Broadcast to agent_{agent_id}: {payload.get('type')}")
        except (TypeError, ValueError) as e:
            logger.error(f"WebSocket broadcast failed - payload not JSON-serializable: {e}")
            logger.error(f"Problematic payload: {payload}")
        except Exception as e:
            logger.error(f"WebSocket broadcast failed: {e}")
