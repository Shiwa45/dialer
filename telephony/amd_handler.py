# telephony/amd_handler.py

import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


class AMDHandler:
    """
    Handle Answering Machine Detection results
    """
    
    @staticmethod
    def process_amd_result(channel_id, amd_status, amd_cause=None):
        """
        Process AMD result and determine if call should be connected to agent
        
        Args:
            channel_id: Asterisk channel ID
            amd_status: AMD status (HUMAN, MACHINE, NOTSURE, HANGUP)
            amd_cause: Optional cause (TOOLONG, INITIALSILENCE, etc.)
        
        Returns:
            dict with 'is_human' boolean and 'action' string
        """
        logger.info(f"AMD Result for {channel_id}: status={amd_status}, cause={amd_cause}")
        
        # Determine if human
        is_human = amd_status == 'HUMAN'
        
        # Conservative approach: treat NOTSURE as human to avoid false positives
        if amd_status == 'NOTSURE':
            is_human = True
            logger.warning(f"AMD uncertain for {channel_id}, treating as HUMAN")
        
        # Determine action
        if is_human:
            action = 'connect_to_agent'
        elif amd_status == 'MACHINE':
            action = 'hangup'  # or 'leave_voicemail' if configured
        elif amd_status == 'HANGUP':
            action = 'mark_failed'
        else:
            action = 'hangup'
        
        return {
            'is_human': is_human,
            'action': action,
            'amd_status': amd_status,
            'amd_cause': amd_cause,
            'timestamp': timezone.now()
        }
    
    @staticmethod
    def should_use_amd(campaign):
        """
        Check if AMD should be used for this campaign
        """
        return getattr(campaign, 'amd_enabled', False)
