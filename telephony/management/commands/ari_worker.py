import asyncio
import json
import logging
import os
import websockets
import requests

from django.core.management.base import BaseCommand
from django.utils import timezone

from telephony.models import AsteriskServer
from calls.models import CallLog
from campaigns.models import OutboundQueue
from agents.models import AgentDialerSession
from telephony.services import AsteriskService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run ARI event worker to manage agent/customer channels and bridges'

    def add_arguments(self, parser):
        parser.add_argument('--server-id', help='AsteriskServer id (optional)')

    def handle(self, *args, **options):
        server_qs = AsteriskServer.objects.filter(is_active=True)
        if options.get('server_id'):
            server_qs = server_qs.filter(id=options['server_id'])
        server = server_qs.first()
        if not server:
            self.stderr.write('No active AsteriskServer found')
            return

        ari_url = f"ws://{server.ari_host}:{server.ari_port}/ari/events?app={server.ari_application}&api_key={server.ari_username}:{server.ari_password}"
        self.stdout.write(self.style.SUCCESS(f"Connecting to ARI: {ari_url}"))

        async def run():
            async for ws in websockets.connect(ari_url, ping_interval=20, ping_timeout=20):
                try:
                    async for message in ws:
                        self.process_event(server, message)
                except websockets.ConnectionClosed:
                    logger.warning('ARI connection closed, retrying...')
                    await asyncio.sleep(2)
                    continue

        asyncio.get_event_loop().run_until_complete(run())

    def process_event(self, server, message):
        try:
            event = json.loads(message)
        except Exception:
            logger.warning('Invalid ARI message')
            return

        etype = event.get('type')
        if etype == 'StasisStart':
            channel = event.get('channel', {})
            chan_id = channel.get('id')
            # Try to read from channelvars
            vars = (channel.get('channelvars') or {})
            bridge_id = vars.get('BRIDGE_ID')
            call_type = vars.get('CALL_TYPE')
            # Fallback to args list (e.g., 'CALL_TYPE=agent_leg,BRIDGE_ID=...')
            if not bridge_id or not call_type:
                args = event.get('args') or []
                for a in args:
                    if isinstance(a, str) and '=' in a:
                        k, _, v = a.partition('=')
                        if k == 'BRIDGE_ID':
                            bridge_id = bridge_id or v
                        if k == 'CALL_TYPE':
                            call_type = call_type or v

            if bridge_id and chan_id:
                svc = AsteriskService(server)
                svc.add_channel_to_bridge(bridge_id, chan_id)

            # Mark agent session ready if this is agent leg
            if call_type == 'agent_leg' and chan_id:
                AgentDialerSession.objects.filter(agent_channel_id=chan_id, status='connecting').update(status='ready')
            # Create call log for customer leg
            if call_type == 'customer_leg' and chan_id:
                try:
                    CallLog.objects.get_or_create(
                        channel=chan_id,
                        defaults={'call_type': 'outbound', 'call_status': 'ringing', 'start_time': timezone.now()}
                    )
                except Exception:
                    pass

        elif etype == 'ChannelDestroyed':
            chan_id = (event.get('channel') or {}).get('id')
            if chan_id:
                # If agent leg destroyed, mark session offline
                updated = AgentDialerSession.objects.filter(agent_channel_id=chan_id, status__in=['connecting', 'ready']).update(status='offline', ended_at=timezone.now())
                if updated:
                    logger.info('Agent leg ended; session set offline')
                # Mark call completed
                try:
                    cl = CallLog.objects.filter(channel=chan_id).first()
                    if cl and not cl.end_time:
                        cl.end_time = timezone.now()
                        cl.call_status = 'completed'
                        if cl.answer_time:
                            cl.talk_duration = int((cl.end_time - cl.answer_time).total_seconds())
                        cl.total_duration = int((cl.end_time - (cl.start_time or cl.end_time)).total_seconds())
                        cl.save()
                except Exception:
                    pass
                # If a queue item is tied via args, mark completed
                args = event.get('args') or []
                qid = None
                for a in args:
                    if isinstance(a, str) and a.startswith('QUEUE_ID='):
                        qid = a.split('=',1)[1]
                        break
                if qid:
                    OutboundQueue.objects.filter(id=qid).update(status='completed')

        elif etype == 'ChannelStateChange':
            channel = event.get('channel') or {}
            chan_id = channel.get('id')
            state = channel.get('state')
            if not chan_id or not state:
                return
            # Answer handling for call log and queue
            if state == 'Up':
                try:
                    cl = CallLog.objects.filter(channel=chan_id).first()
                    if cl and not cl.answer_time:
                        cl.answer_time = timezone.now()
                        cl.call_status = 'answered'
                        cl.save()
                except Exception:
                    pass
                # Update queue status to answered if bound
                args = event.get('args') or []
                qid = None
                for a in args:
                    if isinstance(a, str) and a.startswith('QUEUE_ID='):
                        qid = a.split('=',1)[1]
                        break
                if qid:
                    OutboundQueue.objects.filter(id=qid).update(status='answered')
