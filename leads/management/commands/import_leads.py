# leads/management/commands/import_leads.py

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from leads.models import LeadList, LeadImport
from leads.utils import LeadImportProcessor
import os


class Command(BaseCommand):
    help = 'Import leads from CSV or Excel file'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the import file')
        parser.add_argument('--lead-list', type=str, required=True, help='Lead list name or ID')
        parser.add_argument('--user', type=str, required=True, help='Username of importing user')
        parser.add_argument('--skip-duplicates', action='store_true', help='Skip duplicate phone numbers')
        parser.add_argument('--check-dnc', action='store_true', help='Check against DNC list')
        parser.add_argument('--dry-run', action='store_true', help='Validate file without importing')

    def handle(self, *args, **options):
        file_path = options['file_path']
        
        # Validate file exists
        if not os.path.exists(file_path):
            raise CommandError(f'File does not exist: {file_path}')
        
        # Get user
        try:
            user = User.objects.get(username=options['user'])
        except User.DoesNotExist:
            raise CommandError(f'User does not exist: {options["user"]}')
        
        # Get or create lead list
        lead_list_name = options['lead_list']
        try:
            if lead_list_name.isdigit():
                lead_list = LeadList.objects.get(id=int(lead_list_name))
            else:
                lead_list, created = LeadList.objects.get_or_create(
                    name=lead_list_name,
                    defaults={'created_by': user, 'is_active': True}
                )
                if created:
                    self.stdout.write(f'Created new lead list: {lead_list_name}')
        except LeadList.DoesNotExist:
            raise CommandError(f'Lead list does not exist: {lead_list_name}')
        
        if options['dry_run']:
            self.stdout.write('Dry run mode - validating file...')
            # Validate file format and structure
            from leads.utils import parse_csv_file, parse_excel_file
            
            if file_path.endswith('.csv'):
                success, result = parse_csv_file(file_path)
            else:
                success, result = parse_excel_file(file_path)
            
            if success:
                self.stdout.write(self.style.SUCCESS(f'File validation successful'))
                self.stdout.write(f'Headers found: {result["headers"]}')
                self.stdout.write(f'Sample rows: {len(result.get("sample_data", []))}')
            else:
                raise CommandError(f'File validation failed: {result}')
            return
        
        # Create import record
        import_name = f'Command Import - {os.path.basename(file_path)}'
        
        # Create a temporary file field
        from django.core.files import File
        with open(file_path, 'rb') as f:
            lead_import = LeadImport.objects.create(
                name=import_name,
                user=user,
                lead_list=lead_list,
                skip_duplicates=options['skip_duplicates'],
                check_dnc=options['check_dnc'],
                status='pending'
            )
            lead_import.file.save(os.path.basename(file_path), File(f))
        
        self.stdout.write(f'Starting import: {import_name}')
        
        try:
            # Process import
            processor = LeadImportProcessor(lead_import)
            processor.process()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Import completed successfully!\n'
                    f'Processed: {processor.processed_count}\n'
                    f'Successful: {processor.success_count}\n'
                    f'Failed: {processor.error_count}\n'
                    f'Duplicates: {processor.duplicate_count}'
                )
            )
            
            if processor.errors:
                self.stdout.write(self.style.WARNING('Errors encountered:'))
                for error in processor.errors[:10]:  # Show first 10 errors
                    self.stdout.write(f'  - {error}')
                if len(processor.errors) > 10:
                    self.stdout.write(f'  ... and {len(processor.errors) - 10} more errors')
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Import failed: {str(e)}'))
            raise CommandError(f'Import failed: {str(e)}')


# leads/management/commands/cleanup_leads.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from leads.models import Lead, LeadImport, DNCEntry
from leads.utils import cleanup_old_data


class Command(BaseCommand):
    help = 'Clean up old lead data and files'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30, help='Days to keep data (default: 30)')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without deleting')
        parser.add_argument('--force', action='store_true', help='Force deletion without confirmation')

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        force = options['force']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Find old imports
        old_imports = LeadImport.objects.filter(created_at__lt=cutoff_date)
        
        # Find leads with no activity
        inactive_leads = Lead.objects.filter(
            created_at__lt=cutoff_date,
            last_contact_date__isnull=True,
            status='new'
        )
        
        self.stdout.write(f'Cleanup summary (older than {days} days):')
        self.stdout.write(f'  - Import records: {old_imports.count()}')
        self.stdout.write(f'  - Inactive leads: {inactive_leads.count()}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No data will be deleted'))
            return
        
        if not force:
            confirm = input('Are you sure you want to delete this data? [y/N]: ')
            if confirm.lower() != 'y':
                self.stdout.write('Cleanup cancelled')
                return
        
        # Perform cleanup
        result = cleanup_old_data()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Cleanup completed:\n'
                f'  - Files deleted: {result["deleted_files"]}\n'
                f'  - Import records deleted: {result["deleted_imports"]}\n'
                f'  - Notes cleaned: {result["deleted_notes"]}'
            )
        )


# leads/management/commands/recycle_leads.py

from django.core.management.base import BaseCommand
from leads.utils import schedule_lead_recycling


class Command(BaseCommand):
    help = 'Run lead recycling based on active rules'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would be recycled without recycling')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write('DRY RUN - Checking recycling rules...')
            from leads.models import LeadRecyclingRule, Lead
            from django.utils import timezone
            from datetime import timedelta
            
            rules = LeadRecyclingRule.objects.filter(is_active=True)
            total_recyclable = 0
            
            for rule in rules:
                cutoff_date = timezone.now() - timedelta(days=rule.days_since_contact)
                leads_to_recycle = Lead.objects.filter(
                    status=rule.source_status,
                    last_contact_date__lte=cutoff_date,
                    call_count__lt=rule.max_attempts
                ).count()
                
                self.stdout.write(f'Rule: {rule.name} - {leads_to_recycle} leads would be recycled')
                total_recyclable += leads_to_recycle
            
            self.stdout.write(f'Total leads that would be recycled: {total_recyclable}')
            return
        
        recycled_count = schedule_lead_recycling()
        
        self.stdout.write(
            self.style.SUCCESS(f'Lead recycling completed: {recycled_count} leads recycled')
        )


# leads/management/commands/export_leads.py

from django.core.management.base import BaseCommand, CommandError
from leads.models import Lead, LeadList
from leads.utils import export_leads_to_csv
import os


class Command(BaseCommand):
    help = 'Export leads to CSV file'

    def add_arguments(self, parser):
        parser.add_argument('output_file', type=str, help='Output CSV file path')
        parser.add_argument('--lead-list', type=str, help='Lead list name or ID to export')
        parser.add_argument('--status', type=str, help='Export only leads with this status')
        parser.add_argument('--include-notes', action='store_true', help='Include latest notes in export')
        parser.add_argument('--date-from', type=str, help='Export leads created after this date (YYYY-MM-DD)')
        parser.add_argument('--date-to', type=str, help='Export leads created before this date (YYYY-MM-DD)')

    def handle(self, *args, **options):
        output_file = options['output_file']
        
        # Build queryset
        queryset = Lead.objects.select_related('lead_list', 'assigned_user')
        
        # Apply filters
        if options['lead_list']:
            lead_list_name = options['lead_list']
            try:
                if lead_list_name.isdigit():
                    lead_list = LeadList.objects.get(id=int(lead_list_name))
                else:
                    lead_list = LeadList.objects.get(name=lead_list_name)
                queryset = queryset.filter(lead_list=lead_list)
                self.stdout.write(f'Filtering by lead list: {lead_list.name}')
            except LeadList.DoesNotExist:
                raise CommandError(f'Lead list not found: {lead_list_name}')
        
        if options['status']:
            queryset = queryset.filter(status=options['status'])
            self.stdout.write(f'Filtering by status: {options["status"]}')
        
        if options['date_from']:
            from datetime import datetime
            date_from = datetime.strptime(options['date_from'], '%Y-%m-%d').date()
            queryset = queryset.filter(created_at__date__gte=date_from)
            self.stdout.write(f'Filtering from date: {date_from}')
        
        if options['date_to']:
            from datetime import datetime
            date_to = datetime.strptime(options['date_to'], '%Y-%m-%d').date()
            queryset = queryset.filter(created_at__date__lte=date_to)
            self.stdout.write(f'Filtering to date: {date_to}')
        
        lead_count = queryset.count()
        self.stdout.write(f'Exporting {lead_count} leads...')
        
        if lead_count == 0:
            self.stdout.write(self.style.WARNING('No leads found matching criteria'))
            return
        
        # Export to CSV
        csv_data = export_leads_to_csv(queryset, include_notes=options['include_notes'])
        
        # Write to file
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as file:
                file.write(csv_data)
            
            self.stdout.write(
                self.style.SUCCESS(f'Export completed: {output_file} ({lead_count} leads)')
            )
        
        except Exception as e:
            raise CommandError(f'Failed to write export file: {str(e)}')


# leads/management/commands/send_callback_reminders.py

from django.core.management.base import BaseCommand
from leads.utils import send_callback_reminders


class Command(BaseCommand):
    help = 'Send callback reminders for upcoming callbacks'

    def handle(self, *args, **options):
        reminder_count = send_callback_reminders()
        
        self.stdout.write(
            self.style.SUCCESS(f'Sent {reminder_count} callback reminders')
        )


# leads/management/commands/update_lead_scores.py

from django.core.management.base import BaseCommand
from leads.models import Lead
from leads.utils import calculate_lead_score


class Command(BaseCommand):
    help = 'Update lead scores for all leads'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for processing')

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        
        leads = Lead.objects.all()
        total_leads = leads.count()
        updated_count = 0
        
        self.stdout.write(f'Updating scores for {total_leads} leads...')
        
        for i in range(0, total_leads, batch_size):
            batch = leads[i:i + batch_size]
            
            for lead in batch:
                new_score = calculate_lead_score(lead)
                if lead.score != new_score:
                    lead.score = new_score
                    lead.save(update_fields=['score'])
                    updated_count += 1
            
            self.stdout.write(f'Processed {min(i + batch_size, total_leads)}/{total_leads} leads')
        
        self.stdout.write(
            self.style.SUCCESS(f'Scor e update completed: {updated_count} leads updated')
        )