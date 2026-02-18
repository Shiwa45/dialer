"""
agents/stats_broadcaster.py  –  Phase 5
=========================================

Utility called after any call ends to push live stats to the agent's
dashboard WebSocket.

Usage (in ARI worker, views, or Celery task):
    from agents.stats_broadcaster import broadcast_stats_refresh, broadcast_call_completed

    # After call ends:
    broadcast_call_completed(agent_user_id, call_data_dict)

    # Periodic refresh (e.g. every 30 s from Celery beat):
    broadcast_stats_refresh(agent_user_id)
"""

import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def broadcast_stats_refresh(agent_id: int):
    """Push a stats_refresh event to the agent's stats WebSocket group."""
    try:
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            f'agent_stats_{agent_id}',
            {'type': 'stats_refresh'}
        )
    except Exception as e:
        logger.debug(f'broadcast_stats_refresh({agent_id}) failed: {e}')


def broadcast_call_completed(agent_id: int, call_data: dict):
    """
    Push a call_completed event immediately when a call ends.
    The consumer responds by re-querying DB and sending fresh stats.
    """
    try:
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            f'agent_stats_{agent_id}',
            {
                'type': 'call_completed',
                'data': call_data,
            }
        )
    except Exception as e:
        logger.debug(f'broadcast_call_completed({agent_id}) failed: {e}')


def broadcast_status_changed(agent_id: int, new_status: str):
    """Notify the agent's browser that their status changed (e.g. wrapup → available)."""
    try:
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            f'agent_stats_{agent_id}',
            {
                'type': 'status_changed',
                'data': {'status': new_status},
            }
        )
    except Exception as e:
        logger.debug(f'broadcast_status_changed({agent_id}) failed: {e}')
