from django.db.models.signals import post_save
from django.dispatch import receiver
from users.models import AgentStatus
from reports.consumers import broadcast_agent_update, broadcast_call_event
import logging
import re

logger = logging.getLogger(__name__)

@receiver(post_save, sender=AgentStatus)
def agent_status_changed(sender, instance, created, **kwargs):
    """
    Broadcast agent status changes to real-time dashboard
    """
    try:
        # Determine campaign ID
        campaign_id = instance.current_campaign.id if instance.current_campaign else None
        
        # Broadcast update
        broadcast_agent_update(
            agent_id=instance.user.id,
            status=instance.status,
            campaign_id=campaign_id
        )
        logger.debug(f"Broadcasted status update for agent {instance.user.username}: {instance.status}")
        
    except Exception as e:
        # Sanitize error message (remove potential passwords)
        msg = str(e)
        password_match = re.search(r"password='([^']*)'", msg)
        if password_match:
            msg = msg.replace(password_match.group(1), "********")
            
        logger.error(f"Error broadcasting agent status signal: {msg}")

@receiver(post_save, sender='calls.CallLog')
def call_log_changed(sender, instance, created, **kwargs):
    """
    Broadcast call events to dashboard
    """
    try:
        # Broadcast call event
        broadcast_call_event({
            'id': instance.id,
            'campaign_id': instance.campaign_id,
            'status': instance.call_status,
            'agent_id': instance.agent_id,
            'number': instance.called_number
        }, campaign_id=instance.campaign_id)

    except Exception as e:
        logger.error(f"Error broadcasting call signal: {e}")
