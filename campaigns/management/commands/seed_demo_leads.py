from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction

from campaigns.models import Campaign, OutboundQueue
from leads.models import Lead, LeadList


class Command(BaseCommand):
    help = "Create repeated demo leads and queue items for a campaign so autodial can start immediately."

    def add_arguments(self, parser):
        parser.add_argument(
            "--campaign",
            required=True,
            help="Campaign name, campaign_id, or numeric ID (e.g. 'Demo Campaign').",
        )
        parser.add_argument(
            "--phone",
            required=True,
            help="Phone number to enqueue (e.g. 9625050463).",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=5,
            help="How many duplicate leads/queue rows to create (default: 5).",
        )
        parser.add_argument(
            "--lead-list",
            default="Demo Lead List",
            help="Name of the lead list to attach the demo leads to (default: Demo Lead List).",
        )
        parser.add_argument(
            "--status",
            default="new",
            help="Lead status to use for the generated leads (default: new).",
        )

    def handle(self, *args, **options):
        campaign_identifier = options["campaign"]
        phone_number = options["phone"]
        count = max(1, options["count"])
        lead_list_name = options["lead_list"]
        lead_status = options["status"]

        campaign = self._resolve_campaign(campaign_identifier)
        if not campaign:
            raise CommandError(f"Campaign '{campaign_identifier}' not found.")

        owner = campaign.created_by or self._fallback_user()
        if not owner:
            raise CommandError("Unable to determine a user to own the lead list (no users exist).")

        lead_list, _ = LeadList.objects.get_or_create(
            name=lead_list_name,
            defaults={"created_by": owner},
        )

        created_leads = []
        with transaction.atomic():
            for idx in range(count):
                lead = Lead.objects.create(
                    first_name=f"Demo{idx + 1}",
                    last_name="Lead",
                    phone_number=phone_number,
                    status=lead_status,
                    lead_list=lead_list,
                    source="Autodial Demo Seed",
                )
                OutboundQueue.objects.create(
                    campaign=campaign,
                    lead=lead,
                    phone_number=phone_number,
                )
                created_leads.append(lead.id)

        self.stdout.write(
            self.style.SUCCESS(
                f"Queued {len(created_leads)} demo leads for campaign '{campaign.name}'."
            )
        )
        self.stdout.write(f"Phone number: {phone_number}")
        self.stdout.write(f"Lead IDs: {created_leads}")

    def _resolve_campaign(self, identifier):
        qs = Campaign.objects.all()
        campaign = qs.filter(name__iexact=identifier).first()
        if campaign:
            return campaign
        campaign = qs.filter(campaign_id=identifier).first()
        if campaign:
            return campaign
        if identifier.isdigit():
            campaign = qs.filter(id=int(identifier)).first()
        return campaign

    def _fallback_user(self):
        User = get_user_model()
        return (
            User.objects.filter(is_superuser=True).first()
            or User.objects.filter(is_staff=True).first()
            or User.objects.first()
        )
