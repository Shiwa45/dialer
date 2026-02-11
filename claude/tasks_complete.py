"""
Campaign Tasks - Phase 1 & 2 Complete

This module includes all Celery tasks for:
- Phase 1.1: Auto wrapup timeout checking
- Phase 2.3: Dropped call re-attempt
- Phase 2.4: Lead recycling and status reconciliation
- Predictive dialing
- Hopper management
- Recording sync
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django.db.models import Q, Count

logger = logging.getLogger(__name__)


# ============================================================================
# PHASE 1.1: Auto Wrapup Timeout Checking
# ============================================================================

@shared_task
def check_auto_wrapup_timeouts():
    """
    PHASE 1.1: Check agents in wrapup and auto-dispose if timeout reached
    
    Schedule: Every 5 seconds
    """
    from campaigns.auto_wrapup_service import get_auto_wrapup_service
    
    try:
        service = get_auto_wrapup_service()
        stats = service.check_and_process_timeouts()
        
        if stats.get('timed_out', 0) > 0 or stats.get('errors', 0) > 0:
            logger.info(f"Auto-wrapup check completed: {stats}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error in check_auto_wrapup_timeouts: {e}", exc_info=True)
        return {'error': str(e)}


# ============================================================================
# Predictive Dialing
# ============================================================================

@shared_task
def predictive_dial():
    """
    Runs every second to dial calls based on predictive algorithm
    """
    from campaigns.models import Campaign
    from campaigns.predictive_dialer import DialerManager
    
    total_dialed = 0
    
    for campaign in Campaign.objects.filter(status='active', dial_mode='predictive'):
        try:
            dialed = DialerManager.dial_for_campaign(campaign.id)
            total_dialed += dialed
        except Exception as e:
            logger.error(f"Error dialing for campaign {campaign.id}: {e}")
    
    return {'dialed': total_dialed}


# ============================================================================
# PHASE 2.3: Dropped/Failed Call Re-attempt
# ============================================================================

@shared_task
def recycle_failed_calls():
    """
    PHASE 2.3: Recycle failed/dropped calls back to hopper
    
    Finds calls that failed (no answer, busy, dropped) and
    re-adds eligible leads to the hopper for retry.
    
    Schedule: Every 5 minutes
    """
    from campaigns.models import Campaign
    from campaigns.hopper_service import HopperService
    from leads.models import Lead
    
    stats = {
        'total_recycled': 0,
        'by_campaign': {},
        'by_status': {}
    }
    
    try:
        now = timezone.now()
        cutoff = now - timedelta(hours=4)
        
        recycle_statuses = ['failed', 'no_answer', 'busy', 'dropped', 'congestion']
        
        for campaign in Campaign.objects.filter(status='active'):
            max_attempts = campaign.max_attempts or 3
            
            # Get leads eligible for recycling
            eligible_leads = Lead.objects.filter(
                lead_list__assigned_campaign=campaign,
                status__in=recycle_statuses,
                last_dial_attempt__lt=cutoff,
                dial_attempts__lt=max_attempts
            )[:100]  # Batch of 100
            
            if not eligible_leads:
                continue
            
            # Add to hopper
            lead_ids = [lead.id for lead in eligible_leads]
            count = HopperService.add_leads_to_hopper(campaign.id, lead_ids)
            
            stats['total_recycled'] += count
            stats['by_campaign'][campaign.name] = count
            
            logger.info(f"Recycled {count} failed calls for campaign {campaign.name}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error in recycle_failed_calls: {e}", exc_info=True)
        return {'error': str(e)}


@shared_task
def retry_dropped_calls():
    """
    Handle dropped calls (customer answered but no agent available)
    These get immediate high-priority retry.
    
    Schedule: Every 2 minutes
    """
    from campaigns.models import DialerHopper
    from calls.models import CallLog
    from leads.models import Lead
    
    stats = {'retried': 0}
    
    try:
        cutoff = timezone.now() - timedelta(hours=1)
        
        # Find dropped calls
        dropped_calls = CallLog.objects.filter(
            call_status='dropped',
            start_time__gte=cutoff,
            lead__isnull=False,
            campaign__isnull=False
        ).select_related('lead', 'campaign')
        
        for call in dropped_calls:
            lead = call.lead
            
            # Check if already in hopper
            if DialerHopper.objects.filter(
                campaign=call.campaign,
                lead=lead,
                status__in=['new', 'locked', 'dialing']
            ).exists():
                continue
            
            # Add to hopper with high priority
            DialerHopper.objects.create(
                campaign=call.campaign,
                lead=lead,
                phone_number=lead.phone_number,
                priority=90,  # High priority
                status='new'
            )
            
            stats['retried'] += 1
        
        if stats['retried'] > 0:
            logger.info(f"Queued {stats['retried']} dropped calls for retry")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error in retry_dropped_calls: {e}")
        return {'error': str(e)}


# ============================================================================
# PHASE 2.4: Lead Status Reconciliation
# ============================================================================

@shared_task
def reconcile_lead_status():
    """
    PHASE 2.4: Daily reconciliation of lead status
    
    Finds and fixes leads with missing or incorrect status
    
    Schedule: Daily at 2 AM
    """
    from leads.lead_status_service import get_lead_status_service
    
    try:
        service = get_lead_status_service()
        
        # Find issues
        issues = service.find_leads_with_missing_status()
        
        if issues.get('total_issues', 0) > 0:
            logger.warning(
                f"Found {issues['total_issues']} leads with status issues: "
                f"dialed_but_new={issues['dialed_but_new']}, "
                f"missing_tracking={issues['missing_dial_tracking']}"
            )
            
            # Auto-fix if under threshold
            if issues['total_issues'] < 1000:
                result = service.fix_leads_with_missing_status(dry_run=False)
                logger.info(
                    f"Auto-fixed {result.get('leads_fixed', 0)} leads. "
                    f"Status distribution: {result.get('status_assigned', {})}"
                )
                return result
            else:
                logger.error(
                    f"Too many issues ({issues['total_issues']}) - manual review required"
                )
                return {'needs_manual_review': True, 'issues': issues}
        
        return {'status': 'ok', 'issues_found': 0}
        
    except Exception as e:
        logger.error(f"Error in reconcile_lead_status: {e}", exc_info=True)
        return {'error': str(e)}


@shared_task
def sync_call_log_to_lead_status():
    """
    PHASE 2.4: Sync CallLog status back to Lead
    
    Ensures every CallLog has updated corresponding Lead
    
    Schedule: Every 10 minutes
    """
    from calls.models import CallLog
    from leads.lead_status_service import get_lead_status_service
    
    stats = {
        'checked': 0,
        'updated': 0,
        'errors': 0
    }
    
    try:
        service = get_lead_status_service()
        
        # Get recent calls without proper lead updates
        cutoff = timezone.now() - timedelta(hours=2)
        
        calls_needing_sync = CallLog.objects.filter(
            lead__isnull=False,
            end_time__gte=cutoff,
            call_status__in=['no_answer', 'busy', 'failed', 'dropped', 'answered']
        ).select_related('lead')[:500]  # Batch of 500
        
        for call in calls_needing_sync:
            stats['checked'] += 1
            
            try:
                # Check if lead status matches call result
                lead = call.lead
                expected_status = service._determine_status_from_call(
                    call_status=call.call_status,
                    disposition=call.disposition_status,
                    current_status=lead.status
                )
                
                if lead.status != expected_status:
                    # Update lead
                    result = service.update_lead_from_call_result(
                        lead_id=lead.id,
                        call_status=call.call_status,
                        disposition=call.disposition_status,
                        increment_dial=False  # Don't double-count
                    )
                    
                    if result.get('success'):
                        stats['updated'] += 1
                
            except Exception as e:
                logger.error(f"Error syncing call {call.id}: {e}")
                stats['errors'] += 1
        
        if stats['updated'] > 0:
            logger.info(f"Lead status sync: {stats}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error in sync_call_log_to_lead_status: {e}", exc_info=True)
        return {'error': str(e)}


# ============================================================================
# Hopper Management Tasks
# ============================================================================

@shared_task
def fill_hopper():
    """
    Fill hopper for active campaigns
    
    Schedule: Every minute
    """
    from campaigns.models import Campaign
    from campaigns.hopper_service import HopperService
    
    try:
        for campaign in Campaign.objects.filter(status='active'):
            target = campaign.hopper_level or 100
            filled = HopperService.fill_hopper(campaign.id, target)
            
            if filled > 0:
                logger.info(f"Filled hopper for {campaign.name}: +{filled} leads")
        
        return {'success': True}
        
    except Exception as e:
        logger.error(f"Error in fill_hopper: {e}")
        return {'error': str(e)}


@shared_task
def cleanup_stale_hopper_entries():
    """
    Remove stale entries from hopper (locked for too long)
    
    Schedule: Every 5 minutes
    """
    from campaigns.hopper_service import HopperService
    
    try:
        cleaned = HopperService.cleanup_stale_entries(minutes=10)
        
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} stale hopper entries")
        
        return {'cleaned': cleaned}
        
    except Exception as e:
        logger.error(f"Error in cleanup_stale_hopper_entries: {e}")
        return {'error': str(e)}


# ============================================================================
# Recording Management
# ============================================================================

@shared_task
def sync_call_recordings():
    """
    Sync recordings from disk to database
    
    Schedule: Every 5 minutes
    """
    try:
        from telephony.recording_service import RecordingService
        
        service = RecordingService()
        synced = service.sync_recordings()
        
        if synced > 0:
            logger.info(f"Synced {synced} call recordings")
        
        return {'synced': synced}
        
    except ImportError:
        return {'error': 'RecordingService not available'}
    except Exception as e:
        logger.error(f"Error in sync_call_recordings: {e}")
        return {'error': str(e)}


@shared_task
def cleanup_old_recordings(days=90):
    """
    Clean up recordings older than specified days
    
    Schedule: Daily at 3 AM
    """
    try:
        from telephony.recording_service import RecordingService
        
        service = RecordingService()
        deleted = service.cleanup_old_recordings(days)
        
        logger.info(f"Cleaned up {deleted} old recordings")
        return {'deleted': deleted}
        
    except ImportError:
        return {'error': 'RecordingService not available'}
    except Exception as e:
        logger.error(f"Error in cleanup_old_recordings: {e}")
        return {'error': str(e)}


# ============================================================================
# Agent Session Management
# ============================================================================

@shared_task
def check_offline_agents():
    """
    Check agent registration status and mark offline if unregistered
    
    Schedule: Every 30 seconds
    """
    from users.models import AgentStatus
    from agents.models import AgentDialerSession
    
    try:
        # Get agents marked as online
        online_agents = AgentStatus.objects.exclude(status='offline').select_related('user')
        
        count_offline = 0
        
        for agent_status in online_agents:
            user = agent_status.user
            
            # Check if agent has active session
            has_session = AgentDialerSession.objects.filter(
                agent=user,
                status__in=['ready', 'connecting', 'incall']
            ).exists()
            
            if not has_session and agent_status.status != 'offline':
                # Mark offline
                agent_status.status = 'offline'
                agent_status.status_changed_at = timezone.now()
                agent_status.save()
                count_offline += 1
        
        if count_offline > 0:
            logger.info(f"Marked {count_offline} agents offline")
        
        return {'marked_offline': count_offline}
        
    except Exception as e:
        logger.error(f"Error in check_offline_agents: {e}", exc_info=True)
        return {'error': str(e)}


# ============================================================================
# System Health Monitoring
# ============================================================================

@shared_task
def monitor_system_health():
    """
    Monitor overall system health and alert on issues
    
    Schedule: Every 5 minutes
    """
    stats = {
        'campaigns_active': 0,
        'agents_online': 0,
        'calls_in_progress': 0,
        'hopper_total': 0,
        'alerts': []
    }
    
    try:
        from campaigns.models import Campaign, DialerHopper
        from users.models import AgentStatus
        from calls.models import CallLog
        
        stats['campaigns_active'] = Campaign.objects.filter(status='active').count()
        stats['agents_online'] = AgentStatus.objects.exclude(status='offline').count()
        stats['calls_in_progress'] = CallLog.objects.filter(
            call_status__in=['ringing', 'in_progress', 'answered']
        ).count()
        stats['hopper_total'] = DialerHopper.objects.filter(status='new').count()
        
        # Check for alerts
        if stats['campaigns_active'] > 0 and stats['agents_online'] == 0:
            stats['alerts'].append('Active campaigns but no agents online')
        
        if stats['hopper_total'] < 50 and stats['campaigns_active'] > 0:
            stats['alerts'].append('Low hopper count across all campaigns')
        
        if stats['alerts']:
            logger.warning(f"System health alerts: {stats['alerts']}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error in monitor_system_health: {e}")
        return {'error': str(e)}
