
import logging
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)
User = get_user_model()

class DispositionService:
    """Enhanced disposition service with real-time updates"""
    
    def __init__(self):
        self.channel_layer = get_channel_layer()
    
    def submit_disposition(self, agent, call_id, disposition_id, notes='', **kwargs):
        """
        Submit call disposition with comprehensive validation and updates
        
        Args:
            agent: User object of the agent
            call_id: ID of the call log
            disposition_id: ID of the disposition
            notes: Agent notes (optional)
            **kwargs: Additional data (schedule_time, etc.)
            
        Returns:
            dict: Success status and data
        """
        try:
            with transaction.atomic():
                # Validate inputs
                validation_result = self._validate_disposition_inputs(
                    agent, call_id, disposition_id
                )
                if not validation_result['success']:
                    return validation_result
                
                call_log = validation_result['call_log']
                disposition = validation_result['disposition']
                
                # Check if call is already dispositioned
                if call_log.disposition:
                    logger.warning(f"Call {call_id} already dispositioned")
                    return {
                        'success': False,
                        'error': 'Call already dispositioned'
                    }
                
                # Update call log
                self._update_call_log(call_log, disposition, notes, kwargs)
                
                # Update lead status
                lead_update_result = self._update_lead_status(
                    call_log, disposition, kwargs
                )
                
                # Update agent status
                self._update_agent_status(agent, disposition)
                
                # Handle callbacks if needed
                if disposition.schedule_callback:
                    callback_result = self._schedule_callback(
                        call_log, disposition, kwargs
                    )
                
                # Send real-time notifications
                self._send_realtime_notifications(agent, call_log, disposition)
                
                logger.info(f"Disposition '{disposition.name}' submitted for call {call_id}")
                
                return {
                    'success': True,
                    'disposition': disposition.name,
                    'call_id': call_id,
                    'agent_status': 'available' if disposition.auto_available else 'wrapup',
                    'lead_updated': lead_update_result.get('updated', False),
                    'callback_scheduled': disposition.schedule_callback
                }
                
        except Exception as e:
            logger.error(f"Error submitting disposition: {e}", exc_info=True)
            return {
                'success': False,
                'error': f'Failed to submit disposition: {str(e)}'
            }
    
    def _validate_disposition_inputs(self, agent, call_id, disposition_id):
        """Validate disposition inputs"""
        from telephony.models import CallLog
        from campaigns.models import Disposition
        
        try:
            # Get call log
            call_log = CallLog.objects.select_for_update().filter(
                id=call_id,
                agent=agent
            ).first()
            
            if not call_log:
                return {
                    'success': False,
                    'error': 'Call not found or not assigned to this agent'
                }
            
            # Get disposition
            disposition = Disposition.objects.filter(id=disposition_id).first()
            if not disposition:
                return {
                    'success': False,
                    'error': 'Invalid disposition selected'
                }
            
            # Validate disposition is allowed for this campaign
            if call_log.campaign and disposition.campaigns.exists():
                if not disposition.campaigns.filter(id=call_log.campaign.id).exists():
                    return {
                        'success': False,
                        'error': 'Disposition not allowed for this campaign'
                    }
            
            return {
                'success': True,
                'call_log': call_log,
                'disposition': disposition
            }
            
        except Exception as e:
            logger.error(f"Error validating disposition inputs: {e}")
            return {
                'success': False,
                'error': 'Validation failed'
            }
    
    def _update_call_log(self, call_log, disposition, notes, extra_data):
        """Update call log with disposition"""
        call_log.disposition = disposition
        call_log.disposition_time = timezone.now()
        call_log.agent_notes = notes
        call_log.call_status = 'dispositioned'
        
        # Add extra data to call log if provided
        if 'call_back_date' in extra_data:
            call_log.scheduled_callback = extra_data['call_back_date']
            
        call_log.save()
        
        logger.debug(f"Updated call log {call_log.id} with disposition {disposition.name}")
    
    def _update_lead_status(self, call_log, disposition, extra_data):
        """Update lead status based on disposition"""
        if not call_log.lead_id:
            return {'updated': False}
            
        try:
            from leads.models import Lead
            
            lead = Lead.objects.filter(id=call_log.lead_id).first()
            if not lead:
                return {'updated': False}
            
            # Update lead status based on disposition
            if disposition.is_sale:
                lead.status = 'sale'
            elif disposition.schedule_callback:
                lead.status = 'callback'
                if 'call_back_date' in extra_data:
                    lead.callback_date = extra_data['call_back_date']
            elif disposition.is_dnc:
                lead.status = 'dnc'
            else:
                lead.status = disposition.category
            
            # Update contact information
            lead.last_contact_date = timezone.now()
            lead.last_disposition = disposition.name
            
            # Increment call count
            lead.call_count += 1
            
            # Add notes if provided
            if extra_data.get('lead_notes'):
                current_notes = lead.notes or ''
                timestamp = timezone.now().strftime('%Y-%m-%d %H:%M')
                new_note = f"[{timestamp}] {extra_data['lead_notes']}"
                lead.notes = f"{current_notes}\n{new_note}".strip()
            
            lead.save()
            
            logger.debug(f"Updated lead {lead.id} status to {lead.status}")
            return {'updated': True, 'new_status': lead.status}
            
        except Exception as e:
            logger.error(f"Error updating lead status: {e}")
            return {'updated': False, 'error': str(e)}
    
    def _update_agent_status(self, agent, disposition):
        """Update agent status after disposition"""
        from users.models import AgentStatus
        from agents.models import AgentDialerSession
        
        try:
            # Update AgentStatus
            agent_status, created = AgentStatus.objects.get_or_create(
                user=agent,
                defaults={'status': 'available'}
            )
            
            if disposition.auto_available:
                agent_status.status = 'available'
            else:
                agent_status.status = 'wrapup'
                
            agent_status.last_disposition_time = timezone.now()
            agent_status.save()
            
            # Update AgentDialerSession if exists
            session = AgentDialerSession.objects.filter(
                agent=agent,
                status__in=['on_call', 'wrapup']
            ).first()
            
            if session:
                if disposition.auto_available:
                    session.status = 'ready'
                else:
                    session.status = 'wrapup'
                session.last_disposition_time = timezone.now()
                session.save()
                
            logger.debug(f"Updated agent {agent.username} status to {agent_status.status}")
            
        except Exception as e:
            logger.error(f"Error updating agent status: {e}")
    
    def _schedule_callback(self, call_log, disposition, extra_data):
        """Schedule callback task"""
        try:
            from agents.models import AgentCallbackTask
            
            callback_time = extra_data.get('call_back_date')
            if not callback_time:
                # Default to tomorrow at 9 AM if no time specified
                from datetime import datetime, timedelta
                callback_time = timezone.now() + timedelta(days=1)
                callback_time = callback_time.replace(hour=9, minute=0, second=0)
            
            callback_task = AgentCallbackTask.objects.create(
                agent=call_log.agent,
                lead_id=call_log.lead_id,
                campaign=call_log.campaign,
                scheduled_time=callback_time,
                task_type='callback',
                status='scheduled',
                notes=f"Callback scheduled from disposition: {disposition.name}",
                priority=2 if disposition.is_sale else 1
            )
            
            logger.info(f"Scheduled callback task {callback_task.id} for {callback_time}")
            return {'success': True, 'task_id': callback_task.id}
            
        except Exception as e:
            logger.error(f"Error scheduling callback: {e}")
            return {'success': False, 'error': str(e)}
    
    def _send_realtime_notifications(self, agent, call_log, disposition):
        """Send real-time notifications to agent and supervisors"""
        try:
            # Notify agent
            async_to_sync(self.channel_layer.group_send)(
                f"agent_{agent.id}",
                {
                    'type': 'status_update',
                    'data': {
                        'type': 'disposition_completed',
                        'call_id': call_log.id,
                        'disposition': disposition.name,
                        'new_status': 'available' if disposition.auto_available else 'wrapup',
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
            
            # Notify supervisors
            async_to_sync(self.channel_layer.group_send)(
                'supervisors',
                {
                    'type': 'call_statistics_update',
                    'data': {
                        'type': 'disposition_submitted',
                        'agent_name': agent.get_full_name() or agent.username,
                        'disposition': disposition.name,
                        'campaign': call_log.campaign.name if call_log.campaign else 'Unknown',
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error sending real-time notifications: {e}")
