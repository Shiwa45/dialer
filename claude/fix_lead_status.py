"""
Management Command: Fix Leads Missing Status - Phase 2.1

Usage:
    python manage.py fix_lead_status
    python manage.py fix_lead_status --campaign=123
    python manage.py fix_lead_status --dry-run
    python manage.py fix_lead_status --report-only
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from leads.lead_status_service import get_lead_status_service


class Command(BaseCommand):
    help = 'Fix leads with missing or incorrect status based on call history'

    def add_arguments(self, parser):
        parser.add_argument(
            '--campaign',
            type=int,
            help='Fix leads for specific campaign ID only'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes'
        )
        
        parser.add_argument(
            '--report-only',
            action='store_true',
            help='Only report problems without fixing'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output'
        )

    def handle(self, *args, **options):
        campaign_id = options.get('campaign')
        dry_run = options.get('dry_run')
        report_only = options.get('report_only')
        verbose = options.get('verbose')
        
        service = get_lead_status_service()
        
        self.stdout.write(self.style.SUCCESS('='*70))
        self.stdout.write(self.style.SUCCESS('Lead Status Fix - Phase 2.1'))
        self.stdout.write(self.style.SUCCESS('='*70))
        
        if campaign_id:
            self.stdout.write(f'Campaign ID: {campaign_id}')
        else:
            self.stdout.write('Scope: All campaigns')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        self.stdout.write('')
        
        # Step 1: Find problematic leads
        self.stdout.write(self.style.SUCCESS('Step 1: Analyzing leads...'))
        
        issues = service.find_leads_with_missing_status(campaign_id=campaign_id)
        
        if 'error' in issues:
            self.stdout.write(self.style.ERROR(f'Error: {issues["error"]}'))
            return
        
        self.stdout.write(f'  Leads with dial attempts but status "new": {issues["dialed_but_new"]}')
        self.stdout.write(f'  Leads with calls but missing dial tracking: {issues["missing_dial_tracking"]}')
        self.stdout.write(f'  Total issues found: {issues["total_issues"]}')
        
        if verbose and issues.get('dialed_but_new_ids'):
            self.stdout.write(f'  Sample lead IDs (dialed but new): {issues["dialed_but_new_ids"][:10]}')
        
        if verbose and issues.get('missing_dial_tracking_ids'):
            self.stdout.write(f'  Sample lead IDs (missing tracking): {issues["missing_dial_tracking_ids"][:10]}')
        
        self.stdout.write('')
        
        if issues['total_issues'] == 0:
            self.stdout.write(self.style.SUCCESS('✅ No issues found! All leads have proper status tracking.'))
            return
        
        if report_only:
            self.stdout.write(self.style.WARNING('Report-only mode. Use without --report-only to fix issues.'))
            return
        
        # Step 2: Fix issues
        self.stdout.write(self.style.SUCCESS('Step 2: Fixing issues...'))
        
        result = service.fix_leads_with_missing_status(
            campaign_id=campaign_id,
            dry_run=dry_run
        )
        
        if 'error' in result:
            self.stdout.write(self.style.ERROR(f'Error: {result["error"]}'))
            return
        
        self.stdout.write(f'  Leads checked: {result["leads_checked"]}')
        self.stdout.write(f'  Leads fixed: {result["leads_fixed"]}')
        self.stdout.write(f'  Errors: {result["errors"]}')
        
        if result['status_assigned']:
            self.stdout.write('')
            self.stdout.write('  Status distribution after fix:')
            for status, count in sorted(result['status_assigned'].items(), key=lambda x: -x[1]):
                self.stdout.write(f'    {status}: {count}')
        
        self.stdout.write('')
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                '⚠️  DRY RUN completed. Run without --dry-run to apply fixes.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'✅ Successfully fixed {result["leads_fixed"]} leads!'
            ))
        
        # Step 3: Recommendations
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Recommendations:'))
        self.stdout.write('  1. Run this command periodically (e.g., daily via cron)')
        self.stdout.write('  2. Ensure CallLog always updates Lead status on call end')
        self.stdout.write('  3. Monitor leads with high dial_attempts but no answers')
        self.stdout.write('  4. Review lead recycling rules for optimal retry strategy')
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('='*70))
