import time
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Q
from campaigns.models import Campaign, OutboundQueue
from agents.models import AgentDialerSession
from telephony.services import AsteriskService
from telephony.routing import (
    select_carrier_for_campaign,
    build_dial_number,
    build_call_variables,
)

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run the main autodialer loop'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Dialer Engine...'))
        
        while True:
            try:
                self.run_dialer_loop()
            except Exception as e:
                logger.error(f"Dialer Loop Error: {e}")
                time.sleep(1)
            time.sleep(0.1)  # Prevent CPU spike

    def run_dialer_loop(self):
        # 1. Fetch Active Campaigns
        active_campaigns = Campaign.objects.filter(status='active', is_active=True)

        for campaign in active_campaigns:
            # 2. Calculate Calls Needed
            # Formula: (Ready Agents * Ratio) - Active Ringing Calls
            
            ready_agents_count = AgentDialerSession.objects.filter(
                campaign=campaign, 
                status='ready'
            ).count()

            if ready_agents_count == 0:
                continue

            # Count calls that are currently ringing (initiated but not answered)
            # We check OutboundQueue items in 'dialing' state
            active_calls_count = OutboundQueue.objects.filter(
                campaign=campaign,
                status='dialing'
            ).count()

            target_calls = int(ready_agents_count * campaign.dial_ratio)
            calls_needed = target_calls - active_calls_count

            if calls_needed > 0:
                self.originate_calls(campaign, calls_needed)

    def originate_calls(self, campaign, count):
        # 3. Fetch Leads (Lock rows to prevent race conditions)
        with transaction.atomic():
            leads_to_dial = list(OutboundQueue.objects.select_for_update(skip_locked=True).filter(
                campaign=campaign,
                status='pending'
            ).order_by('created_at')[:count])

            if not leads_to_dial:
                return

            # Mark as dialing immediately to prevent double-dialing in next loop
            queue_ids = [q.id for q in leads_to_dial]
            OutboundQueue.objects.filter(id__in=queue_ids).update(
                status='dialing',
                last_tried_at=timezone.now()
            )

        # 4. Originate Calls via Asterisk
        from telephony.models import AsteriskServer
        server = AsteriskServer.objects.filter(is_active=True).first()
        
        if not server:
            logger.error("No active Asterisk Server found!")
            return

        svc = AsteriskService(server)

        for queue_item in leads_to_dial:
            carrier = select_carrier_for_campaign(campaign)
            target_server = carrier.asterisk_server if carrier and carrier.asterisk_server else server
            svc = AsteriskService(target_server)
            dial_number = build_dial_number(queue_item.phone_number, campaign=campaign, carrier=carrier)
            # Originate
            variables = build_call_variables(
                call_type='autodial',
                campaign=campaign,
                queue_item=queue_item,
                carrier=carrier,
            )

            # We'll use originate_local_channel to let dialplan handle carrier selection
            result = svc.originate_local_channel(
                number=dial_number,
                context='from-campaign',
                app=target_server.ari_application,  # 'autodialer'
                variables=variables,
                callerid=f"{campaign.name} <{campaign.dial_prefix or ''}>"
            )

            if not result.get('success'):
                logger.error(f"Failed to originate {queue_item.phone_number}: {result.get('error')}")
                # Revert status
                queue_item.status = 'failed'
                queue_item.save()
