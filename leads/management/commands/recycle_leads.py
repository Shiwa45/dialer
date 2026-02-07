"""
Lead Recycling Management Command - Phase 2.4

This command processes lead recycle rules and recycles eligible leads.
Run this command periodically via cron or Celery Beat.

Usage:
    python manage.py recycle_leads
    python manage.py recycle_leads --dry-run
    python manage.py recycle_leads --rule-id=1
"""

import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process lead recycle rules and recycle eligible leads'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be recycled without making changes'
        )
        parser.add_argument(
            '--rule-id',
            type=int,
            help='Process only a specific rule by ID'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output'
        )

    def handle(self, *args, **options):
        from leads.models import LeadRecycleRule, LeadRecycleLog, Lead
        
        dry_run = options.get('dry_run', False)
        rule_id = options.get('rule_id')
        verbose = options.get('verbose', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get active rules
        rules = LeadRecycleRule.objects.filter(is_active=True)
        if rule_id:
            rules = rules.filter(id=rule_id)
        
        if not rules.exists():
            self.stdout.write(self.style.WARNING('No active recycle rules found'))
            return
        
        total_recycled = 0
        
        for rule in rules:
            # Check if rule is currently active (time-based)
            if not rule.is_currently_active():
                if verbose:
                    self.stdout.write(f"  Skipping rule '{rule.name}' - not active at current time")
                continue
            
            self.stdout.write(f"\nProcessing rule: {rule.name}")
            self.stdout.write(f"  Source status: {rule.source_status}")
            self.stdout.write(f"  Target status: {rule.target_status}")
            self.stdout.write(f"  Recycle after: {rule.recycle_after_hours} hours")
            self.stdout.write(f"  Max attempts: {rule.max_attempts}")
            
            # Get eligible leads
            eligible_leads = rule.get_eligible_leads()
            count = eligible_leads.count()
            
            self.stdout.write(f"  Eligible leads: {count}")
            
            if count == 0:
                continue
            
            if dry_run:
                # Show sample of leads that would be recycled
                sample_leads = eligible_leads[:5]
                for lead in sample_leads:
                    self.stdout.write(
                        f"    Would recycle: {lead.id} - {lead.first_name} {lead.last_name} "
                        f"({lead.phone_number}) - Calls: {lead.call_count}"
                    )
                if count > 5:
                    self.stdout.write(f"    ... and {count - 5} more")
                continue
            
            # Recycle leads
            recycled_count = self._recycle_leads(rule, eligible_leads, verbose)
            total_recycled += recycled_count
            
            # Update rule statistics
            rule.last_run = timezone.now()
            rule.total_recycled += recycled_count
            rule.save(update_fields=['last_run', 'total_recycled'])
            
            self.stdout.write(self.style.SUCCESS(f"  Recycled: {recycled_count} leads"))
        
        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN: Would have recycled {total_recycled} leads'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Total recycled: {total_recycled} leads'))

    def _recycle_leads(self, rule, leads, verbose=False):
        """
        Recycle leads according to rule
        
        Args:
            rule: LeadRecycleRule instance
            leads: QuerySet of Lead objects
            verbose: Show detailed output
        
        Returns:
            int: Number of leads recycled
        """
        from leads.models import LeadRecycleLog
        
        recycled_count = 0
        
        for lead in leads:
            try:
                with transaction.atomic():
                    # Create log entry
                    LeadRecycleLog.objects.create(
                        rule=rule,
                        lead=lead,
                        old_status=lead.status,
                        new_status=rule.target_status,
                        old_call_count=lead.call_count
                    )
                    
                    # Update lead
                    lead.status = rule.target_status
                    
                    # Adjust priority if configured
                    if rule.priority_adjustment != 0:
                        current_priority = getattr(lead, 'priority', 'medium')
                        # Simple priority adjustment logic
                        priorities = ['low', 'medium', 'high']
                        try:
                            idx = priorities.index(current_priority)
                            new_idx = max(0, min(2, idx + rule.priority_adjustment))
                            lead.priority = priorities[new_idx]
                        except (ValueError, IndexError):
                            pass
                    
                    lead.save(update_fields=['status', 'priority'])
                    
                    recycled_count += 1
                    
                    if verbose:
                        self.stdout.write(
                            f"    Recycled: {lead.id} - {lead.phone_number} "
                            f"({rule.source_status} → {rule.target_status})"
                        )
                    
            except Exception as e:
                logger.error(f"Error recycling lead {lead.id}: {e}")
                self.stdout.write(
                    self.style.ERROR(f"    Error recycling lead {lead.id}: {e}")
                )
        
        return recycled_count
