import json
from channels.generic.websocket import AsyncWebsocketConsumer


class AgentConsumer(AsyncWebsocketConsumer):
    """
    Push realtime call and status updates to an authenticated agent.
    Group name: agent_<user_id>
    """

    async def connect(self):
        user = self.scope.get("user")
        user_id_param = self.scope["url_route"]["kwargs"].get("user_id")
        if not user or not user.is_authenticated or str(user.id) != str(user_id_param):
            await self.close()
            return
        self.group_name = f"agent_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # No inbound messages expected; ignore.
        return

    async def call_event(self, event):
        payload = event.get("data", {})
        await self.send(text_data=json.dumps(payload))


class CampaignConsumer(AsyncWebsocketConsumer):
    """
    Stub consumer to avoid routing errors for campaign websocket paths.
    Currently just accepts and ignores messages.
    """

    async def connect(self):
        await self.accept()

    async def disconnect(self, close_code):
        return

    async def receive(self, text_data=None, bytes_data=None):
        return


class DummyConsumer(AsyncWebsocketConsumer):
    """
    Catch-all websocket consumer to avoid routing errors for unknown WS paths.
    Accepts and immediately closes.
    """

    async def connect(self):
        await self.accept()

    async def disconnect(self, close_code):
        return

    async def receive(self, text_data=None, bytes_data=None):
        # No handling; close connection
        await self.close()
