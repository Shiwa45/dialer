# core/management/commands/seed_demo.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.db import transaction

from telephony.models import AsteriskServer, Phone
from campaigns.models import Campaign, Disposition, CampaignAgent
from leads.models import Lead, LeadList


class Command(BaseCommand):
    help = "Seed demo users, groups, telephony, campaigns, and leads"

    def add_arguments(self, parser):
        parser.add_argument('--wsl-ip', dest='wsl_ip', default='127.0.0.1', help='WSL Asterisk IP (for display)')

    @transaction.atomic
    def handle(self, *args, **options):
        wsl_ip = options['wsl_ip']

        self.stdout.write(self.style.MIGRATE_HEADING('Creating groups'))
        g_agent, _ = Group.objects.get_or_create(name='Agent')
        g_supervisor, _ = Group.objects.get_or_create(name='Supervisor')
        g_manager, _ = Group.objects.get_or_create(name='Manager')

        self.stdout.write(self.style.MIGRATE_HEADING('Creating users'))
        admin_user, created = User.objects.get_or_create(
            username='admin', defaults={'email': 'admin@example.com', 'is_staff': True, 'is_superuser': True}
        )
        if created:
            admin_user.set_password('Demo@12345')
            admin_user.save()

        manager_user, created = User.objects.get_or_create(
            username='manager', defaults={'email': 'manager@example.com', 'is_staff': True}
        )
        if created:
            manager_user.set_password('Demo@123')
            manager_user.save()
        manager_user.groups.add(g_manager)

        agent_user, created = User.objects.get_or_create(
            username='agent1', defaults={'email': 'agent1@example.com'}
        )
        if created:
            agent_user.set_password('Demo@123')
            agent_user.save()
        agent_user.groups.add(g_agent)

        self.stdout.write(self.style.MIGRATE_HEADING('Creating Asterisk server'))
        server, _ = AsteriskServer.objects.get_or_create(
            name='Demo Asterisk',
            defaults={
                'description': 'WSL Asterisk server for demo',
                'server_ip': wsl_ip,
                'ami_host': 'localhost',
                'ami_port': 5038,
                'ami_username': 'admin',
                'ami_password': 'amp111',
                'ari_host': 'localhost',
                'ari_port': 8088,
                'ari_username': 'autodialer',
                'ari_password': 'amp111',
                'ari_application': 'autodialer',
                'is_active': True,
            }
        )

        self.stdout.write(self.style.MIGRATE_HEADING('Creating demo phone/extension'))
        phone, _ = Phone.objects.get_or_create(
            extension='1001',
            defaults={
                'name': 'Agent 1001',
                'phone_type': 'sip',
                'user': agent_user,
                'secret': '1001',
                'host': 'dynamic',
                'context': 'agents',
                'codec': 'ulaw,alaw',
                'qualify': 'yes',
                'nat': 'force_rport,comedia',
                'is_active': True,
                'asterisk_server': server,
            }
        )
        # Ensure assignment if phone existed
        if phone.user_id != agent_user.id:
            phone.user = agent_user
            phone.secret = phone.secret or '1001'
            phone.save()

        self.stdout.write(self.style.MIGRATE_HEADING('Creating campaign/dispositions'))
        # Basic dispositions
        disp_sale, _ = Disposition.objects.get_or_create(
            code='SALE', defaults={'name': 'Sale', 'category': 'sale', 'is_sale': True, 'color': '#28a745'}
        )
        disp_na, _ = Disposition.objects.get_or_create(
            code='NO_ANSWER', defaults={'name': 'No Answer', 'category': 'no_answer', 'color': '#6c757d'}
        )
        disp_cb, _ = Disposition.objects.get_or_create(
            code='CALLBACK', defaults={'name': 'Callback', 'category': 'callback', 'requires_callback': True, 'color': '#17a2b8'}
        )

        campaign, _ = Campaign.objects.get_or_create(
            name='Demo Campaign',
            defaults={
                'description': 'Sample campaign for demo calls',
                'campaign_type': 'outbound',
                'dial_method': 'preview',
                'status': 'active',
                'is_active': True,
                'start_date': timezone.now(),
                'timezone': 'UTC',
                'created_by': manager_user,
                'total_leads': 0,
            }
        )
        CampaignAgent.objects.get_or_create(campaign=campaign, user=agent_user, defaults={'is_active': True})

        self.stdout.write(self.style.MIGRATE_HEADING('Creating leads'))
        lead_list, _ = LeadList.objects.get_or_create(name='Demo Leads', defaults={'description': 'Seeded demo leads', 'created_by': manager_user})
        leads = [
            {'first_name': 'Alice', 'last_name': 'Doe', 'phone_number': '+12025550101'},
            {'first_name': 'Bob', 'last_name': 'Smith', 'phone_number': '+12025550102'},
            {'first_name': 'Carol', 'last_name': 'Johnson', 'phone_number': '+12025550103'},
        ]
        for l in leads:
            Lead.objects.get_or_create(
                phone_number=l['phone_number'],
                defaults={
                    'first_name': l['first_name'],
                    'last_name': l['last_name'],
                    'lead_list': lead_list,
                    'assigned_user': agent_user,
                    'status': 'new',
                    'priority': 'medium',
                    'source': 'Demo Seed',
                }
            )

        self.stdout.write(self.style.SUCCESS('\nDemo data created. Credentials:'))
        self.stdout.write(' - Admin:    admin / Demo@12345')
        self.stdout.write(' - Manager:  manager / Demo@123')
        self.stdout.write(' - Agent:    agent1 / Demo@123')
        self.stdout.write('\nExtension 1001 (secret 1001) assigned to agent1. Register your softphone against your WSL IP and context "agents".')

