from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from users.models import UserProfile
from telephony.models import Phone, AsteriskServer
from django.db import transaction

class Command(BaseCommand):
    help = 'Bulk create agents agent2-agent20 with extensions starting after 1007'

    def handle(self, *args, **options):
        # 1. Get Active Server
        server = AsteriskServer.objects.filter(is_active=True).first()
        if not server:
            self.stdout.write(self.style.ERROR("No active Asterisk Server found. Please create one first."))
            return

        # 2. Get or Create Agent Group
        agent_group, _ = Group.objects.get_or_create(name='Agent')

        # 3. Create Agents
        created_count = 0
        
        # Ranges: Agent 2 to 20
        # Extensions: After 1007 (so starting 1008)
        # Agent 2 -> 1008
        # Agent 3 -> 1009
        # ...
        
        start_agent_num = 2
        end_agent_num = 20
        start_extension = 1008

        for i in range(start_agent_num, end_agent_num + 1):
            username = f"agent{i}"
            password = username
            extension = str(start_extension + (i - start_agent_num))
            
            try:
                with transaction.atomic():
                    # Create User
                    user, created = User.objects.get_or_create(username=username)
                    if created:
                        user.set_password(password)
                        user.save()
                        self.stdout.write(f"Created user: {username}")
                    else:
                        self.stdout.write(f"User {username} already exists")

                    # Add to Group
                    user.groups.add(agent_group)

                    # Update/Create Profile
                    profile, _ = UserProfile.objects.get_or_create(user=user)
                    profile.extension = extension
                    profile.is_active_agent = True
                    profile.agent_id = f"AG{extension}"
                    profile.save()

                    # Create/Update Phone
                    # SIP Secret same as username for simplicity
                    phone, phone_created = Phone.objects.get_or_create(
                        extension=extension,
                        defaults={
                            'name': f"Agent {i} Phone",
                            'phone_type': 'sip',
                            'user': user,
                            'asterisk_server': server,
                            'secret': password, 
                            'is_active': True
                        }
                    )
                    
                    if not phone_created:
                        phone.user = user
                        phone.secret = password
                        phone.asterisk_server = server
                        phone.save() # This triggers sync_to_asterisk

                    self.stdout.write(self.style.SUCCESS(f"  -> Assigned Extension {extension} (SIP Secret: {password})"))
                    created_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to process {username}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Successfully processed {created_count} agents."))
