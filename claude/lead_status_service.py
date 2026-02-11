"""
Lead Status Management Service - Phase 2.1

This service ensures every lead has proper status tracking and no leads are "lost"
in the system without status.

Features:
- Automatic status assignment based on call results
- Status synchronization from CallLog to Lead
- Detection and fixing of leads with missing status
- Comprehensive status tracking
"""

import logging
from typing import Dict, List, Optional
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count

logger = logging.getLogger(__name__)


class LeadStatusService:
    """
    Service for managing lead status and ensuring data integrity
    
    Phase 2.1: Fix leads with missing or incorrect status
    """
    
    # Valid status transitions (from -> to)
    VALID_STATUS_TRANSITIONS = {
        'new': ['no_answer', 'busy', 'failed', 'dropped', 'answered', 'contacted', 'not_interested', 'dnc', 'invalid'],
        'no_answer': ['no_answer', 'busy', 'failed', 'dropped', 'answered', 'contacted', 'callback', 'not_interested', 'dnc'],
        'busy': ['no_answer', 'busy', 'failed', 'dropped', 'answered', 'contacted', 'callback', 'not_interested', 'dnc'],
        'failed': ['no_answer', 'busy', 'failed', 'dropped', 'answered', 'contacted', 'not_interested', 'dnc'],
        'dropped': ['no_answer', 'busy', 'failed', 'dropped', 'answered', 'contacted', 'callback', 'not_interested', 'dnc'],
        'contacted': ['callback', 'sale', 'not_interested', 'dnc', 'no_answer', 'busy'],
        'callback': ['no_answer', 'busy', 'contacted', 'sale', 'not_interested', 'dnc'],
        'not_interested': [],  # Final state
        'dnc': [],  # Final state
        'sale': [],  # Final state
        'invalid': [],  # Final state
    }
    
    # Recyclable statuses (can be retried)
    RECYCLABLE_STATUSES = [
        'no_answer',
        'busy',
        'failed',
        'dropped',
        'congestion',
        'callback'
    ]
    
    # Final statuses (should not be recycled)
    FINAL_STATUSES = [
        'sale',
        'dnc',
        'not_interested',
        'invalid'
    ]
    
    def update_lead_from_call_result(
        self,
        lead_id: int,
        call_status: str,
        call_result: str = None,
        disposition: str = None,
        increment_dial: bool = True
    ) -> Dict:
        """
        Update lead status based on call result
        
        Args:
            lead_id: Lead ID
            call_status: Call status from CallLog (answered, no_answer, busy, etc.)
            call_result: Optional additional call result info
            disposition: Optional disposition from agent
            increment_dial: Whether to increment dial attempt counter
        
        Returns:
            dict: Update result
        """
        from leads.models import Lead
        
        try:
            lead = Lead.objects.select_for_update().get(id=lead_id)
            
            old_status = lead.status
            
            # Determine new status based on call result
            new_status = self._determine_status_from_call(
                call_status=call_status,
                disposition=disposition,
                current_status=lead.status
            )
            
            # Update lead
            with transaction.atomic():
                if increment_dial:
                    lead.dial_attempts = (lead.dial_attempts or 0) + 1
                
                lead.last_dial_attempt = timezone.now()
                lead.dial_result = call_status
                
                # Increment answered count if applicable
                if call_status in ['answered', 'in_progress']:
                    lead.answered_count = (lead.answered_count or 0) + 1
                    lead.last_contact_date = timezone.now()
                
                # Update status if changed
                if new_status and new_status != old_status:
                    lead.status = new_status
                    lead.last_status_change = timezone.now()
                
                # Update call_count (backward compatibility)
                if call_status in ['answered', 'in_progress']:
                    lead.call_count = (lead.call_count or 0) + 1
                
                lead.save()
            
            logger.info(
                f"Updated lead {lead_id}: "
                f"status {old_status} -> {new_status}, "
                f"dial_attempts: {lead.dial_attempts}, "
                f"call_status: {call_status}"
            )
            
            return {
                'success': True,
                'lead_id': lead_id,
                'old_status': old_status,
                'new_status': new_status,
                'dial_attempts': lead.dial_attempts
            }
            
        except Lead.DoesNotExist:
            logger.error(f"Lead {lead_id} not found")
            return {'success': False, 'error': 'Lead not found'}
        except Exception as e:
            logger.error(f"Error updating lead {lead_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _determine_status_from_call(
        self,
        call_status: str,
        disposition: str = None,
        current_status: str = 'new'
    ) -> str:
        """Determine lead status based on call result"""
        
        # If agent provided disposition, use that
        if disposition:
            return disposition
        
        # Map call status to lead status
        status_map = {
            'answered': 'contacted',
            'in_progress': 'contacted',
            'no_answer': 'no_answer',
            'busy': 'busy',
            'failed': 'failed',
            'dropped': 'dropped',
            'congestion': 'congestion',
            'invalid': 'invalid',
        }
        
        new_status = status_map.get(call_status, current_status)
        
        # Validate transition
        if self._is_valid_transition(current_status, new_status):
            return new_status
        
        # If transition invalid, keep current status
        return current_status
    
    def _is_valid_transition(self, from_status: str, to_status: str) -> bool:
        """Check if status transition is valid"""
        if from_status == to_status:
            return True
        
        valid_transitions = self.VALID_STATUS_TRANSITIONS.get(from_status, [])
        return to_status in valid_transitions
    
    def find_leads_with_missing_status(self, campaign_id: int = None) -> Dict:
        """
        Find leads that have dial attempts but incorrect or missing status
        
        This identifies leads that were dialed but somehow lost their status tracking
        
        Args:
            campaign_id: Optional campaign filter
        
        Returns:
            dict: Statistics about leads with missing status
        """
        from leads.models import Lead, LeadList
        from calls.models import CallLog
        
        try:
            # Query leads with dial attempts but status still 'new'
            query = Lead.objects.filter(
                dial_attempts__gt=0,
                status='new'
            )
            
            # Filter by campaign if provided
            if campaign_id:
                lead_lists = LeadList.objects.filter(
                    assigned_campaign_id=campaign_id
                )
                query = query.filter(lead_list__in=lead_lists)
            
            problematic_leads = list(query.values_list('id', flat=True))
            
            # Also find leads with calls but no dial_attempts recorded
            leads_with_calls = CallLog.objects.filter(
                lead__isnull=False
            ).values_list('lead_id', flat=True).distinct()
            
            leads_missing_dial_count = Lead.objects.filter(
                id__in=leads_with_calls,
                dial_attempts=0
            )
            
            if campaign_id:
                leads_missing_dial_count = leads_missing_dial_count.filter(
                    lead_list__in=lead_lists
                )
            
            missing_dial_tracking = list(leads_missing_dial_count.values_list('id', flat=True))
            
            return {
                'dialed_but_new': len(problematic_leads),
                'dialed_but_new_ids': problematic_leads[:100],  # Sample
                'missing_dial_tracking': len(missing_dial_tracking),
                'missing_dial_tracking_ids': missing_dial_tracking[:100],  # Sample
                'total_issues': len(problematic_leads) + len(missing_dial_tracking)
            }
            
        except Exception as e:
            logger.error(f"Error finding leads with missing status: {e}", exc_info=True)
            return {'error': str(e)}
    
    def fix_leads_with_missing_status(
        self,
        lead_ids: List[int] = None,
        campaign_id: int = None,
        dry_run: bool = False
    ) -> Dict:
        """
        Fix leads that have missing or incorrect status by analyzing call history
        
        Args:
            lead_ids: Specific lead IDs to fix (optional)
            campaign_id: Fix all leads in campaign (optional)
            dry_run: If True, only report what would be fixed
        
        Returns:
            dict: Fix statistics
        """
        from leads.models import Lead, LeadList
        from calls.models import CallLog
        
        stats = {
            'leads_checked': 0,
            'leads_fixed': 0,
            'status_assigned': {},
            'errors': 0
        }
        
        try:
            # Build query
            if lead_ids:
                leads = Lead.objects.filter(id__in=lead_ids)
            elif campaign_id:
                lead_lists = LeadList.objects.filter(assigned_campaign_id=campaign_id)
                leads = Lead.objects.filter(lead_list__in=lead_lists)
            else:
                # Fix all problematic leads
                leads = Lead.objects.filter(
                    Q(dial_attempts__gt=0, status='new') |
                    Q(id__in=CallLog.objects.filter(
                        lead__isnull=False
                    ).values_list('lead_id', flat=True), dial_attempts=0)
                )
            
            leads = leads.select_related('lead_list')
            
            for lead in leads:
                stats['leads_checked'] += 1
                
                try:
                    # Get call history for this lead
                    calls = CallLog.objects.filter(
                        lead=lead
                    ).order_by('-start_time')
                    
                    if not calls.exists():
                        # No calls found but dial_attempts > 0, this is an error
                        if not dry_run and lead.dial_attempts > 0:
                            lead.dial_attempts = 0
                            lead.save()
                        continue
                    
                    # Analyze calls to determine correct status
                    latest_call = calls.first()
                    total_calls = calls.count()
                    answered_calls = calls.filter(
                        call_status__in=['answered', 'in_progress']
                    ).count()
                    
                    # Determine correct status
                    if latest_call.disposition_status:
                        correct_status = latest_call.disposition_status
                    elif latest_call.call_status == 'answered':
                        correct_status = 'contacted'
                    elif latest_call.call_status in ['no_answer', 'busy', 'failed', 'dropped', 'congestion']:
                        correct_status = latest_call.call_status
                    else:
                        correct_status = 'contacted' if answered_calls > 0 else 'no_answer'
                    
                    # Apply fix
                    if not dry_run:
                        lead.status = correct_status
                        lead.dial_attempts = total_calls
                        lead.answered_count = answered_calls
                        lead.last_dial_attempt = latest_call.start_time
                        lead.dial_result = latest_call.call_status
                        lead.last_status_change = timezone.now()
                        
                        if answered_calls > 0:
                            lead.call_count = answered_calls
                            lead.last_contact_date = latest_call.start_time
                        
                        lead.save()
                    
                    stats['leads_fixed'] += 1
                    stats['status_assigned'][correct_status] = stats['status_assigned'].get(correct_status, 0) + 1
                    
                    if dry_run:
                        logger.info(
                            f"[DRY RUN] Would fix lead {lead.id}: "
                            f"{lead.status} -> {correct_status}, "
                            f"dial_attempts: {lead.dial_attempts} -> {total_calls}"
                        )
                    
                except Exception as e:
                    logger.error(f"Error fixing lead {lead.id}: {e}")
                    stats['errors'] += 1
            
            logger.info(f"Lead status fix completed: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error in fix_leads_with_missing_status: {e}", exc_info=True)
            return {'error': str(e)}
    
    def get_recyclable_leads(
        self,
        campaign_id: int,
        max_attempts: int = 5,
        hours_since_last: int = 4
    ) -> List[int]:
        """
        Get list of lead IDs that can be recycled (retried)
        
        Args:
            campaign_id: Campaign ID
            max_attempts: Maximum dial attempts allowed
            hours_since_last: Minimum hours since last dial attempt
        
        Returns:
            list: Lead IDs eligible for recycling
        """
        from leads.models import Lead, LeadList
        
        try:
            cutoff_time = timezone.now() - timedelta(hours=hours_since_last)
            
            lead_lists = LeadList.objects.filter(assigned_campaign_id=campaign_id)
            
            recyclable = Lead.objects.filter(
                lead_list__in=lead_lists,
                status__in=self.RECYCLABLE_STATUSES,
                dial_attempts__lt=max_attempts,
                last_dial_attempt__lt=cutoff_time
            ).values_list('id', flat=True)
            
            return list(recyclable)
            
        except Exception as e:
            logger.error(f"Error getting recyclable leads: {e}")
            return []


# Singleton instance
_lead_status_service = None

def get_lead_status_service() -> LeadStatusService:
    """Get singleton instance of LeadStatusService"""
    global _lead_status_service
    if _lead_status_service is None:
        _lead_status_service = LeadStatusService()
    return _lead_status_service
