
from django.urls import re_path
from agents import consumers as agent_consumers
from users import consumers as user_consumers

websocket_urlpatterns = [
    re_path(r'ws/agent/$', agent_consumers.AgentConsumer.as_asgi()),
    re_path(r'ws/supervisor/$', agent_consumers.SupervisorConsumer.as_asgi()),
    re_path(r'ws/notifications/$', user_consumers.NotificationConsumer.as_asgi()),
]
