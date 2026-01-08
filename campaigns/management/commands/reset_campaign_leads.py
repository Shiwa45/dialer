from django.core.management.base import BaseCommand, CommandError
from campaigns.models import Campaign
from leads.models import Lead, LeadList

class Command(BaseCommand):
    help = 'Reset all leads in a campaign to "new" status and 0 call count for re-testing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--campaign',
            required=True,
            help='Campaign ID or Name',
        )

    def handle(self, *args, **options):
        identifier = options['campaign']
        
        # Resolve Campaign
        if identifier.isdigit():
            campaign = Campaign.objects.filter(id=int(identifier)).first()
        else:
            campaign = Campaign.objects.filter(name__iexact=identifier).first()
            
        if not campaign:
            raise CommandError(f"Campaign '{identifier}' not found.")
            
        self.stdout.write(f"Resetting leads for campaign: {campaign.name}")
        
        # Get Lead Lists
        lead_lists = LeadList.objects.filter(assigned_campaign=campaign)
        if not lead_lists.exists():
            self.stdout.write(self.style.WARNING("No lead lists assigned to this campaign."))
            return

        # Reset Leads
        leads = Lead.objects.filter(lead_list__in=lead_lists)
        count = leads.count()
        
        updated = leads.update(
            status='new',
            call_count=0,
            agent_assigned=None,  # Clear agent assignment if any
            last_contact_date=None
        )
        
        # Also clear any Redis hopper keys if possible? 
        # For now, just DB reset is usually enough as hopper checks DB.
        # But if leads are in Redis but marked 'new' in DB, they might be re-added? 
        # Hopper logic excludes IDs in Redis. So existing Redis items will dial. 
        # New items will be added.
        
        try:
            from campaigns.services import HopperService
            HopperService.clear_hopper(campaign.id)
            self.stdout.write("Cleared Redis hopper.")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not clear Redis hopper: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Successfully reset {updated} leads in {count} total rows."))
