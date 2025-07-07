from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from campaigns.models import Campaign
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Create test campaigns for development'

    def handle(self, *args, **options):
        # Get or create a user for testing
        user, created = User.objects.get_or_create(
            username='testadmin',
            defaults={
                'email': 'test@example.com',
                'first_name': 'Test',
                'last_name': 'Admin',
                'is_staff': True,
                'is_superuser': True
            }
        )
        
        if created:
            user.set_password('testpass123')
            user.save()
            self.stdout.write(f'Created test user: {user.username}')
        
        # Create test campaigns
        campaigns_data = [
            {
                'name': 'Sales Outbound Campaign',
                'description': 'Main sales campaign for new customers',
                'campaign_type': 'outbound',
                'dial_method': 'progressive',
                'status': 'active'
            },
            {
                'name': 'Customer Support Inbound',
                'description': 'Handle incoming customer support calls',
                'campaign_type': 'inbound',
                'dial_method': 'manual',
                'status': 'active'
            },
            {
                'name': 'Lead Follow-up Campaign',
                'description': 'Follow up with warm leads',
                'campaign_type': 'outbound',
                'dial_method': 'preview',
                'status': 'paused'
            },
            {
                'name': 'Blended Campaign Test',
                'description': 'Testing blended campaign functionality',
                'campaign_type': 'blended',
                'dial_method': 'predictive',
                'status': 'inactive'
            },
            {
                'name': 'Holiday Promotion Campaign',
                'description': 'Special holiday promotion calls',
                'campaign_type': 'outbound',
                'dial_method': 'progressive',
                'status': 'completed'
            }
        ]
        
        for campaign_data in campaigns_data:
            campaign, created = Campaign.objects.get_or_create(
                name=campaign_data['name'],
                defaults={
                    'description': campaign_data['description'],
                    'campaign_type': campaign_data['campaign_type'],
                    'dial_method': campaign_data['dial_method'],
                    'status': campaign_data['status'],
                    'created_by': user,
                    'start_date': timezone.now() + timedelta(days=1),
                    'daily_start_time': '09:00:00',
                    'daily_end_time': '17:00:00',
                    'max_attempts': 3,
                    'call_timeout': 30,
                    'retry_delay': 3600,
                    'dial_ratio': 1.0,
                    'max_lines': 10,
                    'abandon_rate': 5.0
                }
            )
            
            if created:
                self.stdout.write(f'Created campaign: {campaign.name}')
            else:
                self.stdout.write(f'Campaign already exists: {campaign.name}')
        
        self.stdout.write(
            self.style.SUCCESS('Successfully created test campaigns!')
        )
