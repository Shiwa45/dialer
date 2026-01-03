from django.core.management.base import BaseCommand
from agents.models import AgentDialerSession
from campaigns.models import Campaign

class Command(BaseCommand):
    help = 'Debug agent sessions'

    def handle(self, *args, **options):
        self.stdout.write("Checking Campaigns:")
        for camp in Campaign.objects.all():
            self.stdout.write(f"- ID: {camp.id} Name: {camp.name} Status: {camp.status} Method: {camp.dial_method}")

        self.stdout.write("\nChecking Agent Sessions:")
        sessions = AgentDialerSession.objects.all()
        if not sessions.exists():
            self.stdout.write("No agent sessions found.")
        
        for session in sessions:
            self.stdout.write(f"- Agent: {session.agent.username} (ID: {session.agent.id}) | Campaign: {session.campaign.name} | Status: {session.status}")
