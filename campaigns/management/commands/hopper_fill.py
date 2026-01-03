# campaigns/management/commands/hopper_fill.py

import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, Count
from datetime import timedelta
import pytz

from campaigns.models import Campaign, DialerHopper
from leads.models import Lead, DNCEntry, LeadList

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fill hopper with eligible leads for predictive/progressive campaigns'

    def add_arguments(self, parser):
        parser.add_argument(
            '--campaign-id',
            type=int,
            help='Fill hopper for specific campaign only'
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run once and exit (default: continuous loop)'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=60,
            help='Seconds between fill cycles (default: 60)'
        )

    def handle(self, *args, **options):
        campaign_id = options.get('campaign_id')
        run_once = options.get('once')
        interval = options.get('interval', 60)

        self.stdout.write(self.style.SUCCESS('Starting Hopper Fill Service...'))

        if run_once:
            self.fill_hoppers(campaign_id)
        else:
            import time
            while True:
                try:
                    self.fill_hoppers(campaign_id)
                    time.sleep(interval)
                except KeyboardInterrupt:
                    self.stdout.write(self.style.WARNING('\\nStopping Hopper Fill Service'))
                    break
                except Exception as e:
                    logger.error(f'Hopper fill error: {e}', exc_info=True)
                    time.sleep(interval)

    def fill_hoppers(self, campaign_id=None):
        """Fill hoppers for all active campaigns"""
        # Get campaigns that need hopper filling
        campaigns = Campaign.objects.filter(
            status='active',
            dial_method__in=['progressive', 'predictive']
        )
        
        if campaign_id:
            campaigns = campaigns.filter(id=campaign_id)

        for campaign in campaigns:
            try:
                self.fill_campaign_hopper(campaign)
            except Exception as e:
                logger.error(f'Error filling hopper for {campaign.name}: {e}', exc_info=True)

    def fill_campaign_hopper(self, campaign):
        """Fill hopper for a specific campaign"""
        from campaigns.services import HopperService

        # 1. Check current hopper count in Redis
        current_count = HopperService.get_hopper_count(campaign.id)

        # 2. Calculate how many leads to add
        target = campaign.hopper_level
        max_size = campaign.hopper_size
        
        if current_count >= target:
            # logger.debug(f'{campaign.name}: Hopper OK ({current_count}/{target})')
            return

        needed = min(target - current_count, max_size - current_count)
        
        if needed <= 0:
            return

        logger.info(f'{campaign.name}: Filling hopper ({current_count}/{target}), need {needed} leads')

        # 3. Get eligible leads
        eligible_leads = self.get_eligible_leads(campaign, needed)

        # 4. Insert into Redis hopper
        if eligible_leads:
            try:
                added = HopperService.add_leads(campaign.id, eligible_leads)
                logger.info(f'{campaign.name}: Added {added} leads to Redis hopper')
            except Exception as e:
                logger.error(f'Error adding leads to Redis hopper: {e}')
        else:
            # Debug why nothing was added
            total_leads = Lead.objects.filter(lead_list__assigned_campaign=campaign).count()
            logger.warning(f'{campaign.name}: No eligible leads found for hopper fill. '
                           f'Total leads assigned to campaign: {total_leads}. '
                           f'Needed: {needed}')

    def get_eligible_leads(self, campaign, limit):
        """Get leads eligible for dialing"""
        from campaigns.services import HopperService
        
        # Get all lead lists assigned to this campaign
        from leads.models import LeadList
        lead_lists = LeadList.objects.filter(assigned_campaign=campaign)
        
        # Base query: leads in those lead lists
        leads = Lead.objects.filter(
            lead_list__in=lead_lists
        ).select_related('lead_list')

        # Filter by status
        leads = leads.filter(
            status__in=['new', 'callback']
        )

        # Filter by call attempts
        leads = leads.filter(
            call_count__lt=campaign.max_attempts
        )

        # Exclude leads already in Redis hopper or dialing
        queued_ids = HopperService.get_queued_lead_ids(campaign.id)
        # If queued_ids is large, avoid passing a huge list to exclude()
        if queued_ids and len(queued_ids) < 50000:
            leads = leads.exclude(id__in=queued_ids)

        # DNC Check
        if campaign.use_internal_dnc:
            dnc_numbers = DNCEntry.objects.values_list('phone_number', flat=True)
            leads = leads.exclude(phone_number__in=dnc_numbers)

        # Timezone Check (if enabled) – if it filters everything out, just return empty
        if campaign.local_call_time:
            leads = self.filter_by_calling_hours(leads, campaign)

        # Order by campaign preference
        if campaign.lead_order == 'down':
            leads = leads.order_by('id')
        elif campaign.lead_order == 'up':
            leads = leads.order_by('-id')
        elif campaign.lead_order == 'oldest_first':
            leads = leads.order_by('created_at')
        elif campaign.lead_order == 'newest_first':
            leads = leads.order_by('-created_at')
        elif campaign.lead_order == 'random':
            leads = leads.order_by('?')

        return leads[:limit]

    def filter_by_calling_hours(self, leads, campaign):
        """Filter leads based on timezone and calling hours"""
        now = timezone.now()
        campaign_tz = pytz.timezone(campaign.timezone)
        
        # Get current time in campaign timezone
        campaign_now = now.astimezone(campaign_tz)
        current_time = campaign_now.time()
        current_day = campaign_now.weekday()

        # Check if within campaign hours
        if current_time < campaign.daily_start_time or current_time > campaign.daily_end_time:
            # Outside calling hours, return empty queryset
            return leads.none()

        # For leads with timezone info, filter by their local time
        # This is a simplified version - full implementation would check each lead's timezone
        # For now, we'll just use campaign timezone
        return leads

    def calculate_priority(self, lead, campaign):
        """Calculate priority for lead (1-99, higher = sooner)"""
        # Base priority
        priority = 50

        # Callbacks get higher priority
        if lead.status == 'callback':
            priority = 80

        # Leads with previous contact get medium-high priority
        if lead.call_count > 0:
            priority = 60

        # Fresh leads get medium priority
        if lead.call_count == 0:
            priority = 50

        # Could add more logic here:
        # - Lead score
        # - Time since last contact
        # - Campaign-specific rules

        return min(99, max(1, priority))
