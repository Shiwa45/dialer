# agents/routing.py

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Agent real-time updates
    re_path(r'ws/agent/(?P<agent_id>\w+)/$', consumers.AgentConsumer.as_asgi()),
    
    # Campaign monitoring (for supervisors)
    re_path(r'ws/campaign/(?P<campaign_id>\w+)/$', consumers.CampaignMonitorConsumer.as_asgi()),
]
