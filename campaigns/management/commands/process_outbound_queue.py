from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q

from campaigns.models import OutboundQueue, Campaign, CampaignCarrier
from agents.models import AgentDialerSession
from telephony.services import AsteriskService
from telephony.routing import (
    select_carrier_for_campaign,
    build_dial_number,
    build_call_variables,
)

class Command(BaseCommand):
    help = 'Process outbound queue: originate customer legs to ready agents (basic POC)'

    def add_arguments(self, parser):
        parser.add_argument('--campaign-id', type=int, help='Limit to a specific campaign id')

    def handle(self, *args, **options):
        qs = OutboundQueue.objects.filter(status='pending')
        if options.get('campaign_id'):
            qs = qs.filter(campaign_id=options['campaign_id'])
        # Find one ready agent session per campaign
        for item in qs.order_by('created_at')[:20]:
            session = AgentDialerSession.objects.filter(
                campaign=item.campaign,
                status='ready'
            ).order_by('created_at').first()
            if not session:
                continue
            carrier = select_carrier_for_campaign(item.campaign)
            target_server = carrier.asterisk_server if carrier else session.asterisk_server
            service = AsteriskService(target_server)
            # Originate via Local into from-campaign; dialplan selects carrier by prefix
            number_to_dial = build_dial_number(item.phone_number, campaign=item.campaign, carrier=carrier)
            variables = build_call_variables(
                call_type='customer_leg',
                campaign=item.campaign,
                queue_item=item,
                carrier=carrier,
            )
            res = service.originate_local_channel(
                number=number_to_dial,
                context='from-campaign',
                app='autodialer',
                callerid=f"OUT {item.phone_number}",
                variables=variables,
            )
            if res.get('success'):
                item.status = 'dialing'
                item.attempts += 1
                item.last_tried_at = timezone.now()
                item.save()
                self.stdout.write(self.style.SUCCESS(f"Dialing {item.phone_number} for {item.campaign.name}"))
            else:
                item.status = 'failed'
                item.attempts += 1
                item.last_tried_at = timezone.now()
                item.save()
                self.stderr.write(f"Failed to originate {item.phone_number}: {res.get('error')}")
