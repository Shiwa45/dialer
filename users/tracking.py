"""
Agent Tracking Service - Phase 3.3

Real-time per-second agent tracking using Redis for state management.
Provides GoAutodial-style agent monitoring with instant updates.

Features:
- Per-second state tracking
- Redis-backed state storage
- Automatic status time calculation
- WebSocket broadcasting
- Historical tracking for reports
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any

from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

# Try to import Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available, agent tracking will use fallback")


class AgentTracker:
    """
    Real-time agent state tracking with Redis backend
    
    PHASE 3.3: Per-second agent tracking
    
    Usage:
        tracker = AgentTracker()
        tracker.update_status(agent_id, 'busy', call_id='123')
        state = tracker.get_agent_state(agent_id)
    """
    
    # Redis key prefixes
    KEY_PREFIX = 'autodialer:agent:'
    STATE_KEY = 'state'
    HISTORY_KEY = 'history'
    STATS_KEY = 'stats'
    
    # Status categories
    PRODUCTIVE_STATUSES = ['available', 'busy', 'wrapup']
    PAUSE_STATUSES = ['break', 'lunch', 'training', 'meeting', 'system_issues']
    
    def __init__(self, redis_url: str = None):
        """
        Initialize the agent tracker
        
        Args:
            redis_url: Redis connection URL (defaults to settings.REDIS_URL)
        """
        self.redis_url = redis_url or getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
        self._redis = None
        self._fallback_store = {}  # Fallback if Redis unavailable
    
    @property
    def redis(self):
        """Get or create Redis connection"""
        if not REDIS_AVAILABLE:
            return None
        
        if self._redis is None:
            try:
                self._redis = redis.from_url(self.redis_url, decode_responses=True)
                self._redis.ping()
            except Exception as e:
                logger.error(f"Redis connection failed: {e}")
                self._redis = None
        
        return self._redis
    
    def _get_key(self, agent_id: int, key_type: str) -> str:
        """Generate Redis key for agent data"""
        return f"{self.KEY_PREFIX}{agent_id}:{key_type}"
    
    def update_status(
        self,
        agent_id: int,
        status: str,
        call_id: str = None,
        campaign_id: int = None,
        phone_number: str = None,
        lead_id: int = None,
        extra_data: Dict = None
    ) -> Dict:
        """
        Update agent status with timestamp
        
        Args:
            agent_id: User ID of the agent
            status: New status (available, busy, break, etc.)
            call_id: Current call ID if on call
            campaign_id: Current campaign ID
            phone_number: Phone number being called
            lead_id: Lead ID being called
            extra_data: Additional data to store
        
        Returns:
            dict: Updated agent state
        """
        now = timezone.now()
        
        # Get previous state to calculate duration
        previous_state = self.get_agent_state(agent_id)
        previous_status = previous_state.get('status') if previous_state else None
        previous_timestamp = previous_state.get('status_timestamp') if previous_state else None
        
        # Calculate time in previous status
        duration_in_previous = 0
        if previous_timestamp:
            try:
                prev_time = datetime.fromisoformat(previous_timestamp.replace('Z', '+00:00'))
                duration_in_previous = int((now - prev_time).total_seconds())
            except (ValueError, TypeError):
                pass
        
        # Build new state
        state = {
            'agent_id': agent_id,
            'status': status,
            'status_timestamp': now.isoformat(),
            'call_id': call_id,
            'campaign_id': campaign_id,
            'phone_number': phone_number,
            'lead_id': lead_id,
            'previous_status': previous_status,
            'duration_in_previous': duration_in_previous,
            'updated_at': now.isoformat()
        }
        
        if extra_data:
            state.update(extra_data)
        
        # Store state
        self._store_state(agent_id, state)
        
        # Record in history
        self._record_history(agent_id, previous_status, status, duration_in_previous)
        
        # Update daily stats
        self._update_daily_stats(agent_id, previous_status, duration_in_previous)
        
        # Broadcast update
        self._broadcast_update(agent_id, state)
        
        logger.debug(f"Agent {agent_id} status: {previous_status} -> {status}")
        
        return state
    
    def get_agent_state(self, agent_id: int) -> Optional[Dict]:
        """
        Get current agent state
        
        Args:
            agent_id: User ID of the agent
        
        Returns:
            dict: Current agent state or None
        """
        key = self._get_key(agent_id, self.STATE_KEY)
        
        if self.redis:
            try:
                data = self.redis.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.error(f"Error getting agent state: {e}")
        
        # Fallback
        return self._fallback_store.get(key)
    
    def get_all_agents_state(self, campaign_id: int = None) -> List[Dict]:
        """
        Get state of all agents
        
        Args:
            campaign_id: Optional filter by campaign
        
        Returns:
            list: List of agent states
        """
        agents = []
        
        if self.redis:
            try:
                # Get all agent state keys
                pattern = f"{self.KEY_PREFIX}*:{self.STATE_KEY}"
                keys = self.redis.keys(pattern)
                
                for key in keys:
                    data = self.redis.get(key)
                    if data:
                        state = json.loads(data)
                        if campaign_id is None or state.get('campaign_id') == campaign_id:
                            agents.append(state)
            except Exception as e:
                logger.error(f"Error getting all agent states: {e}")
        else:
            # Fallback
            for key, state in self._fallback_store.items():
                if self.STATE_KEY in key:
                    if campaign_id is None or state.get('campaign_id') == campaign_id:
                        agents.append(state)
        
        return agents
    
    def get_status_duration(self, agent_id: int) -> int:
        """
        Get seconds in current status
        
        Args:
            agent_id: User ID of the agent
        
        Returns:
            int: Seconds in current status
        """
        state = self.get_agent_state(agent_id)
        
        if not state or not state.get('status_timestamp'):
            return 0
        
        try:
            status_time = datetime.fromisoformat(state['status_timestamp'].replace('Z', '+00:00'))
            return int((timezone.now() - status_time).total_seconds())
        except (ValueError, TypeError):
            return 0
    
    def get_daily_stats(self, agent_id: int, date: datetime = None) -> Dict:
        """
        Get agent's daily statistics
        
        Args:
            agent_id: User ID of the agent
            date: Date to get stats for (defaults to today)
        
        Returns:
            dict: Daily statistics
        """
        if date is None:
            date = timezone.now().date()
        
        key = f"{self._get_key(agent_id, self.STATS_KEY)}:{date.isoformat()}"
        
        default_stats = {
            'date': date.isoformat(),
            'agent_id': agent_id,
            'time_available': 0,
            'time_busy': 0,
            'time_wrapup': 0,
            'time_paused': 0,
            'total_calls': 0,
            'status_changes': 0
        }
        
        if self.redis:
            try:
                data = self.redis.hgetall(key)
                if data:
                    for k, v in data.items():
                        if k in default_stats and k not in ['date', 'agent_id']:
                            default_stats[k] = int(v)
                    return default_stats
            except Exception as e:
                logger.error(f"Error getting daily stats: {e}")
        
        return default_stats
    
    def start_call(self, agent_id: int, call_id: str, phone_number: str, lead_id: int = None):
        """
        Record call start
        
        Args:
            agent_id: User ID of the agent
            call_id: Call identifier
            phone_number: Number being called
            lead_id: Lead ID if available
        """
        return self.update_status(
            agent_id=agent_id,
            status='busy',
            call_id=call_id,
            phone_number=phone_number,
            lead_id=lead_id,
            extra_data={'call_start': timezone.now().isoformat()}
        )
    
    def end_call(self, agent_id: int):
        """
        Record call end, transition to wrapup
        
        Args:
            agent_id: User ID of the agent
        """
        state = self.get_agent_state(agent_id)
        call_id = state.get('call_id') if state else None
        campaign_id = state.get('campaign_id') if state else None
        
        # Calculate call duration
        call_duration = 0
        if state and state.get('call_start'):
            try:
                start = datetime.fromisoformat(state['call_start'].replace('Z', '+00:00'))
                call_duration = int((timezone.now() - start).total_seconds())
            except (ValueError, TypeError):
                pass
        
        return self.update_status(
            agent_id=agent_id,
            status='wrapup',
            campaign_id=campaign_id,
            extra_data={
                'last_call_id': call_id,
                'last_call_duration': call_duration
            }
        )
    
    def set_available(self, agent_id: int, campaign_id: int = None):
        """
        Set agent as available
        
        Args:
            agent_id: User ID of the agent
            campaign_id: Campaign ID
        """
        return self.update_status(
            agent_id=agent_id,
            status='available',
            campaign_id=campaign_id
        )
    
    def set_paused(self, agent_id: int, pause_reason: str = 'break'):
        """
        Set agent as paused
        
        Args:
            agent_id: User ID of the agent
            pause_reason: Reason for pause (break, lunch, etc.)
        """
        return self.update_status(
            agent_id=agent_id,
            status=pause_reason
        )
    
    def set_offline(self, agent_id: int):
        """
        Set agent as offline and clear state
        
        Args:
            agent_id: User ID of the agent
        """
        # Record final duration before going offline
        self.update_status(agent_id, 'offline')
        
        # Clear state from Redis
        key = self._get_key(agent_id, self.STATE_KEY)
        
        if self.redis:
            try:
                self.redis.delete(key)
            except Exception as e:
                logger.error(f"Error clearing agent state: {e}")
        
        if key in self._fallback_store:
            del self._fallback_store[key]
    
    def _store_state(self, agent_id: int, state: Dict):
        """Store agent state in Redis"""
        key = self._get_key(agent_id, self.STATE_KEY)
        
        if self.redis:
            try:
                self.redis.set(key, json.dumps(state), ex=86400)  # 24 hour expiry
            except Exception as e:
                logger.error(f"Error storing agent state: {e}")
                self._fallback_store[key] = state
        else:
            self._fallback_store[key] = state
    
    def _record_history(self, agent_id: int, from_status: str, to_status: str, duration: int):
        """Record status transition in history"""
        if not from_status:
            return
        
        key = self._get_key(agent_id, self.HISTORY_KEY)
        
        record = {
            'from': from_status,
            'to': to_status,
            'duration': duration,
            'timestamp': timezone.now().isoformat()
        }
        
        if self.redis:
            try:
                self.redis.lpush(key, json.dumps(record))
                self.redis.ltrim(key, 0, 999)  # Keep last 1000 records
                self.redis.expire(key, 86400 * 7)  # 7 day expiry
            except Exception as e:
                logger.error(f"Error recording history: {e}")
    
    def _update_daily_stats(self, agent_id: int, previous_status: str, duration: int):
        """Update daily statistics"""
        if not previous_status or duration <= 0:
            return
        
        today = timezone.now().date()
        key = f"{self._get_key(agent_id, self.STATS_KEY)}:{today.isoformat()}"
        
        # Determine which time bucket to increment
        time_field = None
        if previous_status == 'available':
            time_field = 'time_available'
        elif previous_status == 'busy':
            time_field = 'time_busy'
        elif previous_status == 'wrapup':
            time_field = 'time_wrapup'
        elif previous_status in self.PAUSE_STATUSES:
            time_field = 'time_paused'
        
        if self.redis and time_field:
            try:
                self.redis.hincrby(key, time_field, duration)
                self.redis.hincrby(key, 'status_changes', 1)
                self.redis.expire(key, 86400 * 30)  # 30 day expiry
            except Exception as e:
                logger.error(f"Error updating daily stats: {e}")
    
    def _broadcast_update(self, agent_id: int, state: Dict):
        """Broadcast agent update via WebSocket"""
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            
            channel_layer = get_channel_layer()
            if not channel_layer:
                return
            
            # Broadcast to realtime report subscribers
            async_to_sync(channel_layer.group_send)(
                'realtime_report_all',
                {
                    'type': 'agent_update',
                    'data': {
                        'agent_id': agent_id,
                        'status': state.get('status'),
                        'campaign_id': state.get('campaign_id'),
                        'call_id': state.get('call_id'),
                        'phone_number': state.get('phone_number'),
                        'timestamp': state.get('updated_at')
                    }
                }
            )
            
            # Also broadcast to campaign-specific group
            campaign_id = state.get('campaign_id')
            if campaign_id:
                async_to_sync(channel_layer.group_send)(
                    f'realtime_report_{campaign_id}',
                    {
                        'type': 'agent_update',
                        'data': state
                    }
                )
                
        except Exception as e:
            logger.debug(f"Could not broadcast agent update: {e}")


# Global tracker instance
_tracker = None

def get_tracker() -> AgentTracker:
    """Get or create global tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = AgentTracker()
    return _tracker


# ============================================================================
# Integration Points
# ============================================================================

"""
Integration with ARI Worker:
----------------------------
In your ari_worker.py, add tracking calls:

from users.tracking import get_tracker

# When call starts:
tracker = get_tracker()
tracker.start_call(agent_id, channel_id, phone_number, lead_id)

# When call ends:
tracker.end_call(agent_id)


Integration with Agent Views:
-----------------------------
In your agents/views_simple.py update_status():

from users.tracking import get_tracker

@login_required
def update_status(request):
    tracker = get_tracker()
    status = request.POST.get('status')
    
    if status == 'available':
        tracker.set_available(request.user.id, campaign_id)
    elif status in ['break', 'lunch', 'training']:
        tracker.set_paused(request.user.id, status)
    elif status == 'offline':
        tracker.set_offline(request.user.id)
    
    # ... rest of view logic


Integration with WebSocket Consumer:
------------------------------------
The tracker automatically broadcasts updates to 'realtime_report_all' group.
Supervisors subscribed to this group will receive instant updates.
"""
