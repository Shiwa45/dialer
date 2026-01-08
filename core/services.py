
import logging
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

class RealTimeStatusService:
    """Service for managing real-time status updates across the system"""
    
    def __init__(self):
        self.channel_layer = get_channel_layer()
    
    def update_agent_status(self, agent, new_status, reason=None, campaign=None):
        """
        Update agent status with real-time notifications
        
        Args:
            agent: User object
            new_status: New status string
            reason: Optional reason for status change
            campaign: Optional campaign context
        """
        try:
            from users.models import AgentStatus
            from agents.models import AgentDialerSession
            from agents.telephony_service import AgentTelephonyService
            
            # Update or create agent status
            agent_status, created = AgentStatus.objects.get_or_create(
                user=agent,
                defaults={'status': new_status}
            )
            
            old_status = agent_status.status
            agent_status.status = new_status
            agent_status.status_changed_at = timezone.now()
            
            if reason:
                agent_status.break_reason = reason
            if campaign:
                agent_status.current_campaign = campaign
                
            agent_status.save()
            
            # Handle telephony status changes
            telephony_service = AgentTelephonyService(agent)
            
            if new_status == 'available':
                # Make agent ready for calls
                self._make_agent_ready(agent, campaign, telephony_service)
            elif new_status in ['break', 'lunch', 'training', 'meeting', 'offline']:
                # Logout agent from dialer session
                self._logout_agent(agent, telephony_service)
            
            # Send real-time updates
            self._broadcast_status_update(agent, old_status, new_status, reason)
            
            logger.info(f"Agent {agent.username} status updated: {old_status} -> {new_status}")
            
            return {
                'success': True,
                'old_status': old_status,
                'new_status': new_status,
                'timestamp': agent_status.status_changed_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error updating agent status: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _make_agent_ready(self, agent, campaign, telephony_service):
        """Make agent ready for calls"""
        try:
            # Login to campaign if specified
            if campaign:
                result = telephony_service.login_campaign(campaign.id)
                if not result.get('success'):
                    logger.warning(f"Failed to login agent {agent.username} to campaign")
            else:
                # Find default campaign
                from campaigns.models import Campaign
                default_campaign = Campaign.objects.filter(
                    assigned_users=agent,
                    status='active'
                ).first()
                
                if default_campaign:
                    telephony_service.login_campaign(default_campaign.id)
                    
        except Exception as e:
            logger.error(f"Error making agent ready: {e}")
    
    def _logout_agent(self, agent, telephony_service):
        """Logout agent from dialer session"""
        try:
            result = telephony_service.logout_session()
            if not result.get('success'):
                logger.warning(f"Failed to logout agent {agent.username}")
        except Exception as e:
            logger.error(f"Error logging out agent: {e}")
    
    def _broadcast_status_update(self, agent, old_status, new_status, reason):
        """Broadcast status update to relevant parties"""
        try:
            # Update to the agent themselves
            async_to_sync(self.channel_layer.group_send)(
                f"agent_{agent.id}",
                {
                    'type': 'status_update',
                    'data': {
                        'type': 'status_changed',
                        'old_status': old_status,
                        'new_status': new_status,
                        'reason': reason,
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
            
            # Update to supervisors
            async_to_sync(self.channel_layer.group_send)(
                'supervisors',
                {
                    'type': 'agent_status_change',
                    'agent_id': agent.id,
                    'agent_name': agent.get_full_name() or agent.username,
                    'old_status': old_status,
                    'new_status': new_status,
                    'reason': reason,
                    'timestamp': timezone.now().isoformat()
                }
            )
            
            # Update global stats
            self._update_global_statistics()
            
        except Exception as e:
            logger.error(f"Error broadcasting status update: {e}")
    
    def _update_global_statistics(self):
        """Update and broadcast global system statistics"""
        try:
            from users.models import AgentStatus
            from telephony.models import CallLog
            from django.db.models import Count, Q
            
            # Get agent counts by status
            agent_counts = dict(
                AgentStatus.objects.values('status').annotate(
                    count=Count('id')
                ).values_list('status', 'count')
            )
            
            # Get today's call stats
            today = timezone.now().date()
            today_calls = CallLog.objects.filter(start_time__date=today)
            
            call_stats = {
                'total_calls': today_calls.count(),
                'answered_calls': today_calls.filter(
                    call_status__in=['answered', 'completed']
                ).count(),
                'active_calls': today_calls.filter(
                    call_status__in=['ringing', 'answered']
                ).count(),
            }
            
            # Broadcast to supervisors
            async_to_sync(self.channel_layer.group_send)(
                'supervisors',
                {
                    'type': 'call_statistics_update',
                    'data': {
                        'type': 'global_stats_update',
                        'agent_counts': agent_counts,
                        'call_stats': call_stats,
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error updating global statistics: {e}")
    
    def update_campaign_statistics(self, campaign_id):
        """Update and broadcast campaign-specific statistics"""
        try:
            from campaigns.models import Campaign
            from telephony.models import CallLog
            from agents.models import AgentDialerSession
            from campaigns.services import HopperService
            
            campaign = Campaign.objects.get(id=campaign_id)
            today = timezone.now().date()
            
            # Get campaign stats
            campaign_calls = CallLog.objects.filter(
                campaign=campaign,
                start_time__date=today
            )
            
            stats = {
                'total_calls': campaign_calls.count(),
                'answered_calls': campaign_calls.filter(
                    call_status__in=['answered', 'completed']
                ).count(),
                'active_calls': campaign_calls.filter(
                    call_status__in=['ringing', 'answered']
                ).count(),
                'agents_logged_in': AgentDialerSession.objects.filter(
                    campaign=campaign,
                    status__in=['ready', 'on_call', 'wrapup']
                ).count(),
                'hopper_count': HopperService.get_hopper_count(campaign_id),
                'active_dialing': HopperService.get_active_call_count(campaign_id)
            }
            
            # Broadcast campaign stats
            async_to_sync(self.channel_layer.group_send)(
                f"campaign_{campaign_id}",
                {
                    'type': 'campaign_stats_update',
                    'data': {
                        'campaign_id': campaign_id,
                        'campaign_name': campaign.name,
                        'stats': stats,
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
            
            # Also send to supervisors
            async_to_sync(self.channel_layer.group_send)(
                'supervisors',
                {
                    'type': 'campaign_stats_update',
                    'data': {
                        'campaign_id': campaign_id,
                        'campaign_name': campaign.name,
                        'stats': stats,
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error updating campaign statistics: {e}")
