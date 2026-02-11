"""
Auto Wrapup Timer Service - Phase 1.1

This service manages automatic call disposition after a configured timeout period.
When an agent enters wrapup status, a timer starts. If the agent doesn't manually
dispose the call before the timeout, the system automatically applies a default disposition.

Features:
- Campaign-specific wrapup timeouts
- Configurable default dispositions
- WebSocket notifications to agent
- Graceful handling of manual dispositions
- Logging for audit trail
"""

import logging
from datetime import timedelta
from typing import Optional, Dict
from django.utils import timezone
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


class AutoWrapupService:
    """
    Service for managing auto-wrapup timers and dispositions
    
    Usage:
        service = AutoWrapupService()
        service.start_wrapup_timer(agent_id=123, call_log_id=456, campaign_id=789)
        # Timer runs in background, auto-disposes if timeout reached
    """
    
    def __init__(self):
        self.channel_layer = get_channel_layer()
    
    def start_wrapup_timer(
        self, 
        agent_id: int, 
        call_log_id: int, 
        campaign_id: int
    ) -> Dict:
        """
        Start wrapup timer for an agent
        
        This records the wrapup start time and initiates countdown.
        The actual timeout checking is handled by a Celery periodic task.
        
        Args:
            agent_id: User ID of the agent
            call_log_id: CallLog ID for this call
            campaign_id: Campaign ID
        
        Returns:
            dict: Wrapup timer info
        """
        from users.models import AgentStatus
        from campaigns.models import Campaign
        from calls.models import CallLog
        
        try:
            # Get campaign configuration
            campaign = Campaign.objects.get(id=campaign_id)
            
            if not campaign.auto_wrapup_enabled:
                logger.debug(f"Auto-wrapup not enabled for campaign {campaign_id}")
                return {'enabled': False}
            
            # Update agent status
            agent_status = AgentStatus.objects.filter(user_id=agent_id).first()
            if not agent_status:
                logger.error(f"AgentStatus not found for agent {agent_id}")
                return {'error': 'Agent status not found'}
            
            # Record wrapup start time
            now = timezone.now()
            agent_status.status = 'wrapup'
            agent_status.wrapup_start_time = now
            agent_status.current_call_id = str(call_log_id)
            agent_status.save()
            
            timeout_seconds = campaign.auto_wrapup_timeout
            
            logger.info(
                f"Started wrapup timer for agent {agent_id}, "
                f"call {call_log_id}, timeout: {timeout_seconds}s"
            )
            
            # Notify agent via WebSocket
            self._notify_agent_wrapup_started(
                agent_id, 
                timeout_seconds,
                call_log_id
            )
            
            return {
                'enabled': True,
                'agent_id': agent_id,
                'call_log_id': call_log_id,
                'campaign_id': campaign_id,
                'timeout_seconds': timeout_seconds,
                'wrapup_start_time': now.isoformat(),
                'auto_disposition': campaign.auto_wrapup_disposition
            }
            
        except Campaign.DoesNotExist:
            logger.error(f"Campaign {campaign_id} not found")
            return {'error': 'Campaign not found'}
        except Exception as e:
            logger.error(f"Error starting wrapup timer: {e}", exc_info=True)
            return {'error': str(e)}
    
    def check_and_process_timeouts(self) -> Dict:
        """
        Check all agents in wrapup status and auto-dispose if timeout reached
        
        This method is called by a Celery periodic task every few seconds.
        
        Returns:
            dict: Processing statistics
        """
        from users.models import AgentStatus
        from campaigns.models import Campaign
        from calls.models import CallLog
        
        stats = {
            'checked': 0,
            'timed_out': 0,
            'auto_disposed': 0,
            'errors': 0
        }
        
        try:
            now = timezone.now()
            
            # TEMPORARILY DISABLED: wrapup_start_time field doesn't exist in AgentStatus
            # TODO: Add wrapup_start_time field to AgentStatus model or use status_changed_at
            # Get all agents in wrapup status
            agents_in_wrapup = AgentStatus.objects.filter(
                status='wrapup',
                # wrapup_start_time__isnull=False,  # DISABLED - field doesn't exist
                current_campaign__isnull=False
            ).select_related('current_campaign')
            
            stats['checked'] = agents_in_wrapup.count()
            
            for agent_status in agents_in_wrapup:
                try:
                    campaign = agent_status.current_campaign
                    
                    # Check if auto-wrapup is enabled
                    if not campaign.auto_wrapup_enabled:
                        continue
                    
                    # Calculate time in wrapup
                    wrapup_duration = (now - agent_status.wrapup_start_time).total_seconds()
                    timeout = campaign.auto_wrapup_timeout
                    
                    # Check if timeout reached
                    if wrapup_duration >= timeout:
                        stats['timed_out'] += 1
                        
                        # Apply auto-disposition
                        success = self._apply_auto_disposition(
                            agent_status=agent_status,
                            campaign=campaign,
                            disposition_status=campaign.auto_wrapup_disposition
                        )
                        
                        if success:
                            stats['auto_disposed'] += 1
                            logger.info(
                                f"Auto-disposed call for agent {agent_status.user_id} "
                                f"after {wrapup_duration:.0f}s timeout"
                            )
                        
                except Exception as e:
                    logger.error(f"Error processing agent {agent_status.user_id}: {e}")
                    stats['errors'] += 1
            
            if stats['auto_disposed'] > 0:
                logger.info(f"Auto-wrapup stats: {stats}")
            
            return stats
            
        except Exception as e:
            logger.error(f"Error in check_and_process_timeouts: {e}", exc_info=True)
            stats['errors'] += 1
            return stats
    
    def _apply_auto_disposition(
        self, 
        agent_status, 
        campaign, 
        disposition_status: str
    ) -> bool:
        """
        Apply automatic disposition to call and update agent status
        
        Args:
            agent_status: AgentStatus instance
            campaign: Campaign instance
            disposition_status: Disposition status to apply
        
        Returns:
            bool: True if successful
        """
        from calls.models import CallLog
        from leads.models import Lead
        
        try:
            # Get the call log
            if not agent_status.current_call_id:
                logger.warning(f"No current call ID for agent {agent_status.user_id}")
                return False
            
            call_log = CallLog.objects.filter(id=agent_status.current_call_id).first()
            if not call_log:
                logger.warning(f"CallLog {agent_status.current_call_id} not found")
                # Still set agent to available
                agent_status.status = 'available'
                agent_status.wrapup_start_time = None
                agent_status.current_call_id = ''
                agent_status.save()
                return False
            
            # Check if already dispositioned
            if call_log.disposition_status and call_log.disposition_status != 'pending':
                logger.debug(f"Call {call_log.id} already dispositioned: {call_log.disposition_status}")
                # Set agent to available
                agent_status.status = 'available'
                agent_status.wrapup_start_time = None
                agent_status.current_call_id = ''
                agent_status.save()
                return True
            
            # Apply disposition
            call_log.disposition_status = disposition_status
            call_log.disposition_time = timezone.now()
            call_log.disposition_notes = 'Auto-dispositioned after timeout'
            call_log.auto_dispositioned = True
            call_log.save()
            
            # Update lead status if exists
            if call_log.lead:
                call_log.lead.status = disposition_status
                call_log.lead.last_contact_date = timezone.now()
                call_log.lead.save(update_fields=['status', 'last_contact_date'])
            
            # Set agent to available
            agent_status.status = 'available'
            agent_status.wrapup_start_time = None
            agent_status.current_call_id = ''
            agent_status.save()
            
            # Notify agent via WebSocket
            self._notify_agent_auto_disposed(
                agent_status.user_id,
                call_log.id,
                disposition_status
            )
            
            # Track in agent tracking system
            try:
                from users.tracking import AgentTracker
                tracker = AgentTracker()
                tracker.set_available(agent_status.user_id, campaign.id)
            except Exception as e:
                logger.debug(f"Error updating agent tracker: {e}")
            
            logger.info(
                f"Auto-disposed call {call_log.id} for agent {agent_status.user_id} "
                f"with status: {disposition_status}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error applying auto-disposition: {e}", exc_info=True)
            return False
    
    def cancel_wrapup_timer(self, agent_id: int) -> bool:
        """
        Cancel wrapup timer (called when agent manually disposes call)
        
        Args:
            agent_id: User ID of the agent
        
        Returns:
            bool: True if cancelled successfully
        """
        from users.models import AgentStatus
        
        try:
            agent_status = AgentStatus.objects.filter(user_id=agent_id).first()
            if not agent_status:
                return False
            
            # Clear wrapup fields
            agent_status.wrapup_start_time = None
            agent_status.current_call_id = ''
            agent_status.save()
            
            logger.debug(f"Cancelled wrapup timer for agent {agent_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling wrapup timer: {e}")
            return False
    
    def get_remaining_time(self, agent_id: int) -> Optional[int]:
        """
        Get remaining time before auto-disposition
        
        Args:
            agent_id: User ID of the agent
        
        Returns:
            int: Seconds remaining, or None if not in wrapup
        """
        from users.models import AgentStatus
        
        try:
            agent_status = AgentStatus.objects.filter(user_id=agent_id).first()
            if not agent_status or agent_status.status != 'wrapup':
                return None
            
            if not agent_status.wrapup_start_time or not agent_status.current_campaign:
                return None
            
            campaign = agent_status.current_campaign
            if not campaign.auto_wrapup_enabled:
                return None
            
            elapsed = (timezone.now() - agent_status.wrapup_start_time).total_seconds()
            timeout = campaign.auto_wrapup_timeout
            remaining = max(0, timeout - elapsed)
            
            return int(remaining)
            
        except Exception as e:
            logger.error(f"Error getting remaining time: {e}")
            return None
    
    def _notify_agent_wrapup_started(
        self, 
        agent_id: int, 
        timeout_seconds: int,
        call_log_id: int
    ):
        """Send WebSocket notification to agent that wrapup started"""
        if not self.channel_layer:
            return
        
        try:
            async_to_sync(self.channel_layer.group_send)(
                f'agent_{agent_id}',
                {
                    'type': 'wrapup_started',
                    'data': {
                        'type': 'wrapup_started',
                        'timeout_seconds': timeout_seconds,
                        'call_log_id': call_log_id,
                        'message': f'Call ended. Wrapup time: {timeout_seconds} seconds'
                    }
                }
            )
        except Exception as e:
            logger.error(f"Error sending wrapup notification: {e}")
    
    def _notify_agent_auto_disposed(
        self, 
        agent_id: int, 
        call_log_id: int,
        disposition_status: str
    ):
        """Send WebSocket notification to agent that call was auto-disposed"""
        if not self.channel_layer:
            return
        
        try:
            async_to_sync(self.channel_layer.group_send)(
                f'agent_{agent_id}',
                {
                    'type': 'call_auto_disposed',
                    'data': {
                        'type': 'call_auto_disposed',
                        'call_log_id': call_log_id,
                        'disposition': disposition_status,
                        'message': f'Call automatically dispositioned as: {disposition_status}'
                    }
                }
            )
        except Exception as e:
            logger.error(f"Error sending auto-dispose notification: {e}")


# Singleton instance
_auto_wrapup_service = None

def get_auto_wrapup_service() -> AutoWrapupService:
    """Get singleton instance of AutoWrapupService"""
    global _auto_wrapup_service
    if _auto_wrapup_service is None:
        _auto_wrapup_service = AutoWrapupService()
    return _auto_wrapup_service
