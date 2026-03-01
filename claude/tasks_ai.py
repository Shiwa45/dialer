"""
campaigns/tasks_ai.py – Phase 8.3: AI Agent Celery Tasks
==========================================================

Celery tasks for AI agent calls.

ADD TO YOUR campaigns/tasks.py OR CREATE NEW FILE
"""

import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def make_ai_outbound_call(self, lead_id: int, campaign_id: int):
    """
    Make an outbound AI call to a lead.
    
    This task:
    1. Validates lead and campaign
    2. Checks if AI is enabled
    3. Originates call via Asterisk
    4. Call enters Stasis → AI handler takes over
    
    Args:
        lead_id: Lead ID to call
        campaign_id: Campaign ID
    
    Returns:
        dict: {'success': True, 'call_id': ...} or error
    """
    from leads.models import Lead
    from campaigns.models import Campaign
    from calls.models import CallLog
    from telephony.services import AsteriskService
    from telephony.models import AsteriskServer
    
    try:
        # 1. Get lead and campaign
        lead = Lead.objects.get(id=lead_id)
        campaign = Campaign.objects.get(id=campaign_id)
        
        # 2. Validate
        if not campaign.ai_enabled:
            logger.warning(f"Campaign {campaign_id} AI not enabled")
            return {
                'success': False,
                'error': 'AI not enabled for this campaign'
            }
        
        if not lead.phone_number:
            logger.warning(f"Lead {lead_id} has no phone number")
            return {
                'success': False,
                'error': 'Lead has no phone number'
            }
        
        # 3. Create call log
        call_log = CallLog.objects.create(
            campaign=campaign,
            lead=lead,
            called_number=lead.phone_number,
            call_type='outbound',
            call_status='initiated',
            handled_by_ai=True,
        )
        
        logger.info(f"AI call initiated: call_log={call_log.id}, "
                   f"lead={lead_id}, campaign={campaign_id}")
        
        # 4. Get Asterisk server
        server = AsteriskServer.objects.filter(is_active=True).first()
        if not server:
            call_log.call_status = 'failed'
            call_log.save()
            return {
                'success': False,
                'error': 'No active Asterisk server'
            }
        
        # 5. Originate call
        asterisk = AsteriskService(server)
        
        # Find carrier/trunk for this number
        # You may need to adjust this based on your routing logic
        carrier_string = f'PJSIP/{lead.phone_number}@carrier'  # Adjust as needed
        
        # Originate call and send to Stasis app
        result = asterisk.originate_call(
            endpoint=carrier_string,
            app='autodialer',
            app_args=[
                'ai_call',  # call_type
                str(campaign_id),
                str(lead_id),
                campaign.ai_language,  # Pass language
            ],
            caller_id=campaign.caller_id or 'AI Agent',
            timeout=30,
            variables={
                'CALL_TYPE': 'ai_call',
                'CAMPAIGN_ID': str(campaign_id),
                'LEAD_ID': str(lead_id),
                'AI_LANGUAGE': campaign.ai_language,
                'AI_ENABLED': '1',
            }
        )
        
        if result.get('success'):
            call_log.channel_id = result.get('channel_id')
            call_log.call_status = 'ringing'
            call_log.save()
            
            logger.info(f"AI call originated: channel={result.get('channel_id')}")
            
            return {
                'success': True,
                'call_id': call_log.id,
                'channel_id': result.get('channel_id'),
            }
        else:
            call_log.call_status = 'failed'
            call_log.save()
            
            return {
                'success': False,
                'error': result.get('error', 'Origination failed')
            }
    
    except Lead.DoesNotExist:
        logger.error(f"Lead {lead_id} not found")
        return {'success': False, 'error': 'Lead not found'}
    
    except Campaign.DoesNotExist:
        logger.error(f"Campaign {campaign_id} not found")
        return {'success': False, 'error': 'Campaign not found'}
    
    except Exception as e:
        logger.error(f"AI call task error: {e}", exc_info=True)
        
        # Retry on failure
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60)
        
        return {'success': False, 'error': str(e)}


@shared_task
def process_ai_call_queue(campaign_id: int, max_calls: int = 10):
    """
    Process AI call queue for a campaign.
    
    Finds leads ready to be called and queues AI calls.
    
    Args:
        campaign_id: Campaign ID
        max_calls: Maximum number of calls to queue
    
    Returns:
        dict: {'queued': 5, 'skipped': 2}
    """
    from campaigns.models import Campaign
    from leads.models import Lead
    
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        
        if not campaign.ai_enabled:
            logger.warning(f"Campaign {campaign_id} AI not enabled")
            return {'queued': 0, 'skipped': 0}
        
        # Find leads to call
        # Adjust this query based on your lead status logic
        leads_to_call = Lead.objects.filter(
            status__in=['new', 'callback', 'retry'],
            phone_number__isnull=False,
        ).exclude(
            phone_number=''
        )[:max_calls]
        
        queued = 0
        skipped = 0
        
        for lead in leads_to_call:
            # Check if already called recently
            from calls.models import CallLog
            from datetime import timedelta
            
            recent_call = CallLog.objects.filter(
                lead=lead,
                start_time__gte=timezone.now() - timedelta(hours=24),
            ).exists()
            
            if recent_call:
                skipped += 1
                continue
            
            # Queue AI call
            make_ai_outbound_call.delay(
                lead_id=lead.id,
                campaign_id=campaign_id,
            )
            
            queued += 1
            
            # Update lead status
            lead.status = 'dialing'
            lead.save()
        
        logger.info(f"AI call queue processed: campaign={campaign_id}, "
                   f"queued={queued}, skipped={skipped}")
        
        return {'queued': queued, 'skipped': skipped}
    
    except Exception as e:
        logger.error(f"AI call queue error: {e}", exc_info=True)
        return {'queued': 0, 'skipped': 0, 'error': str(e)}


# ══════════════════════════════════════════════════════════════════════
# ADD TO YOUR settings.py CELERY_BEAT_SCHEDULE:
# ══════════════════════════════════════════════════════════════════════

"""
CELERY_BEAT_SCHEDULE = {
    # ... existing tasks ...
    
    # Phase 8: AI call queue processing
    'process-ai-call-queues': {
        'task': 'campaigns.tasks.process_ai_call_queue',
        'schedule': 60.0,  # Every 60 seconds
        'kwargs': {
            'campaign_id': 1,  # Set your campaign ID
            'max_calls': 10,
        }
    },
}
"""
