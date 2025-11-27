from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/agent/(?P<user_id>\d+)/$', consumers.AgentConsumer.as_asgi()),
    re_path(r'ws/campaign/(?P<campaign_id>\d+)/$', consumers.CampaignConsumer.as_asgi()),
    # Catch-all to prevent noisy "No route found" errors
    re_path(r'ws/.*', consumers.DummyConsumer.as_asgi()),
]
