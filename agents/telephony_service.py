# agents/telephony_service.py

import logging
import requests
import json
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone
from django.conf import settings
from telephony.models import AsteriskServer, Phone
from telephony.services import AsteriskService, WebRTCService
from campaigns.models import Campaign
from leads.models import Lead
from calls.models import CallLog
from users.models import AgentStatus
from .models import AgentQueue, AgentWebRTCSession, AgentDialerSession

logger = logging.getLogger(__name__)

class AgentTelephonyService:
    """
    Service class for agent telephony operations
    Integrates with your existing telephony system
    """
    
    def __init__(self, agent):
        self.agent = agent
        self.agent_phone = self.get_agent_phone()
        self.asterisk_server = self.get_asterisk_server()
        
    def get_agent_phone(self):
        """Get agent's assigned phone/extension"""
        return Phone.objects.filter(user=self.agent, is_active=True).first()
    
    def get_asterisk_server(self):
        """Get active Asterisk server"""
        return AsteriskServer.objects.filter(is_active=True).first()
    
    def get_webrtc_config(self):
        """
        Get WebRTC configuration for agent's softphone
        """
        if not self.agent_phone:
            return {
                'success': False,
                'error': 'No phone assigned to agent'
            }
        
        webrtc_service = WebRTCService(self.agent_phone)
        config = webrtc_service.get_webrtc_config()
        
        # Add agent-specific settings
        if config.get('success'):
            config.update({
                'agent_id': self.agent.id,
                'extension': self.agent_phone.extension,
                'display_name': f"{self.agent.get_full_name()} ({self.agent_phone.extension})",
                'auto_answer': self.get_agent_auto_answer_setting(),
            })
        
        return config
    
    def get_agent_auto_answer_setting(self):
        """Check if agent has auto-answer enabled"""
        agent_queue = AgentQueue.objects.filter(
            agent=self.agent,
            is_active=True
        ).first()
        return agent_queue.auto_answer if agent_queue else False
    
    def register_webrtc_phone(self):
        """
        Register agent's WebRTC phone session
        """
        if not self.agent_phone or not self.asterisk_server:
            return {
                'success': False,
                'error': 'Phone or server not available'
            }
        
        try:
            # Create or update WebRTC session
            session, created = AgentWebRTCSession.objects.get_or_create(
                agent=self.agent,
                defaults={
                    'sip_extension': self.agent_phone.extension,
                    'asterisk_server': self.asterisk_server,
                    'status': 'connecting'
                }
            )
            
            # Use telephony service to register
            webrtc_service = WebRTCService(self.agent_phone)
            result = webrtc_service.register_webrtc_phone()
            
            if result.get('success'):
                session.status = 'connected'
                session.connect_time = timezone.now()
                session.save()
                
                return {
                    'success': True,
                    'session_id': str(session.session_id),
                    'extension': self.agent_phone.extension,
                    'message': 'WebRTC phone registered successfully'
                }
            else:
                session.status = 'failed'
                session.save()
                return result
                
        except Exception as e:
            logger.error(f"Error registering WebRTC phone: {str(e)}")
            return {
                'success': False,
                'error': f'Registration failed: {str(e)}'
            }
    
    def is_extension_registered(self):
        """
        Check if the agent's assigned extension is currently registered/reachable.
        """
        if not self.agent_phone or not self.asterisk_server:
            return False
        try:
            service = AsteriskService(self.asterisk_server)
            status = service.get_endpoint_status(self.agent_phone.extension)
            return status.get('registered', False)
        except Exception:
            return False
    
    def make_call(self, phone_number, campaign_id=None, lead_id=None, force_manual=False):
        """
        Initiate outbound call using campaign dial method
        """
        if not self.agent_phone or not self.asterisk_server:
            return {
                'success': False,
                'error': 'Phone or server not configured'
            }
        call_log = None
        # Check agent availability
        agent_status = getattr(self.agent, 'agent_status', None)
        if not agent_status or agent_status.status != 'available':
            return {
                'success': False,
                'error': 'Agent not available for calls'
            }
        
        if not self.is_extension_registered():
            return {
                'success': False,
                'error': f'Extension {self.agent_phone.extension} is not registered. Please register your softphone.'
            }
        
        try:
            # Normalize identifiers that may arrive as strings like "" or "null"
            def _to_int(val):
                if val in (None, '', 'null', 'None'):
                    return None
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return None

            # Get campaign and determine dial method
            campaign = None
            cid = _to_int(campaign_id)
            if cid is not None:
                campaign = Campaign.objects.filter(id=cid).first()
            
            # Get lead if provided
            lead = None
            lid = _to_int(lead_id)
            if lid is not None:
                lead = Lead.objects.filter(id=lid).first()
            
            # Create call log entry
            call_log = CallLog.objects.create(
                call_type='outbound',
                call_status='initiated',
                called_number=phone_number,
                agent=self.agent,
                lead=lead,
                campaign=campaign,
                start_time=timezone.now(),
                channel=f"SIP/{self.agent_phone.extension}"
            )
            
            # Use Asterisk service to originate call
            asterisk_service = AsteriskService(self.asterisk_server)
            
            # Determine dial method
            dial_method = 'manual'
            if campaign:
                dial_method = campaign.dial_method
            if force_manual:
                dial_method = 'manual'
            
            if dial_method in ['manual', 'preview']:
                # Manual/preview: prefer dialplan routing via prefix if configured
                ctx = 'from-campaign'
                num = phone_number
                if campaign and campaign.dial_prefix:
                    num = f"{campaign.dial_prefix}{phone_number}"
                    ctx = 'from-campaign'
                else:
                    # fallback to existing agents context
                    ctx = 'agents'
                result = asterisk_service.originate_call(
                    extension=self.agent_phone.extension,
                    phone_number=num,
                    campaign=campaign,
                    context=ctx
                )
            elif dial_method in ['progressive', 'predictive', 'auto']:
                # Use dialer queue system
                result = self.queue_call_for_dialing(
                    phone_number=phone_number,
                    campaign=campaign,
                    lead=lead,
                    call_log=call_log
                )
            else:
                result = {
                    'success': False,
                    'error': f'Dial method {dial_method} not implemented'
                }
            
            if result.get('success'):
                # Update call log with channel info
                if 'channel_id' in result:
                    call_log.channel = result['channel_id']
                    call_log.uniqueid = result['channel_id']
                    call_log.save(update_fields=['channel', 'uniqueid'])
                
                # Update agent status
                agent_status.set_status('busy')
                agent_status.current_call_id = str(call_log.id)
                agent_status.call_start_time = timezone.now()
                agent_status.save()

                # Broadcast call start to agent websocket
                self._broadcast_call_event({
                    'type': 'call_started',
                    'call': {
                        'id': call_log.id,
                        'number': phone_number,
                        'status': call_log.call_status,
                        'duration': 0,
                    }
                })
                
                return {
                    'success': True,
                    'call_id': call_log.id,
                    'channel_id': result.get('channel_id'),
                    'message': f'Call initiated to {phone_number}'
                }
            else:
                # Update call log with failure
                call_log.call_status = 'failed'
                call_log.end_time = timezone.now()
                call_log.save()
                failure = dict(result)
                failure.setdefault('success', False)
                failure['call_id'] = call_log.id
                self._broadcast_call_event({
                    'type': 'call_ended',
                    'call_id': call_log.id,
                })
                return failure
                
        except Exception as e:
            logger.error(f"Error making call: {str(e)}")
            if call_log:
                call_log.call_status = 'failed'
                call_log.end_time = timezone.now()
                call_log.save()
                self._broadcast_call_event({
                    'type': 'call_ended',
                    'call_id': call_log.id,
                })
                return {
                    'success': False,
                    'error': f'Call failed: {str(e)}',
                    'call_id': call_log.id
                }
            return {
                'success': False,
                'error': f'Call failed: {str(e)}'
            }

    def _broadcast_call_event(self, payload):
        try:
            layer = get_channel_layer()
            if not layer:
                return
            async_to_sync(layer.group_send)(
                f"agent_{self.agent.id}",
                {
                    'type': 'call.event',
                    'data': payload
                }
            )
        except Exception:
            # Best-effort; don't break call flow
            logger.debug('Call event broadcast failed', exc_info=True)

    # =====================
    # Autodial Session (Phase 1)
    # =====================
    def login_campaign(self, campaign_id):
        """Create persistent agent leg and bridge for the selected campaign."""
        if not self.agent_phone or not self.asterisk_server:
            return {'success': False, 'error': 'Phone or Asterisk server not configured'}

        try:
            campaign = Campaign.objects.filter(id=campaign_id).first()
            if not campaign:
                return {'success': False, 'error': 'Campaign not found'}

            service = AsteriskService(self.asterisk_server)
            # Create bridge for the agent
            b = service.create_bridge('mixing')
            if not b.get('success'):
                return b
            bridge_id = b['bridge_id']

            # Originate agent leg
            o = service.originate_pjsip_channel(
                endpoint=self.agent_phone.extension,
                app='autodialer',
                callerid=f"Agent {self.agent_phone.extension}",
                variables={'CALL_TYPE': 'agent_leg', 'BRIDGE_ID': bridge_id}
            )
            if not o.get('success'):
                # cleanup bridge
                return o
            agent_channel_id = o['channel_id']

            # Try to add agent channel to bridge (may fail until answered)
            _ = service.add_channel_to_bridge(bridge_id, agent_channel_id)

            session = AgentDialerSession.objects.create(
                agent=self.agent,
                campaign=campaign,
                asterisk_server=self.asterisk_server,
                agent_extension=self.agent_phone.extension,
                agent_channel_id=agent_channel_id,
                agent_bridge_id=bridge_id,
                status='connecting'
            )

            # Mark agent as available, connection expected to complete when answered
            agent_status = getattr(self.agent, 'agent_status', None)
            if agent_status:
                agent_status.set_status('available')

            return {
                'success': True,
                'session_id': session.id,
                'bridge_id': bridge_id,
                'agent_channel_id': agent_channel_id,
                'message': 'Agent session created. Answer your phone to complete connection.'
            }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def logout_session(self):
        try:
            session = AgentDialerSession.objects.filter(agent=self.agent, status__in=['connecting', 'ready']).first()
            if not session:
                return {'success': True, 'message': 'No active session'}
            service = AsteriskService(session.asterisk_server)
            if session.agent_channel_id:
                service.hangup_channel(session.agent_channel_id)
            session.status = 'offline'
            session.ended_at = timezone.now()
            session.save()
            agent_status = getattr(self.agent, 'agent_status', None)
            if agent_status:
                agent_status.set_status('offline')
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def push_call(self, phone_number):
        """Manually push a number to the agent bridge (POC)."""
        session = AgentDialerSession.objects.filter(agent=self.agent, status__in=['connecting', 'ready']).first()
        if not session:
            return {'success': False, 'error': 'No active session'}
        service = AsteriskService(session.asterisk_server)
        # Originate via Local into dialplan (from-campaign); prefix selects carrier
        number_to_dial = f"{session.campaign.dial_prefix}{phone_number}" if session.campaign.dial_prefix else phone_number
        o = service.originate_local_channel(
            number=number_to_dial,
            context='from-campaign',
            app='autodialer',
            callerid=f"OUT {phone_number}",
            variables={'CALL_TYPE': 'customer_leg', 'BRIDGE_ID': session.agent_bridge_id, 'CAMPAIGN_ID': str(session.campaign.id)}
        )
        if not o.get('success'):
            return o
        # Attempt to add to bridge (will succeed when answered)
        _ = service.add_channel_to_bridge(session.agent_bridge_id, o['channel_id'])
        return {'success': True, 'customer_channel_id': o['channel_id']}
    
    def queue_call_for_dialing(self, phone_number, campaign, lead, call_log):
        """
        Queue call for progressive/predictive dialing
        """
        # This would integrate with your dialing algorithm
        # For now, fall back to direct origination
        asterisk_service = AsteriskService(self.asterisk_server)
        return asterisk_service.originate_call(
            extension=self.agent_phone.extension,
            phone_number=phone_number,
            campaign=campaign,
            context='agents'
        )
    
    def answer_call(self, call_id):
        """
        Answer incoming call
        """
        try:
            call_log = CallLog.objects.filter(id=call_id, agent=self.agent).first()
            if not call_log:
                return {
                    'success': False,
                    'error': 'Call not found'
                }
            
            # Update call status
            call_log.call_status = 'answered'
            call_log.answer_time = timezone.now()
            call_log.save()
            
            # Notify agent via websocket about call end
            self._broadcast_call_event({
                'type': 'call_ended',
                'call_id': call_id,
            })
            
            # Update agent status
            agent_status = getattr(self.agent, 'agent_status', None)
            if agent_status:
                agent_status.set_status('busy')
                agent_status.current_call_id = str(call_id)
                agent_status.call_start_time = timezone.now()
                agent_status.save()
            
            return {
                'success': True,
                'call_id': call_id,
                'message': 'Call answered successfully'
            }
            
        except Exception as e:
            logger.error(f"Error answering call: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to answer call: {str(e)}'
            }
    
    def hangup_call(self, call_id, reason='agent_hangup'):
        """
        Hangup call and update records
        """
        try:
            call_log = CallLog.objects.filter(id=call_id, agent=self.agent).first()
            if not call_log:
                return {
                    'success': False,
                    'error': 'Call not found'
                }
            
            # Use Asterisk service to hangup if channel is active
            if call_log.uniqueid and self.asterisk_server:
                asterisk_service = AsteriskService(self.asterisk_server)
                # TODO: Implement channel hangup via ARI
            
            # Update call log
            call_log.call_status = 'completed'
            call_log.end_time = timezone.now()
            call_log.hangup_cause_text = reason
            
            # Calculate durations
            if call_log.answer_time and call_log.end_time:
                call_log.talk_duration = int(
                    (call_log.end_time - call_log.answer_time).total_seconds()
                )
            
            if call_log.start_time and call_log.end_time:
                call_log.total_duration = int(
                    (call_log.end_time - call_log.start_time).total_seconds()
                )
            
            call_log.save()
            
            # Update agent status back to available
            agent_status = getattr(self.agent, 'agent_status', None)
            if agent_status:
                agent_status.set_status('available')
                agent_status.current_call_id = ''
                agent_status.call_start_time = None
                agent_status.save()
            
            return {
                'success': True,
                'call_id': call_id,
                'duration': call_log.total_duration,
                'message': 'Call ended successfully'
            }
            
        except Exception as e:
            logger.error(f"Error hanging up call: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to hangup call: {str(e)}'
            }
    
    def transfer_call(self, call_id, transfer_to, transfer_type='warm'):
        """
        Transfer call to another extension/number
        """
        try:
            call_log = CallLog.objects.filter(id=call_id, agent=self.agent).first()
            if not call_log:
                return {
                    'success': False,
                    'error': 'Call not found'
                }
            
            # Use Asterisk service for transfer
            if self.asterisk_server and call_log.uniqueid:
                asterisk_service = AsteriskService(self.asterisk_server)
                # TODO: Implement call transfer via ARI
                
                # Create transfer record
                from calls.models import Transfer
                transfer = Transfer.objects.create(
                    call_log=call_log,
                    from_agent=self.agent,
                    transfer_type=transfer_type,
                    to_number=transfer_to,
                    transfer_time=timezone.now()
                )
                
                return {
                    'success': True,
                    'transfer_id': transfer.id,
                    'message': f'{transfer_type.title()} transfer initiated'
                }
            
            return {
                'success': False,
                'error': 'Transfer service not available'
            }
            
        except Exception as e:
            logger.error(f"Error transferring call: {str(e)}")
            return {
                'success': False,
                'error': f'Transfer failed: {str(e)}'
            }
    
    def hold_call(self, call_id):
        """
        Put call on hold
        """
        try:
            call_log = CallLog.objects.filter(id=call_id, agent=self.agent).first()
            if not call_log:
                return {
                    'success': False,
                    'error': 'Call not found'
                }
            
            # TODO: Implement hold via Asterisk ARI
            
            return {
                'success': True,
                'call_id': call_id,
                'message': 'Call placed on hold'
            }
            
        except Exception as e:
            logger.error(f"Error holding call: {str(e)}")
            return {
                'success': False,
                'error': f'Hold failed: {str(e)}'
            }
    
    def get_agent_call_status(self):
        """
        Get agent's current call status and active calls
        """
        try:
            active_statuses = {'initiated', 'ringing', 'answered', 'in-progress', 'talking', 'active'}
            # Primary: active call with no end_time and an active status
            current_call = CallLog.objects.filter(
                agent=self.agent,
                end_time__isnull=True,
                call_status__in=active_statuses
            ).order_by('-start_time').first()

            # Fallback: most recent call in the last 5 minutes, even if end_time is set,
            # so the UI can still show it for disposition.
            if not current_call:
                cutoff = timezone.now() - timezone.timedelta(minutes=5)
                current_call = CallLog.objects.filter(
                    agent=self.agent,
                    start_time__gte=cutoff
                ).order_by('-start_time').first()

            # Get agent status
            agent_status = getattr(self.agent, 'agent_status', None)

            call_payload = None
            if current_call:
                # Derive a display status from timestamps to avoid stale call_status values.
                status = (current_call.call_status or '').lower()
                if current_call.end_time:
                    status = status or 'completed'
                elif current_call.answer_time:
                    status = status or 'in-progress'
                elif not status:
                    status = 'initiated'

                call_payload = {
                    'id': current_call.id,
                    'number': current_call.called_number,
                    'status': status,
                    'duration': self.calculate_call_duration(current_call),
                    'lead_id': current_call.lead.id if current_call.lead else None
                }

            return {
                'success': True,
                'agent_status': agent_status.status if agent_status else 'offline',
                'phone_registered': self.is_extension_registered(),
                'current_call': call_payload,
                'extension': self.agent_phone.extension if self.agent_phone else None
            }

        except Exception as e:
            logger.error(f"Error getting call status: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to get status: {str(e)}'
            }
    
    def calculate_call_duration(self, call_log):
        """Calculate current call duration"""
        if not call_log.start_time:
            return 0
        
        end_time = call_log.end_time or timezone.now()
        return int((end_time - call_log.start_time).total_seconds())
    
    def get_next_lead(self, campaign_id):
        """
        Get next lead for agent from campaign lead hopper
        """
        try:
            campaign = Campaign.objects.filter(id=campaign_id).first()
            if not campaign:
                return {
                    'success': False,
                    'error': 'Campaign not found'
                }
            
            # Find next available lead based on campaign dial method
            if campaign.dial_method == 'preview':
                # Preview dial - get next lead for agent to review
                next_lead = Lead.objects.filter(
                    lead_list__campaigns=campaign,
                    status='new',
                    call_attempts__lt=campaign.max_attempts
                ).order_by(campaign.lead_order).first()
            
            elif campaign.dial_method in ['progressive', 'predictive']:
                # System will manage lead selection
                next_lead = self.get_system_selected_lead(campaign)
            
            else:
                # Manual dial - no automatic lead selection
                return {
                    'success': False,
                    'error': 'Manual dial mode - no automatic lead selection'
                }
            
            if next_lead:
                return {
                    'success': True,
                    'lead': {
                        'id': next_lead.id,
                        'first_name': next_lead.first_name,
                        'last_name': next_lead.last_name,
                        'phone_number': next_lead.phone_number,
                        'email': next_lead.email,
                        'company': next_lead.company,
                        'status': next_lead.status,
                        'comments': next_lead.comments,
                        'last_contact_date': next_lead.last_contact_date.isoformat() if next_lead.last_contact_date else None
                    }
                }
            else:
                return {
                    'success': False,
                    'error': 'No more leads available in campaign'
                }
                
        except Exception as e:
            logger.error(f"Error getting next lead: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to get lead: {str(e)}'
            }
    
    def get_system_selected_lead(self, campaign):
        """
        Get next lead selected by dialing algorithm
        """
        # This would integrate with your predictive/progressive dialing algorithm
        # For now, return next available lead
        return Lead.objects.filter(
            lead_list__campaigns=campaign,
            status='new',
            call_attempts__lt=campaign.max_attempts
        ).order_by(campaign.lead_order).first()
