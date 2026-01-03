# campaigns/management/commands/predictive_dialer.py

import logging
import time
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, Count

from campaigns.models import Campaign, DialerHopper
from users.models import AgentStatus
from agents.models import AgentDialerSession
from telephony.models import AsteriskServer
from telephony.services import AsteriskService
from calls.models import CallLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Predictive dialing engine - originates calls based on agent availability'

    def add_arguments(self, parser):
        parser.add_argument(
            '--campaign-id',
            type=int,
            help='Dial for specific campaign only'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=3,
            help='Seconds between dial cycles (default: 3)'
        )
        parser.add_argument(
            '--test-mode',
            action='store_true',
            help='Test mode: log actions without actually dialing'
        )

    def handle(self, *args, **options):
        campaign_id = options.get('campaign_id')
        interval = options.get('interval', 3)
        test_mode = options.get('test_mode', False)

        self.stdout.write(self.style.SUCCESS('Starting Predictive Dialer Engine...'))
        if test_mode:
            self.stdout.write(self.style.WARNING('TEST MODE: No actual calls will be placed'))

        while True:
            try:
                self.dial_cycle(campaign_id, test_mode)
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('\\nStopping Predictive Dialer'))
                break
            except Exception as e:
                logger.error(f'Dialer error: {e}', exc_info=True)
                time.sleep(interval)

    def dial_cycle(self, campaign_id=None, test_mode=False):
        """Execute one dial cycle for all active campaigns"""
        # Get active campaigns
        campaigns = Campaign.objects.filter(
            status='active',
            dial_method__in=['progressive', 'predictive']
        )
        
        if campaign_id:
            campaigns = campaigns.filter(id=campaign_id)

        for campaign in campaigns:
            try:
                # **CRITICAL: Clean up stuck leads before dialing**
                # This prevents leads from staying in dialing set forever when calls fail
                self.cleanup_stuck_leads(campaign)
                
                self.dial_campaign(campaign, test_mode)
            except Exception as e:
                logger.error(f'Error dialing campaign {campaign.name}: {e}', exc_info=True)
    
    def cleanup_stuck_leads(self, campaign):
        """
        Remove leads from dialing set that have been there too long
        This handles cases where calls fail but cleanup doesn't happen
        
        Strategy: Use Redis timestamps to track when leads were added
        If no timestamp exists, assume it's stuck and remove it
        """
        from campaigns.services import HopperService
        import time
        
        r = HopperService.get_redis()
        dialing_key = f"campaign:{campaign.id}:dialing"
        timestamp_key = f"campaign:{campaign.id}:dialing_timestamps"
        
        # Get all leads currently in dialing set
        dialing_leads = r.smembers(dialing_key)
        
        if not dialing_leads:
            return
        
        current_time = int(time.time())
        timeout_seconds = 30  # 30 seconds timeout (fast recovery)
        
        # Check each lead
        cleaned = 0
        for lead_id_bytes in dialing_leads:
            lead_id = int(lead_id_bytes)
            
            # Get timestamp when this lead was added to dialing set
            timestamp = r.hget(timestamp_key, lead_id)
            
            if timestamp is None:
                # No timestamp found - this is stuck, remove it
                r.srem(dialing_key, lead_id)
                cleaned += 1
                logger.info(f"Cleaned stuck lead {lead_id} (no timestamp)")
            else:
                # Check if it's been too long
                lead_time = int(timestamp)
                age = current_time - lead_time
                
                if age > timeout_seconds:
                    # Lead has been dialing for > 30 seconds, remove it
                    r.srem(dialing_key, lead_id)
                    r.hdel(timestamp_key, lead_id)
                    cleaned += 1
                    logger.info(f"Cleaned stuck lead {lead_id} (timeout: {age}s)")
        
        if cleaned > 0:
            logger.info(f"{campaign.name}: Cleaned {cleaned} stuck leads from dialing set")

    def dial_campaign(self, campaign, test_mode=False):
        """Execute dialing for a specific campaign"""
        from campaigns.services import HopperService
        
        # 1. Count available agents for this campaign
        available_agents = self.get_available_agents(campaign)
        
        if available_agents == 0:
            logger.info(f'{campaign.name}: No available agents')
            return

        # 2. Count current active calls for this campaign (Redis)
        active_calls = HopperService.get_active_call_count(campaign.id)

        # 3. Calculate how many calls to place
        dial_count = self.calculate_dial_count(
            campaign, 
            available_agents, 
            active_calls
        )

        if dial_count <= 0:
            logger.info(f'{campaign.name}: IDLE - Agents={available_agents}, Active={active_calls}, Needed={dial_count}')
            return

        logger.info(f'{campaign.name}: Dialing {dial_count} calls (agents={available_agents}, active={active_calls})')

        # 4. Get leads from hopper (Redis)
        leads = HopperService.get_next_leads(campaign.id, count=dial_count)
        logger.info(f"Fetched {len(leads)} leads from hopper")

        # 5. Originate calls
        for lead_data in leads:
            try:
                self.originate_call(campaign, lead_data, test_mode)
            except Exception as e:
                logger.error(f'Error originating call for lead {lead_data.get("id")}: {e}')

    def get_available_agents(self, campaign):
        """
        Count agents available for this campaign
        
        Enhanced to consider:
        1. Agent status (ready)
        2. Campaign assignment
        3. Agent session state
        4. Recent activity
        5. **Softphone registration status**
        """
        # Agents must be:
        # 1. Logged into this campaign (AgentDialerSession)
        # 2. Status = 'ready' (ready to take calls)
        # 3. Not in wrapup timeout
        # 4. **Softphone must be registered**
        
        from django.utils import timezone
        from datetime import timedelta
        from agents.telephony_service import AgentTelephonyService
        
        # Get all ready sessions for this campaign
        ready_sessions = AgentDialerSession.objects.filter(
            campaign=campaign,
            status='ready'
        )
        
        # Filter out agents still in wrapup (if wrapup_timeout is set)
        available_count = 0
        for session in ready_sessions:
            # Check if agent status is actually ready
            agent_status = getattr(session.agent, 'agent_status', None)
            if not agent_status or agent_status.status != 'available':
                continue
            
            # **CRITICAL: Check if softphone is registered**
            telephony_service = AgentTelephonyService(session.agent)
            if not telephony_service.is_extension_registered():
                logger.warning(
                    f"Agent {session.agent.username} marked as ready but softphone not registered. "
                    f"Skipping from available count."
                )
                continue
            
            # Check if agent is past wrapup timeout
            if campaign.wrapup_timeout > 0 and session.last_call_end:
                wrapup_end = session.last_call_end + timedelta(seconds=campaign.wrapup_timeout)
                if timezone.now() < wrapup_end:
                    continue
            
            available_count += 1
        
        return available_count

    def calculate_dial_count(self, campaign, available_agents, active_calls):
        """
        Calculate how many calls to place.
        Simplified: always target available_agents * dial_level, capped by max_lines.
        We are intentionally skipping drop-rate throttling here to ensure calls are placed.
        """
        dial_level = float(campaign.dial_level)
        if dial_level < 1.0:
            dial_level = 1.0
        target_calls = int(available_agents * dial_level)
        needed = target_calls - active_calls
        # Do not cap by max_lines here; let Asterisk trunk limits handle hard caps
        return max(0, needed)

    def originate_call(self, campaign, lead_data, test_mode=False):
        """Originate a call for a hopper entry"""
        from campaigns.services import HopperService
        
        # Get Asterisk server
        server = AsteriskServer.objects.filter(is_active=True).first()
        if not server:
            logger.error('No active Asterisk server found')
            return

        lead_id = int(lead_data['id'])
        phone_number = lead_data['phone_number']

        # Increment call count to prevent infinite loop
        from leads.models import Lead
        try:
            lead = Lead.objects.get(id=lead_id)
            lead.call_count += 1
            lead.save(update_fields=['call_count'])
        except Lead.DoesNotExist:
            logger.error(f'Lead {lead_id} does not exist')
            return

        # Register dialing in Redis
        HopperService.register_dialing(campaign.id, lead_id)
        
        # Track timestamp for timeout-based cleanup
        import time
        r = HopperService.get_redis()
        timestamp_key = f"campaign:{campaign.id}:dialing_timestamps"
        r.hset(timestamp_key, lead_id, int(time.time()))
        
        if test_mode:
            logger.info(f'TEST: Would dial {phone_number} for lead {lead_id}')
            # Immediately unregister since we aren't really dialing
            HopperService.unregister_dialing(campaign.id, lead_id)
            return

        # Prepare dial string
        # Use campaign dial_prefix if configured
        dial_number = phone_number
        if campaign.dial_prefix:
            dial_number = f"{campaign.dial_prefix}{phone_number}"

        # Originate call via ARI
        service = AsteriskService(server)
        
        try:
            # Prepare channel variables
            variables = {
                'CALL_TYPE': 'autodial',
                'CAMPAIGN_ID': str(campaign.id),
                'LEAD_ID': str(lead_id),
                'CUSTOMER_NUMBER': phone_number,
            }
            
            # Pass hopper id if we have it (for legacy DB tracking)
            hopper_id = lead_data.get('hopper_id')
            if hopper_id:
                variables['HOPPER_ID'] = str(hopper_id)
            
            # Add AMD variables if enabled
            if campaign.amd_enabled:
                variables.update({
                    'AMD_ENABLED': '1',
                    'AMD_SILENCE': '2500',      # Initial silence (ms)
                    'AMD_AFTER_GREETING_SILENCE': '800',  # After greeting silence
                    'AMD_TOTAL_ANALYSIS_TIME': '5000',    # Total analysis time
                    'AMD_MIN_WORD_LENGTH': '100',         # Minimum word length
                    'AMD_BETWEEN_WORDS_SILENCE': '50',    # Between words silence
                    'AMD_MAXIMUM_NUMBER_OF_WORDS': '3',   # Max words
                    'AMD_MAXIMUM_WORD_LENGTH': '5000',    # Max word length
                })
            
            # Originate to Local channel that goes through dialplan (_X. in from-campaign hits AMD/Stasis)
            result = service.originate_local_channel(
                number=dial_number,
                context='from-campaign',
                callerid=f"Campaign {campaign.name}",
                variables=variables
            )

            if result.get('success'):
                channel_id = result.get('channel_id')
                
                # Create call log
                CallLog.objects.create(
                    channel=channel_id,
                    call_type='outbound',
                    call_status='initiated',
                    called_number=phone_number,
                    campaign=campaign,
                    lead_id=lead_id, 
                    start_time=timezone.now()
                )
                
                logger.info(f'Originated call {channel_id} for {phone_number} (call_count={lead.call_count})')
            else:
                logger.error(f'Failed to originate call: {result.get("error")}')
                HopperService.unregister_dialing(campaign.id, lead_id)

        except Exception as e:
            logger.error(f'Exception originating call: {e}', exc_info=True)
            HopperService.unregister_dialing(campaign.id, lead_id)
