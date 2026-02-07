import os
import django
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "autodialer.settings")
django.setup()

from users.models import AgentStatus
from agents.models import AgentDialerSession

print("Resetting all agent statuses to 'offline'...")
updated = AgentStatus.objects.all().update(status='offline', current_call_id='', call_start_time=None)
print(f"Updated {updated} AgentStatus records.")

print("Deleting all active AgentDialerSessions...")
deleted, _ = AgentDialerSession.objects.all().delete()
print(f"Deleted {deleted} AgentDialerSession records.")

print("Reset complete. All agents are offline.")
