# agents/consumers.py
# UPDATED: added agent_message handler so force_logout push from supervisor
# reaches the connected agent WebSocket and triggers instant redirect.

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class AgentConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for agent real-time updates."""

    async def connect(self):
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        self.agent_group_name = f'agent_{self.user.id}'

        await self.channel_layer.group_add(
            self.agent_group_name,
            self.channel_name
        )
        await self.accept()

        logger.info(f'Agent {self.user.username} connected to WebSocket')

        await self.send(text_data=json.dumps({
            'type'    : 'connection_established',
            'agent_id': self.user.id,
            'username': self.user.username,
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.agent_group_name,
            self.channel_name
        )
        logger.info(f'Agent {self.user.username} disconnected from WebSocket')

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            msg_type = data.get('type')

            if msg_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type'     : 'pong',
                    'timestamp': data.get('timestamp'),
                }))

            elif msg_type == 'status_update':
                await self.handle_status_update(data)

            elif msg_type == 'request_stats':
                await self.send_agent_stats()

        except Exception as e:
            logger.error(f'Error in AgentConsumer.receive: {e}')

    # ── Channel-layer message handlers ────────────────────────────────────
    # Each method maps to 'type' key in group_send payload.

    async def agent_message(self, event):
        """
        Generic message relay — forwards any payload from the channel layer
        straight to the connected WebSocket client.

        Used by:
          • force_logout_agent view  (type: 'force_logout')
          • call events, status pushes, etc.
        """
        message = event.get('message', event)
        await self.send(text_data=json.dumps(message))

    async def call_update(self, event):
        """Relay call event to agent."""
        await self.send(text_data=json.dumps({
            'type': 'call_update',
            **event.get('data', {}),
        }))

    async def status_update(self, event):
        """Relay status update to agent."""
        await self.send(text_data=json.dumps({
            'type'  : 'status_update',
            **event.get('data', {}),
        }))

    # ── Helpers ───────────────────────────────────────────────────────────

    @database_sync_to_async
    def handle_status_update(self, data):
        pass  # Handled server-side via update_status view

    @database_sync_to_async
    def send_agent_stats(self):
        pass  # Placeholder — stats sent via REST API


# ── Campaign monitor consumer (supervisor) ───────────────────────────────────

class CampaignMonitorConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for campaign monitoring (supervisors)."""

    async def connect(self):
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        self.campaign_id = self.scope['url_route']['kwargs'].get('campaign_id', 'all')
        self.group_name  = f'campaign_{self.campaign_id}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass

    async def campaign_update(self, event):
        await self.send(text_data=json.dumps(event.get('data', {})))
