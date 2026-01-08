
from django.urls import re_path
from agents import consumers

websocket_urlpatterns = [
    re_path(r'ws/agent/$', consumers.AgentConsumer.as_asgi()),
    re_path(r'ws/supervisor/$', consumers.SupervisorConsumer.as_asgi()),
]
