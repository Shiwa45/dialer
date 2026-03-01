"""
sarvam/action_executor.py – Phase 8.1: Action Execution
=========================================================

Executes actions requested by AI agent:
- Book appointments
- Cancel appointments
- Update CRM
- Transfer to human
- Send SMS
- Log complaints
"""

import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


class ActionExecutor:
    """
    Executes actions based on AI agent decisions.
    """
    
    def execute(self, action: Dict, call_log=None, lead=None) -> Dict:
        """
        Execute an action.
        
        Args:
            action: Action dict from conversation engine
            call_log: CallLog instance (if available)
            lead: Lead instance (if available)
        
        Returns:
            {
                'success': True,
                'result': {...},
                'message': 'Action completed'
            }
        """
        action_type = action.get('action')
        
        if not action_type:
            return {'success': False, 'error': 'No action type'}
        
        logger.info(f"Executing action: {action_type} for call {call_log.id if call_log else 'N/A'}")
        
        handlers = {
            'book_appointment': self._book_appointment,
            'cancel_appointment': self._cancel_appointment,
            'transfer_to_human': self._transfer_to_human,
            'update_crm': self._update_crm,
            'send_sms': self._send_sms,
            'log_complaint': self._log_complaint,
        }
        
        handler = handlers.get(action_type)
        if handler:
            return handler(action, call_log, lead)
        
        return {'success': False, 'error': f'Unknown action: {action_type}'}
    
    def _book_appointment(self, action: Dict, call_log, lead) -> Dict:
        """Book an appointment."""
        try:
            # Parse date and time
            date_str = action.get('date')
            time_str = action.get('time')
            
            # Convert to datetime
            appointment_datetime = self._parse_datetime(date_str, time_str)
            
            if not appointment_datetime:
                return {'success': False, 'error': 'Invalid date/time'}
            
            # Create appointment
            from django.apps import apps
            try:
                Appointment = apps.get_model('appointments', 'Appointment')
            except LookupError:
                # Model doesn't exist, log to call log instead
                logger.warning('Appointment model not found, logging to call notes')
                if call_log:
                    call_log.notes = (call_log.notes or '') + \
                        f"\nAI Agent Appointment Request: {appointment_datetime}"
                    call_log.save()
                return {
                    'success': True,
                    'message': 'Appointment logged in call notes',
                }
            
            appointment = Appointment.objects.create(
                lead=lead,
                call_log=call_log,
                scheduled_time=appointment_datetime,
                status='pending',
                created_by_ai=True,
                notes=f'Booked by AI Agent - {date_str} {time_str}',
            )
            
            logger.info(f'Appointment created: ID={appointment.id}')
            
            # Update lead status
            if lead:
                lead.status = 'callback_scheduled'
                lead.save()
            
            return {
                'success': True,
                'appointment_id': appointment.id,
                'message': f'Appointment booked for {appointment_datetime}',
            }
        
        except Exception as e:
            logger.error(f'Appointment booking error: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _cancel_appointment(self, action: Dict, call_log, lead) -> Dict:
        """Cancel existing appointment."""
        try:
            from django.apps import apps
            Appointment = apps.get_model('appointments', 'Appointment')
            
            # Find latest pending appointment for this lead
            appointment = Appointment.objects.filter(
                lead=lead,
                status='pending',
            ).order_by('-scheduled_time').first()
            
            if appointment:
                appointment.status = 'cancelled'
                appointment.cancelled_by_ai = True
                appointment.save()
                
                logger.info(f'Appointment cancelled: ID={appointment.id}')
                
                return {
                    'success': True,
                    'message': 'Appointment cancelled',
                }
            
            return {
                'success': False,
                'error': 'No pending appointment found',
            }
        
        except Exception as e:
            logger.error(f'Appointment cancellation error: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _transfer_to_human(self, action: Dict, call_log, lead) -> Dict:
        """Flag call for transfer to human agent."""
        try:
            if call_log:
                call_log.ai_requested_transfer = True
                call_log.transfer_reason = action.get('reason', 'Customer request')
                call_log.save()
            
            logger.info(f'Transfer to human requested for call {call_log.id if call_log else "N/A"}')
            
            return {
                'success': True,
                'message': 'Transfer requested',
                'transfer': True,
            }
        
        except Exception as e:
            logger.error(f'Transfer error: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _update_crm(self, action: Dict, call_log, lead) -> Dict:
        """Update lead/CRM data."""
        try:
            if not lead:
                return {'success': False, 'error': 'No lead provided'}
            
            field = action.get('field')
            value = action.get('value')
            
            if field and hasattr(lead, field):
                setattr(lead, field, value)
                lead.save()
                
                logger.info(f'Lead {lead.id} updated: {field}={value}')
                
                return {
                    'success': True,
                    'message': f'Updated {field}',
                }
            
            return {'success': False, 'error': 'Invalid field'}
        
        except Exception as e:
            logger.error(f'CRM update error: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _send_sms(self, action: Dict, call_log, lead) -> Dict:
        """Send SMS to customer."""
        try:
            if not lead or not lead.phone_number:
                return {'success': False, 'error': 'No phone number'}
            
            message = action.get('message', '')
            
            # TODO: Integrate with SMS gateway
            # For now, just log it
            logger.info(f'SMS to {lead.phone_number}: {message}')
            
            if call_log:
                call_log.notes = (call_log.notes or '') + f"\nSMS Sent: {message}"
                call_log.save()
            
            return {
                'success': True,
                'message': 'SMS queued',
            }
        
        except Exception as e:
            logger.error(f'SMS error: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _log_complaint(self, action: Dict, call_log, lead) -> Dict:
        """Log customer complaint."""
        try:
            if call_log:
                call_log.has_complaint = True
                call_log.complaint_text = action.get('complaint_text', 'Logged by AI')
                call_log.save()
            
            if lead:
                lead.status = 'complaint'
                lead.save()
            
            logger.info(f'Complaint logged for call {call_log.id if call_log else "N/A"}')
            
            return {
                'success': True,
                'message': 'Complaint logged',
            }
        
        except Exception as e:
            logger.error(f'Complaint logging error: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _parse_datetime(self, date_str: str, time_str: str) -> Optional[datetime]:
        """Parse date and time strings to datetime object."""
        try:
            # Handle relative dates
            if date_str in ['today', 'आज']:
                target_date = timezone.now().date()
            elif date_str in ['tomorrow', 'कल']:
                target_date = timezone.now().date() + timedelta(days=1)
            elif date_str in ['day_after_tomorrow', 'परसों']:
                target_date = timezone.now().date() + timedelta(days=2)
            else:
                # Try to parse actual date
                # For now, default to tomorrow
                target_date = timezone.now().date() + timedelta(days=1)
            
            # Handle time
            if 'morning' in time_str or 'सुबह' in time_str:
                target_time = datetime.strptime('10:00', '%H:%M').time()
            elif 'afternoon' in time_str or 'दोपहर' in time_str:
                target_time = datetime.strptime('14:00', '%H:%M').time()
            elif 'evening' in time_str or 'शाम' in time_str:
                target_time = datetime.strptime('17:00', '%H:%M').time()
            else:
                # Default to 10 AM
                target_time = datetime.strptime('10:00', '%H:%M').time()
            
            # Combine date and time
            return timezone.make_aware(
                datetime.combine(target_date, target_time)
            )
        
        except Exception as e:
            logger.error(f'DateTime parsing error: {e}')
            return None


# Singleton
_action_executor = None

def get_action_executor() -> ActionExecutor:
    """Get or create action executor instance."""
    global _action_executor
    if _action_executor is None:
        _action_executor = ActionExecutor()
    return _action_executor
