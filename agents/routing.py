# agents/routing.py

from django.urls import re_path
from . import consumers
from reports.consumers import MonitorDashboardConsumer, RealtimeReportConsumer
from users import consumers as user_consumers

websocket_urlpatterns = [
    # Agent real-time updates
    re_path(r'ws/agent/(?P<agent_id>\w+)/$', consumers.AgentConsumer.as_asgi()),
    
    # Campaign monitoring (for supervisors)
    re_path(r'ws/campaign/(?P<campaign_id>\w+)/$', consumers.CampaignMonitorConsumer.as_asgi()),
    re_path(r'ws/monitor/$', MonitorDashboardConsumer.as_asgi()),
    
    # Phase 3.2: Real-time Reports
    re_path(r'ws/reports/realtime/(?P<campaign_id>\w+)/$', RealtimeReportConsumer.as_asgi()),
    re_path(r'ws/reports/realtime/$', RealtimeReportConsumer.as_asgi()),

    # Notifications
    re_path(r'ws/notifications/$', user_consumers.NotificationConsumer.as_asgi()),
]
