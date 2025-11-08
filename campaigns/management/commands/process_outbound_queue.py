from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q

from campaigns.models import OutboundQueue, Campaign, CampaignCarrier
from agents.models import AgentDialerSession
from telephony.services import AsteriskService

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
            service = AsteriskService(session.asterisk_server)
            # Originate via Local into from-campaign; dialplan selects carrier by prefix
            number_to_dial = f"{item.campaign.dial_prefix}{item.phone_number}" if item.campaign.dial_prefix else item.phone_number
            res = service.originate_local_channel(
                number=number_to_dial,
                context='from-campaign',
                app='autodialer',
                callerid=f"OUT {item.phone_number}",
                variables={'CALL_TYPE': 'customer_leg', 'BRIDGE_ID': session.agent_bridge_id, 'QUEUE_ID': str(item.id)}
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
