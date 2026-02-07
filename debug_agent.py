import os
import django
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "autodialer.settings")
django.setup()

from django.contrib.auth.models import User
from users.models import AgentStatus, UserProfile
from agents.models import AgentDialerSession

username = 'shiwansh'
try:
    user = User.objects.get(username=username)
    print(f"User: {user.username} (ID: {user.id})")
except User.DoesNotExist:
    print(f"User {username} not found")
    sys.exit(1)

# Check Profile
try:
    profile = user.profile
    print(f"Profile found. Extension: '{profile.extension}'")
except Exception as e:
    print(f"Profile error: {e}")

# Check AgentStatus
try:
    status = AgentStatus.objects.get(user=user)
    print(f"AgentStatus: {status.status}")
    print(f"  Changed at: {status.status_changed_at}")
except AgentStatus.DoesNotExist:
    print("AgentStatus not found")

# Check Sessions
sessions = AgentDialerSession.objects.filter(agent=user)
print(f"found {sessions.count()} sessions")
for s in sessions:
    print(f"  Session {s.id}: status={s.status}, extension='{s.agent_extension}', created={s.created_at}")

# Check check_agent_registrations logic simulation
print("\n--- Simulation ---")
extension = None
active_session = sessions.filter(status__in=['ready', 'connecting', 'incall']).order_by('-created_at').first()

if active_session:
    print(f"Found active session with extension: {active_session.agent_extension}")
    extension = active_session.agent_extension
else:
    print("No active session found")
    try:
        if hasattr(user, 'profile'):
             extension = user.profile.extension
             print(f"Found profile extension: {extension}")
        else:
             print("User has no profile attribute")
    except Exception as e:
        print(f"Error accessing profile: {e}")

if not extension:
    print("RESULT: No extension found -> Should mark offline")
else:
    print(f"RESULT: Extension {extension} found -> Checking registration...")
