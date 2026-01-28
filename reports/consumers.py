import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from reports.monitoring import build_monitor_payload

logger = logging.getLogger(__name__)


class MonitorDashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close()
            return

        await self.accept()
        await self._send_snapshot()

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        if data.get('type') == 'request_update':
            await self._send_snapshot()

    async def _send_snapshot(self):
        payload = await self._get_payload()
        await self.send(text_data=json.dumps({
            'type': 'monitor_snapshot',
            'payload': payload,
        }))

    @database_sync_to_async
    def _get_payload(self):
        return build_monitor_payload()
