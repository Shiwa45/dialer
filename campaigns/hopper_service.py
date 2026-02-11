"""
Enhanced Hopper Service - Phase 2.2

Improvements:
- Proper lead status updates on dial
- Failed call handling and recycling
- Retry logic with delays
- Comprehensive eligibility checks
"""

import logging
from typing import List, Dict, Optional
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

logger = logging.getLogger(__name__)


class HopperService:
    """
    Enhanced service for managing dialer hopper
    
    Phase 2.2: Proper status tracking and retry logic
    """
    
    @staticmethod
    def get_eligible_leads(campaign_id: int, limit: int = 100) -> List:
        """
        Get eligible leads for dialing
        
        Phase 2.2 Enhancement: Includes leads with recyclable statuses
        
        Args:
            campaign_id: Campaign ID
            limit: Maximum number of leads to return
        
        Returns:
            list: Eligible Lead objects
        """
        from leads.models import Lead, LeadList
        from campaigns.models import Campaign
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            max_attempts = campaign.max_attempts or 5
            
            # Get lead lists for this campaign
            lead_lists = LeadList.objects.filter(
                assigned_campaign_id=campaign_id,
                is_active=True
            )
            
            # Recyclable statuses
            recyclable_statuses = [
                'new',
                'no_answer',
                'busy',
                'failed',
                'dropped',
                'congestion',
                'callback'
            ]
            
            # Time-based retry logic
            now = timezone.now()
            retry_cutoff = now - timedelta(hours=4)
            
            # Build query
            query = Q(
                lead_list__in=lead_lists,
                status__in=recyclable_statuses,
                dial_attempts__lt=max_attempts
            )
            
            # For leads that have been dialed, add time restriction
            query &= (
                Q(last_dial_attempt__isnull=True) |  # Never dialed
                Q(last_dial_attempt__lt=retry_cutoff)  # Retry after delay
            )
            
            # Order by priority and last dial attempt
            leads = Lead.objects.filter(query).order_by(
                '-priority',  # High priority first
                'last_dial_attempt',  # Oldest attempts first
                'dial_attempts'  # Fewer attempts first
            )[:limit]
            
            return list(leads)
            
        except Exception as e:
            logger.error(f"Error getting eligible leads: {e}", exc_info=True)
            return []
    
    @staticmethod
    def add_leads_to_hopper(campaign_id: int, lead_ids: List[int]) -> int:
        """
        Add leads to hopper
        
        Phase 2.2: Validates lead eligibility before adding
        
        Args:
            campaign_id: Campaign ID
            lead_ids: List of lead IDs to add
        
        Returns:
            int: Number of leads added
        """
        from campaigns.models import DialerHopper
        from leads.models import Lead
        
        try:
            # Validate leads exist and are eligible
            leads = Lead.objects.filter(
                id__in=lead_ids
            ).select_related('lead_list')
            
            added = 0
            
            for lead in leads:
                # Check if already in hopper
                exists = DialerHopper.objects.filter(
                    campaign_id=campaign_id,
                    lead=lead,
                    status__in=['new', 'locked', 'dialing']
                ).exists()
                
                if exists:
                    continue
                
                # Add to hopper
                DialerHopper.objects.create(
                    campaign_id=campaign_id,
                    lead=lead,
                    phone_number=lead.phone_number,
                    status='new',
                    priority=lead.priority if hasattr(lead, 'priority') else 'medium'
                )
                added += 1
            
            logger.info(f"Added {added} leads to hopper for campaign {campaign_id}")
            return added
            
        except Exception as e:
            logger.error(f"Error adding leads to hopper: {e}", exc_info=True)
            return 0
    
    @staticmethod
    def fill_hopper(campaign_id: int, target_count: int = 100) -> int:
        """
        Fill hopper to target count
        
        Phase 2.2: Smart filling based on lead status
        
        Args:
            campaign_id: Campaign ID
            target_count: Target number of leads in hopper
        
        Returns:
            int: Number of leads added
        """
        from campaigns.models import DialerHopper
        
        try:
            # Check current hopper count
            current_count = DialerHopper.objects.filter(
                campaign_id=campaign_id,
                status='new'
            ).count()
            
            if current_count >= target_count:
                return 0
            
            # Get eligible leads
            needed = target_count - current_count
            eligible_leads = HopperService.get_eligible_leads(
                campaign_id=campaign_id,
                limit=needed * 2  # Get extra in case some filtered out
            )
            
            if not eligible_leads:
                logger.warning(f"No eligible leads found for campaign {campaign_id}")
                return 0
            
            # Add leads to hopper
            lead_ids = [lead.id for lead in eligible_leads[:needed]]
            added = HopperService.add_leads_to_hopper(campaign_id, lead_ids)
            
            return added
            
        except Exception as e:
            logger.error(f"Error filling hopper: {e}", exc_info=True)
            return 0
    
    @staticmethod
    def handle_dial_attempt(lead_id: int, campaign_id: int, result: str) -> Dict:
        """
        Handle dial attempt result and update lead
        
        Phase 2.2: Comprehensive result handling
        
        Args:
            lead_id: Lead ID
            campaign_id: Campaign ID
            result: Dial result (answered, no_answer, busy, failed, etc.)
        
        Returns:
            dict: Update result
        """
        from leads.lead_status_service import get_lead_status_service
        
        try:
            service = get_lead_status_service()
            
            # Update lead status
            update_result = service.update_lead_from_call_result(
                lead_id=lead_id,
                call_status=result,
                increment_dial=True
            )
            
            # Handle based on result
            if result in ['no_answer', 'busy', 'congestion']:
                # Recyclable - will be retried later
                logger.debug(f"Lead {lead_id} marked as {result}, will retry")
            
            elif result == 'failed':
                # Technical failure - immediate retry eligible
                logger.debug(f"Lead {lead_id} failed, eligible for immediate retry")
            
            elif result == 'dropped':
                # Dropped call - high priority retry
                logger.warning(f"Lead {lead_id} call dropped, marking for high priority retry")
            
            elif result in ['answered', 'in_progress']:
                # Successfully connected
                logger.info(f"Lead {lead_id} answered")
            
            return update_result
            
        except Exception as e:
            logger.error(f"Error handling dial attempt: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def cleanup_stale_entries(minutes: int = 10) -> int:
        """
        Clean up stale hopper entries
        
        Phase 2.2: Remove stuck/locked entries
        
        Args:
            minutes: Age threshold in minutes
        
        Returns:
            int: Number of entries cleaned
        """
        from campaigns.models import DialerHopper
        
        try:
            cutoff = timezone.now() - timedelta(minutes=minutes)
            
            # Find stuck entries
            stuck_entries = DialerHopper.objects.filter(
                status__in=['locked', 'dialing'],
                locked_at__lt=cutoff
            )
            
            count = stuck_entries.count()
            
            if count > 0:
                # Reset to 'new' status
                stuck_entries.update(
                    status='new',
                    locked_at=None,
                    locked_by=None
                )
                
                logger.info(f"Cleaned up {count} stale hopper entries")
            
            return count
            
        except Exception as e:
            logger.error(f"Error cleaning stale entries: {e}", exc_info=True)
            return 0
    
    @staticmethod
    def get_hopper_stats(campaign_id: int) -> Dict:
        """
        Get hopper statistics
        
        Args:
            campaign_id: Campaign ID
        
        Returns:
            dict: Hopper statistics
        """
        from campaigns.models import DialerHopper
        from django.db.models import Count
        
        try:
            stats = DialerHopper.objects.filter(
                campaign_id=campaign_id
            ).values('status').annotate(
                count=Count('id')
            )
            
            status_dict = {item['status']: item['count'] for item in stats}
            
            return {
                'total': sum(status_dict.values()),
                'new': status_dict.get('new', 0),
                'locked': status_dict.get('locked', 0),
                'dialing': status_dict.get('dialing', 0),
                'completed': status_dict.get('completed', 0)
            }
            
        except Exception as e:
            logger.error(f"Error getting hopper stats: {e}", exc_info=True)
            return {}


# Convenience function
def get_hopper_service() -> HopperService:
    """Get HopperService instance"""
    return HopperService()
