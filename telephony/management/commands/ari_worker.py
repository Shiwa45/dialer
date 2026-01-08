import asyncio
import json
import logging
import websockets
from django.core.management.base import BaseCommand
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.db import models
from django.db.models import Q

from telephony.models import AsteriskServer
from calls.models import CallLog
from campaigns.models import OutboundQueue
from agents.models import AgentDialerSession
from users.models import AgentStatus
from telephony.services import AsteriskService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run ARI event worker to manage agent/customer channels and bridges'

    def handle(self, *args, **options):
        server = AsteriskServer.objects.filter(is_active=True).first()
        if not server:
            self.stderr.write('No active AsteriskServer found')
            return

        ari_url = f"ws://{server.ari_host}:{server.ari_port}/ari/events?app={server.ari_application}&api_key={server.ari_username}:{server.ari_password}"
        self.stdout.write(self.style.SUCCESS(f"Connecting to ARI: {ari_url}"))
        self.channel_layer = get_channel_layer()

        async def run():
            while True:
                try:
                    async with websockets.connect(ari_url, ping_interval=10, ping_timeout=10) as ws:
                        logger.info("Connected to Asterisk ARI")
                        async for message in ws:
                            await asyncio.get_event_loop().run_in_executor(None, self.process_event, server, message)
                except websockets.ConnectionClosed as e:
                    logger.warning(f'ARI connection closed ({e.code}): {e.reason}')
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f'ARI connection error: {e}', exc_info=True)
                    await asyncio.sleep(2)

        asyncio.get_event_loop().run_until_complete(run())

    def process_event(self, server, message):
        try:
            event = json.loads(message)
        except Exception:
            return

        etype = event.get('type')
        channel = event.get('channel', {})
        chan_id = channel.get('id')
        
        # Helper to extract variables
        args = event.get('args') or []
        vars = channel.get('channelvars') or {}
        
        bridge_id = vars.get('BRIDGE_ID')
        call_type = vars.get('CALL_TYPE')
        agent_id = vars.get('AGENT_ID')  # set in originate variables
        queue_id = vars.get('QUEUE_ID')
        campaign_id = vars.get('CAMPAIGN_ID')
        customer_number = vars.get('CUSTOMER_NUMBER') or (channel.get('caller') or {}).get('number', '')
        lead_id = vars.get('LEAD_ID')
        hopper_id = vars.get('HOPPER_ID')

        def _normalize_id(val):
            if val in (None, '', 'None', 'null'):
                return None
            try:
                return int(val)
            except (TypeError, ValueError):
                return None

        campaign_id = _normalize_id(campaign_id)
        lead_id = _normalize_id(lead_id)
        hopper_id = _normalize_id(hopper_id)

        # Fallback to arguments if variables missing
        if not bridge_id or not call_type or not agent_id or not queue_id:
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

        # Support positional Stasis args: call_type, campaign_id, lead_id, hopper_id
        if args and isinstance(args, list):
            if not call_type and len(args) > 0 and isinstance(args[0], str):
                call_type = args[0]
            if not campaign_id and len(args) > 1 and isinstance(args[1], str):
                campaign_id = args[1]
            if not lead_id and len(args) > 2 and isinstance(args[2], str):
                lead_id = args[2]
            if not hopper_id and len(args) > 3 and isinstance(args[3], str):
                hopper_id = args[3]

        campaign_id = _normalize_id(campaign_id)
        lead_id = _normalize_id(lead_id)
        hopper_id = _normalize_id(hopper_id)

        if etype == 'StasisStart':
            if bridge_id and chan_id:
                AsteriskService(server).add_channel_to_bridge(bridge_id, chan_id)

            # 1. AGENT LEG CONNECTED
            if call_type == 'agent_leg' and agent_id:
                AgentDialerSession.objects.filter(agent_id=agent_id, status='connecting').update(status='ready', agent_channel_id=chan_id)
                self.broadcast_message(agent_id, {
                    'type': 'status_update',
                    'status': 'ready',
                    'message': 'Softphone Connected'
                })

            # 2. CUSTOMER CALL STARTED (Ringing) - DO NOT notify agent yet
            # For manual calls (customer_leg), we log the call but don't show to agent until answered
            if call_type == 'customer_leg':
                # Mark queue row as dialing and stamp last_tried_at
                if queue_id:
                    try:
                        OutboundQueue.objects.filter(id=queue_id).update(
                            status='dialing',
                            last_tried_at=timezone.now()
                        )
                    except Exception:
                        pass
                # Log call (but don't notify agent yet)
                CallLog.objects.get_or_create(
                    channel=chan_id,
                    defaults={
                        'agent_id': agent_id if agent_id else None,
                        'call_type': 'outbound', 
                        'call_status': 'ringing', 
                        'start_time': timezone.now(),
                        'called_number': customer_number,
                        'lead_id': lead_id
                    }
                )

            # --- Handle Autodial Answer (Hopper-based) ---
            if call_type == 'autodial':
                if not campaign_id and hopper_id:
                    try:
                        from campaigns.models import DialerHopper
                        hopper_entry = DialerHopper.objects.select_related('campaign', 'lead').filter(id=hopper_id).first()
                        if hopper_entry:
                            campaign_id = hopper_entry.campaign_id
                            lead_id = lead_id or hopper_entry.lead_id
                    except Exception:
                        pass

                if not campaign_id:
                    logger.warning("Autodial call %s missing campaign_id; hanging up", chan_id)
                    AsteriskService(server).hangup_channel(chan_id)
                    return

                call_log, _ = CallLog.objects.get_or_create(
                    channel=chan_id,
                    defaults={
                        'call_type': 'outbound',
                        'call_status': 'ringing',
                        'start_time': timezone.now(),
                        'called_number': customer_number,
                        'campaign_id': campaign_id,
                        'lead_id': lead_id,
                    }
                )

                logger.info(
                    "Autodial StasisStart channel=%s state=%s campaign=%s lead=%s",
                    chan_id,
                    channel.get('state'),
                    campaign_id,
                    lead_id,
                )

                if channel.get('state') == 'Up':
                    self._assign_autodial_answer(
                        server=server,
                        chan_id=chan_id,
                        campaign_id=campaign_id,
                        lead_id=lead_id,
                        hopper_id=hopper_id,
                        customer_number=customer_number,
                    )
                    return

                # Autodial assignment is deferred until ChannelStateChange Up.

            # ... (keep existing manual call logic) ...

        elif etype == 'ChannelStateChange':
            state = channel.get('state')
            # 3. CUSTOMER ANSWERED
            if state == 'Up':
                if call_type == 'autodial':
                    logger.info(
                        "Autodial ChannelStateChange Up channel=%s campaign=%s lead=%s",
                        chan_id,
                        campaign_id,
                        lead_id,
                    )
                if call_type == 'autodial':
                    self._assign_autodial_answer(
                        server=server,
                        chan_id=chan_id,
                        campaign_id=campaign_id,
                        lead_id=lead_id,
                        hopper_id=hopper_id,
                        customer_number=customer_number,
                    )
                    return
                cl = CallLog.objects.filter(channel=chan_id).first()
                if cl and not cl.answer_time:
                    cl.answer_time = timezone.now()
                    cl.call_status = 'answered'
                    cl.save()
                if queue_id:
                    try:
                        OutboundQueue.objects.filter(id=queue_id).update(status='answered')
                    except Exception:
                        pass
                target_agent_id = agent_id or (cl.agent_id if cl else None)
                
                # When customer leg answers, mark agent busy and set current call
                if call_type == 'customer_leg' and target_agent_id:
                    AgentStatus.objects.filter(user_id=target_agent_id).update(
                        status='busy',
                        current_call_id=str(queue_id or (cl.id if cl else chan_id)),
                        call_start_time=timezone.now(),
                        current_campaign_id=campaign_id if campaign_id else None,
                        status_changed_at=timezone.now()
                    )
                    self.broadcast_message(target_agent_id, {
                        'type': 'status_update',
                        'status': 'busy',
                        'message': 'On call'
                    })
                
                # Fetch full lead details for screen pop
                lead_info = {}
                actual_lead_id = cl.lead_id if cl else lead_id
                if actual_lead_id:
                    from leads.models import Lead
                    lead = Lead.objects.filter(id=actual_lead_id).first()
                    if lead:
                        lead_info = {
                            'id': lead.id,
                            'first_name': lead.first_name,
                            'last_name': lead.last_name,
                            'phone': lead.phone_number,
                            'email': lead.email,
                            'company': lead.company,
                            'address': lead.address,
                            'city': lead.city,
                            'state': lead.state,
                            'zip_code': lead.zip_code,
                            'status': lead.status,
                            'call_count': lead.call_count,
                            'notes': lead.notes or '',
                        }
                
                # Notify agent with full lead details (ONLY when answered)
                if target_agent_id:
                    self.broadcast_message(target_agent_id, {
                        'type': 'call_connected',  # Standardized
                        'call': {
                            'id': queue_id or (cl.id if cl else chan_id),
                            'number': cl.called_number if cl else customer_number,
                            'status': 'answered',
                            'duration': 0,
                            'lead_id': actual_lead_id,
                            'call_type': call_type
                        },
                        'lead': lead_info  # Full lead details for screen pop
                    })

        elif etype == 'ChannelDestroyed':
            # 4. CALL ENDED (Hangup)
            # Check if this channel belongs to a call log
            cl = CallLog.objects.filter(channel=chan_id).first()
            
            # Unregister from Redis (if this was an autodial call)
            if cl and cl.call_type == 'outbound' and cl.campaign_id and cl.lead_id:
                 from campaigns.services import HopperService
                 HopperService.unregister_dialing(cl.campaign_id, cl.lead_id)

            if cl and not cl.end_time:
                cl.end_time = timezone.now()
                cl.call_status = 'completed'
                if cl.answer_time:
                    cl.talk_duration = int((cl.end_time - cl.answer_time).total_seconds())
                cl.save()
                
                # Notify Agent to Open Disposition
                if cl.agent_id:
                    # Only send disposition prompt when customer leg ends
                    if call_type == 'customer_leg' or call_type == 'autodial':
                        self.broadcast_message(cl.agent_id, {
                            'type': 'call_ended',
                            'call_id': cl.id,
                            'disposition_needed': True
                        })
                    else:
                        # Agent leg ended but we still want to tell UI to stop ringing
                        self.broadcast_message(cl.agent_id, {
                            'type': 'call_ended', # Standardized
                            'call': {
                                'id': cl.id,
                                'number': cl.called_number,
                                'status': 'completed',
                                'duration': cl.total_duration or 0,
                            }
                        })
                # Tear down bridge and agent leg for autodial calls
                if call_type == 'autodial' and cl and cl.agent_id:
                    try:
                        sessions = AgentDialerSession.objects.filter(
                            agent_id=cl.agent_id,
                            campaign_id=cl.campaign_id,
                            status__in=['incall', 'ready', 'connecting']
                        ).order_by('-updated_at')
                        for session in sessions:
                            if session.agent_channel_id:
                                AsteriskService(server).hangup_channel(session.agent_channel_id)
                            if session.agent_bridge_id:
                                AsteriskService(server).destroy_bridge(session.agent_bridge_id)
                            session.status = 'offline'
                            session.ended_at = timezone.now()
                            session.save(update_fields=['status', 'ended_at'])
                    except Exception:
                        pass
                # If this was the customer leg, tear down the bridge to drop agent softphone
                if call_type == 'customer_leg' and bridge_id:
                    try:
                        AsteriskService(server).destroy_bridge(bridge_id)
                    except Exception:
                        pass
                # Update queue status on end
                if queue_id:
                    try:
                        OutboundQueue.objects.filter(id=queue_id).update(
                            status='completed',
                            last_tried_at=timezone.now()
                        )
                    except Exception:
                        pass
                # If customer leg ended, we keep the agent connected (Persistent Bridge)
                if call_type == 'customer_leg' and cl and cl.agent_id:
                    # Update Session to Ready so they can take next call
                    AgentDialerSession.objects.filter(
                        agent_id=cl.agent_id, 
                        campaign=cl.campaign
                    ).update(
                        status='ready',
                        last_state_change=timezone.now()
                    )
                # Reset agent availability when customer leg ends
                target_agent_id = agent_id or (cl.agent_id if cl else None)
                if (call_type == 'customer_leg' or call_type == 'autodial') and target_agent_id:
                    AgentStatus.objects.filter(user_id=target_agent_id).update(
                        status='wrapup',
                        current_call_id='',
                        call_start_time=None,
                        current_campaign_id=campaign_id if campaign_id else None,
                        status_changed_at=timezone.now()
                    )
                    # Notify UI about wrapup state
                    self.broadcast_message(target_agent_id, {
                        'type': 'status_update',
                        'status': 'wrapup',
                        'message': 'Wrap-up: log disposition'
                    })

            # If agent leg died, set them offline
            if call_type == 'agent_leg' and agent_id:
                AgentDialerSession.objects.filter(agent_id=agent_id).update(status='offline')
                AgentStatus.objects.filter(user_id=agent_id).update(
                    status='available',
                    current_call_id='',
                    call_start_time=None,
                    status_changed_at=timezone.now()
                )
                self.broadcast_message(agent_id, {'type': 'status_update', 'status': 'available', 'message': 'Softphone offline'})

    def broadcast_message(self, agent_id, payload):
        if not agent_id or not self.channel_layer:
            return
        try:
            async_to_sync(self.channel_layer.group_send)(
                f"agent_{agent_id}",
                {
                    'type': 'call_event', # Must match consumer method
                    'data': payload
                }
            )
        except Exception as e:
            logger.error(f"WS Broadcast failed: {e}")

    def _assign_autodial_answer(self, server, chan_id, campaign_id, lead_id, hopper_id, customer_number):
        logger.info(
            "Assign autodial start channel=%s campaign=%s lead=%s",
            chan_id,
            campaign_id,
            lead_id,
        )
        if not campaign_id:
            logger.warning("Autodial call %s missing campaign_id; hanging up", chan_id)
            AsteriskService(server).hangup_channel(chan_id)
            return

        # Ensure channel still exists before assigning.
        chan_state = AsteriskService(server).get_channel(chan_id)
        if not chan_state.get('success'):
            logger.warning("Autodial channel %s missing at assign time; skipping", chan_id)
            return

        call_log, _ = CallLog.objects.get_or_create(
            channel=chan_id,
            defaults={
                'call_type': 'outbound',
                'call_status': 'answered',
                'start_time': timezone.now(),
                'answer_time': timezone.now(),
                'called_number': customer_number,
                'campaign_id': campaign_id,
                'lead_id': lead_id,
            }
        )
        if not call_log.answer_time:
            call_log.answer_time = timezone.now()
            call_log.call_status = 'answered'
            call_log.save(update_fields=['answer_time', 'call_status'])

        # 1) WebRTC persistent session path
        agent_session = AgentDialerSession.objects.filter(
            campaign_id=campaign_id,
            status__in=['ready', 'connecting']
        ).select_related('agent', 'asterisk_server').order_by('last_state_change').first()

        if agent_session:
            from telephony.models import Phone
            webrtc_phone = Phone.objects.filter(
                user=agent_session.agent,
                is_active=True,
                webrtc_enabled=True,
                phone_type='webrtc'
            ).exists()
            if not webrtc_phone:
                agent_session = None

        if agent_session and agent_session.agent_channel_id:
            chan_info = AsteriskService(server).get_channel(agent_session.agent_channel_id)
            if not chan_info.get('success'):
                agent_session = None

        if agent_session:
            svc = AsteriskService(server)
            bridge_id = agent_session.agent_bridge_id
            if not bridge_id:
                b = svc.create_bridge('mixing')
                if b.get('success'):
                    bridge_id = b['bridge_id']
                    agent_session.agent_bridge_id = bridge_id
            if bridge_id:
                svc.add_channel_to_bridge(bridge_id, chan_id)

            agent_session.status = 'incall'
            agent_session.last_state_change = timezone.now()
            agent_session.save()

            AgentStatus.objects.filter(user_id=agent_session.agent.id).update(
                status='busy',
                current_call_id=str(call_log.id),
                call_start_time=timezone.now(),
                current_campaign_id=campaign_id,
                status_changed_at=timezone.now()
            )

            lead_info = {}
            if lead_id:
                from leads.models import Lead
                lead = Lead.objects.filter(id=lead_id).first()
                if lead:
                    lead_info = {
                        'id': lead.id,
                        'first_name': lead.first_name,
                        'last_name': lead.last_name,
                        'phone': lead.phone_number,
                        'company': lead.company,
                        'email': lead.email,
                        'status': lead.status
                    }

            self.broadcast_message(agent_session.agent.id, {
                'type': 'call_connected',
                'call': {
                    'id': call_log.id,
                    'number': call_log.called_number,
                    'status': 'answered',
                    'lead_id': lead_id
                },
                'lead': lead_info
            })

            if hopper_id:
                from campaigns.models import DialerHopper
                hopper = DialerHopper.objects.filter(id=hopper_id).first()
                if hopper:
                    hopper.mark_completed(call_log=call_log)

            call_log.agent_id = agent_session.agent.id
            call_log.save(update_fields=['agent_id'])
            return

        # 2) Softphone fallback: ring agent now
        fallback_connected = False
        try:
            from agents.telephony_service import AgentTelephonyService
            available = AgentStatus.objects.filter(
                Q(current_campaign_id=campaign_id) | Q(user__assigned_campaigns__id=campaign_id),
                status='available',
            ).select_related('user').order_by('status_changed_at').first()
            if available:
                logger.info("Assign autodial using agent=%s", available.user.username)
                telephony = AgentTelephonyService(available.user)
                phone = telephony.agent_phone
                if not phone:
                    logger.warning("No phone assigned for available agent %s", available.user.username)
                elif not telephony.is_extension_registered():
                    logger.warning(
                        "Agent %s extension %s is not registered; skipping fallback",
                        available.user.username,
                        phone.extension,
                    )
                else:
                    svc = AsteriskService(server)
                    b = svc.create_bridge('mixing')
                    if b.get('success'):
                        bridge_id = b['bridge_id']
                        svc.add_channel_to_bridge(bridge_id, chan_id)
                        logger.info("Ringing agent extension %s for channel %s", phone.extension, chan_id)
                        ares = svc.originate_pjsip_channel(
                            endpoint=phone.extension,
                            app='autodialer',
                            callerid=f"Agent {phone.extension}",
                            variables={
                                'CALL_TYPE': 'agent_leg',
                                'BRIDGE_ID': bridge_id,
                                'CAMPAIGN_ID': str(campaign_id),
                                'AGENT_ID': str(available.user_id),
                                'CUSTOMER_NUMBER': customer_number,
                                'LEAD_ID': lead_id or ''
                            }
                        )
                        if ares.get('success'):
                            # Ensure agent leg is added to bridge even if Stasis args are missing.
                            svc.wait_for_channel_up(ares['channel_id'], timeout_sec=15, interval=0.5)
                            svc.add_channel_to_bridge(bridge_id, ares['channel_id'])
                            AgentDialerSession.objects.filter(
                                agent_id=available.user_id,
                                campaign_id=campaign_id
                            ).delete()
                            AgentDialerSession.objects.create(
                                agent_id=available.user_id,
                                campaign_id=campaign_id,
                                agent_channel_id=ares['channel_id'],
                                agent_bridge_id=bridge_id,
                                asterisk_server=server,
                                status='incall',
                                last_state_change=timezone.now()
                            )
                            AgentStatus.objects.filter(pk=available.pk).update(
                                status='busy',
                                current_call_id=str(call_log.id),
                                current_campaign_id=campaign_id,
                                call_start_time=timezone.now(),
                                status_changed_at=timezone.now()
                            )
                            call_log.agent_id = available.user_id
                            call_log.save(update_fields=['agent_id'])
                            fallback_connected = True
                        else:
                            logger.warning(
                                "Agent leg originate failed for %s: %s",
                                phone.extension,
                                ares.get('error')
                            )
            else:
                logger.warning("No available agents for campaign %s at assign time", campaign_id)
        except Exception as e:
            logger.error(f"On-the-fly agent leg failed: {e}", exc_info=True)

        if not fallback_connected:
            logger.warning(f"No agent available for {chan_id} - DROPPING CALL")
            svc = AsteriskService(server)
            svc.hangup_channel(chan_id)
            from campaigns.services import HopperService
            if campaign_id and lead_id:
                HopperService.unregister_dialing(campaign_id, lead_id)
            if hopper_id:
                from campaigns.models import DialerHopper
                hopper = DialerHopper.objects.filter(id=hopper_id).first()
                if hopper:
                    hopper.mark_dropped()
            if campaign_id:
                from campaigns.models import CampaignStats
                today = timezone.now().date()
                stats, _ = CampaignStats.objects.get_or_create(
                    campaign_id=campaign_id,
                    date=today
                )
                stats.drop_count += 1
                stats.save(update_fields=['drop_count'])
