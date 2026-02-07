#!/usr/bin/env python
"""
Check agent status and availability
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from users.models import AgentStatus, User
from agents.models import AgentDialerSession

print("=" * 60)
print("AGENT STATUS CHECK")
print("=" * 60)

# Check all agents
agents = AgentStatus.objects.select_related('user').all()
print(f"\nTotal Agent Statuses: {agents.count()}")

for agent_status in agents:
    agent = agent_status.user
    print(f"\n{'='*60}")
    print(f"Agent: {agent.username} (ID: {agent.id})")
    print(f"{'='*60}")
    
    print(f"  Status: {agent_status.status}")
    print(f"  Current Campaign: {agent_status.current_campaign}")
    print(f"  Extension: {agent.profile.extension if hasattr(agent, 'profile') else 'N/A'}")
    print(f"  Status Changed: {agent_status.status_changed_at}")
    
    # Get dialer sessions
    sessions = AgentDialerSession.objects.filter(agent=agent)
    print(f"  Dialer Sessions: {sessions.count()}")
    for session in sessions:
        print(f"    - Campaign: {session.campaign}, Status: {session.status}")
        print(f"      Bridge ID: {session.agent_bridge_id}")
        print(f"      Channel ID: {session.agent_channel_id}")

print(f"\n{'='*60}")
print("AVAILABLE AGENTS FOR CAMPAIGN 1:")
print(f"{'='*60}")

from django.db.models import Q
available = AgentStatus.objects.filter(
    Q(current_campaign_id=1) | Q(user__assigned_campaigns__id=1),
    status='available'
).select_related('user')

for a in available:
    print(f"  - {a.user.username} (ID: {a.user_id})")
