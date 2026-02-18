"""
agents/consumers_stats.py  –  Phase 5: Live Dashboard Stats
============================================================

WebSocket consumer that pushes real-time stats to the agent dashboard.
Sends updates whenever:
  • A call ends (via channel-layer group push from ARI worker / signal)
  • The browser sends a 'request_stats' ping
  • A 30-second auto-refresh ticker fires

Group name:  agent_stats_{user_id}
URL:         /ws/agent/stats/

Add to agents/routing.py:
    re_path(r'ws/agent/stats/$', consumers_stats.AgentStatsConsumer.as_asgi()),
"""

import json
import logging
from datetime import timedelta

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)


class AgentStatsConsumer(AsyncWebsocketConsumer):
    """
    Live dashboard stats for a single agent.
    """

    # ── Connect ──────────────────────────────────────────────────────────
    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close()
            return

        self.group_name = f'agent_stats_{self.user.id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.info(f'Agent {self.user.username} connected to live stats')

        # Send current stats immediately on connect
        stats = await self.get_agent_stats()
        await self.send(text_data=json.dumps({'type': 'stats_update', **stats}))

    # ── Disconnect ────────────────────────────────────────────────────────
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f'Agent {self.user.username} disconnected from live stats')

    # ── Receive (from browser) ────────────────────────────────────────────
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)

            if data.get('type') == 'request_stats':
                stats = await self.get_agent_stats()
                await self.send(text_data=json.dumps({'type': 'stats_update', **stats}))

            elif data.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))

        except Exception as e:
            logger.error(f'AgentStatsConsumer.receive error: {e}')

    # ── Channel-layer handler: triggered by signal/task ──────────────────
    async def stats_refresh(self, event):
        """
        Called when another part of the system broadcasts a refresh.
        Push fresh stats to this agent's browser.
        """
        stats = await self.get_agent_stats()
        await self.send(text_data=json.dumps({'type': 'stats_update', **stats}))

    async def call_completed(self, event):
        """
        Called right after a call ends.
        Sends incremental update so counter ticks immediately.
        """
        stats = await self.get_agent_stats()
        await self.send(text_data=json.dumps({
            'type': 'call_completed',
            **event.get('data', {}),
            'stats': stats,
        }))

    async def status_changed(self, event):
        """Push status-change notification."""
        await self.send(text_data=json.dumps({
            'type': 'status_changed',
            **event.get('data', {}),
        }))

    # ── DB query (sync → async) ───────────────────────────────────────────
    @database_sync_to_async
    def get_agent_stats(self) -> dict:
        """Compute today's stats + this week's stats for the agent."""
        from django.db.models import Sum, Count, Q
        from calls.models import CallLog

        now   = timezone.now()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())

        def _stats(qs):
            total    = qs.count()
            answered = qs.filter(call_status='answered').count()
            talk_sec = qs.aggregate(t=Sum('talk_duration'))['t'] or 0
            return {
                'total_calls':   total,
                'answered_calls': answered,
                'contact_rate':  round((answered / total * 100) if total else 0, 1),
                'talk_time_sec': int(talk_sec),
                'talk_time_fmt': _fmt(int(talk_sec)),
            }

        today_qs = CallLog.objects.filter(agent=self.user, start_time__date=today)
        week_qs  = CallLog.objects.filter(agent=self.user, start_time__date__gte=week_start)

        # Current call info
        current_call = None
        try:
            from users.models import AgentStatus
            agent_status = self.user.agent_status
            if agent_status and agent_status.current_call_id:
                call = CallLog.objects.filter(id=agent_status.current_call_id).first()
                if call:
                    duration = 0
                    if call.answer_time:
                        duration = int((now - call.answer_time).total_seconds())
                    current_call = {
                        'id':       call.id,
                        'number':   call.called_number,
                        'duration': duration,
                        'status':   call.call_status,
                    }
        except Exception:
            pass

        return {
            'today':        _stats(today_qs),
            'week':         _stats(week_qs),
            'current_call': current_call,
            'server_time':  now.isoformat(),
        }


def _fmt(seconds: int) -> str:
    """Format seconds → H:MM:SS or MM:SS."""
    h, rem = divmod(seconds, 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f'{h}:{m:02d}:{s:02d}'
    return f'{m:02d}:{s:02d}'
