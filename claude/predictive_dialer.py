"""
Predictive Dialer Algorithm - Phase 4.1

This module implements an intelligent predictive dialing algorithm that:
1. Dynamically adjusts dial ratio based on agent availability
2. Predicts call answer rates and agent wrap-up times
3. Minimizes abandoned calls while maximizing agent utilization
4. Supports AMD (Answering Machine Detection) integration

Based on Erlang-C queuing theory with real-time adjustments.
"""

import logging
import math
from datetime import timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from django.utils import timezone
from django.db.models import Avg, Count, Q, F
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class DialerMetrics:
    """Real-time dialer metrics"""
    agents_available: int
    agents_busy: int
    agents_wrapup: int
    agents_total: int
    calls_in_progress: int
    calls_in_queue: int
    avg_talk_time: float  # seconds
    avg_wrapup_time: float  # seconds
    avg_ring_time: float  # seconds
    answer_rate: float  # percentage (0-100)
    abandon_rate: float  # percentage (0-100)
    amd_rate: float  # answering machine rate (0-100)


@dataclass
class DialerConfig:
    """Dialer configuration parameters"""
    target_abandon_rate: float = 3.0  # Target max abandon rate %
    max_abandon_rate: float = 5.0  # Hard limit abandon rate %
    min_dial_ratio: float = 1.0  # Minimum calls per agent
    max_dial_ratio: float = 3.0  # Maximum calls per agent
    safety_factor: float = 0.85  # Conservative factor
    amd_enabled: bool = True
    amd_timeout_ms: int = 3000  # AMD detection timeout
    predictive_enabled: bool = True
    adaptive_pacing: bool = True


class PredictiveDialer:
    """
    Intelligent Predictive Dialing Algorithm
    
    Phase 4.1: Dynamic dial ratio calculation based on real-time metrics
    
    Usage:
        dialer = PredictiveDialer(campaign_id)
        ratio = dialer.calculate_dial_ratio()
        calls_to_make = dialer.get_calls_to_dial()
    """
    
    def __init__(self, campaign_id: int, config: DialerConfig = None):
        self.campaign_id = campaign_id
        self.config = config or DialerConfig()
        self._metrics_cache = None
        self._cache_time = None
        self._cache_ttl = 5  # seconds
    
    def get_metrics(self, force_refresh: bool = False) -> DialerMetrics:
        """
        Get current dialer metrics with caching
        
        Args:
            force_refresh: Force refresh metrics from database
        
        Returns:
            DialerMetrics: Current metrics
        """
        now = timezone.now()
        
        # Use cached metrics if available and fresh
        if (not force_refresh and 
            self._metrics_cache and 
            self._cache_time and 
            (now - self._cache_time).total_seconds() < self._cache_ttl):
            return self._metrics_cache
        
        metrics = self._fetch_metrics()
        self._metrics_cache = metrics
        self._cache_time = now
        
        return metrics
    
    def _fetch_metrics(self) -> DialerMetrics:
        """Fetch real-time metrics from database"""
        from users.models import AgentStatus
        from calls.models import CallLog
        from campaigns.models import Campaign, CampaignAgent, DialerHopper
        
        now = timezone.now()
        today = now.date()
        last_hour = now - timedelta(hours=1)
        last_15_min = now - timedelta(minutes=15)
        
        # Get campaign
        campaign = Campaign.objects.filter(id=self.campaign_id).first()
        if not campaign:
            return self._empty_metrics()
        
        # Get agent counts
        agent_ids = CampaignAgent.objects.filter(
            campaign_id=self.campaign_id,
            is_active=True
        ).values_list('user_id', flat=True)
        
        agent_statuses = AgentStatus.objects.filter(
            user_id__in=agent_ids
        ).exclude(status='offline')
        
        agents_available = agent_statuses.filter(status='available').count()
        agents_busy = agent_statuses.filter(status='busy').count()
        agents_wrapup = agent_statuses.filter(status='wrapup').count()
        agents_total = agent_statuses.count()
        
        # Get call metrics from last hour
        calls_query = CallLog.objects.filter(
            campaign_id=self.campaign_id,
            start_time__gte=last_hour
        )
        
        total_calls = calls_query.count()
        answered_calls = calls_query.filter(
            Q(call_status='answered') | Q(answer_time__isnull=False)
        ).count()
        abandoned_calls = calls_query.filter(call_status='abandoned').count()
        amd_calls = calls_query.filter(call_status='machine').count()
        
        # Calculate rates
        answer_rate = (answered_calls / total_calls * 100) if total_calls > 0 else 30.0
        abandon_rate = (abandoned_calls / total_calls * 100) if total_calls > 0 else 0.0
        amd_rate = (amd_calls / total_calls * 100) if total_calls > 0 else 15.0
        
        # Get average times from last 15 minutes (more recent = more accurate)
        recent_calls = CallLog.objects.filter(
            campaign_id=self.campaign_id,
            start_time__gte=last_15_min,
            talk_duration__gt=0
        )
        
        avg_times = recent_calls.aggregate(
            avg_talk=Avg('talk_duration'),
            avg_ring=Avg('ring_duration')
        )
        
        avg_talk_time = avg_times['avg_talk'] or campaign.avg_talk_time or 180.0
        avg_ring_time = avg_times['avg_ring'] or 15.0
        
        # Estimate wrapup time
        avg_wrapup_time = campaign.wrapup_time or 30.0
        
        # Get current call counts
        calls_in_progress = CallLog.objects.filter(
            campaign_id=self.campaign_id,
            end_time__isnull=True
        ).count()
        
        calls_in_queue = DialerHopper.objects.filter(
            campaign_id=self.campaign_id,
            status='dialing'
        ).count()
        
        return DialerMetrics(
            agents_available=agents_available,
            agents_busy=agents_busy,
            agents_wrapup=agents_wrapup,
            agents_total=agents_total,
            calls_in_progress=calls_in_progress,
            calls_in_queue=calls_in_queue,
            avg_talk_time=avg_talk_time,
            avg_wrapup_time=avg_wrapup_time,
            avg_ring_time=avg_ring_time,
            answer_rate=answer_rate,
            abandon_rate=abandon_rate,
            amd_rate=amd_rate
        )
    
    def _empty_metrics(self) -> DialerMetrics:
        """Return empty metrics for missing campaign"""
        return DialerMetrics(
            agents_available=0, agents_busy=0, agents_wrapup=0, agents_total=0,
            calls_in_progress=0, calls_in_queue=0,
            avg_talk_time=180.0, avg_wrapup_time=30.0, avg_ring_time=15.0,
            answer_rate=30.0, abandon_rate=0.0, amd_rate=15.0
        )
    
    def calculate_dial_ratio(self) -> float:
        """
        Calculate optimal dial ratio using predictive algorithm
        
        The dial ratio is the number of calls to place per available agent.
        
        Formula based on:
        - Expected agent availability at call answer time
        - Historical answer rate
        - Current abandon rate
        - AMD rate (if enabled)
        
        Returns:
            float: Optimal dial ratio
        """
        metrics = self.get_metrics()
        
        if metrics.agents_total == 0:
            return 0.0
        
        if not self.config.predictive_enabled:
            # Simple ratio mode
            return self.config.min_dial_ratio
        
        # Step 1: Calculate base ratio from answer rate
        # If 30% of calls are answered, we need ~3.3 calls per agent
        effective_answer_rate = metrics.answer_rate / 100
        
        # Account for AMD if enabled
        if self.config.amd_enabled and metrics.amd_rate > 0:
            # AMD calls don't need agents, so they effectively increase capacity
            human_answer_rate = effective_answer_rate * (1 - metrics.amd_rate / 100)
        else:
            human_answer_rate = effective_answer_rate
        
        if human_answer_rate <= 0:
            human_answer_rate = 0.25  # Assume 25% minimum
        
        base_ratio = 1 / human_answer_rate
        
        # Step 2: Predict agent availability at answer time
        # Calls take avg_ring_time to connect
        # Some busy agents will become available
        predicted_available = self._predict_agent_availability(
            metrics, 
            metrics.avg_ring_time
        )
        
        # Step 3: Adjust for current abandon rate
        abandon_adjustment = self._calculate_abandon_adjustment(metrics)
        
        # Step 4: Apply safety factor
        adjusted_ratio = base_ratio * abandon_adjustment * self.config.safety_factor
        
        # Step 5: Factor in predicted availability
        if predicted_available > metrics.agents_available:
            # More agents becoming available, can be more aggressive
            availability_boost = min(predicted_available / max(metrics.agents_available, 1), 1.3)
            adjusted_ratio *= availability_boost
        
        # Step 6: Clamp to configured limits
        final_ratio = max(
            self.config.min_dial_ratio,
            min(adjusted_ratio, self.config.max_dial_ratio)
        )
        
        logger.debug(
            f"Campaign {self.campaign_id} dial ratio: {final_ratio:.2f} "
            f"(base={base_ratio:.2f}, abandon_adj={abandon_adjustment:.2f})"
        )
        
        return round(final_ratio, 2)
    
    def _predict_agent_availability(self, metrics: DialerMetrics, seconds_ahead: float) -> int:
        """
        Predict how many agents will be available in N seconds
        
        Uses exponential decay model based on average call duration
        """
        current_available = metrics.agents_available
        
        # Calculate probability that busy agents will become available
        if metrics.avg_talk_time > 0:
            # Exponential probability of call ending
            prob_call_ends = 1 - math.exp(-seconds_ahead / metrics.avg_talk_time)
        else:
            prob_call_ends = 0
        
        # Estimate agents finishing calls
        agents_finishing = metrics.agents_busy * prob_call_ends
        
        # Estimate agents finishing wrapup
        if metrics.avg_wrapup_time > 0:
            prob_wrapup_ends = 1 - math.exp(-seconds_ahead / metrics.avg_wrapup_time)
        else:
            prob_wrapup_ends = 0.5
        
        agents_from_wrapup = metrics.agents_wrapup * prob_wrapup_ends
        
        predicted = current_available + agents_finishing + agents_from_wrapup
        
        return int(predicted)
    
    def _calculate_abandon_adjustment(self, metrics: DialerMetrics) -> float:
        """
        Calculate adjustment factor based on abandon rate
        
        If abandon rate is high, reduce dialing
        If abandon rate is low, can be more aggressive
        """
        current_abandon = metrics.abandon_rate
        target = self.config.target_abandon_rate
        max_abandon = self.config.max_abandon_rate
        
        if current_abandon >= max_abandon:
            # Emergency slowdown
            return 0.5
        elif current_abandon > target:
            # Linear reduction as we approach max
            overage = (current_abandon - target) / (max_abandon - target)
            return 1.0 - (overage * 0.4)  # Reduce up to 40%
        elif current_abandon < target * 0.5:
            # Very low abandon rate, can be more aggressive
            return 1.15  # 15% boost
        else:
            return 1.0
    
    def get_calls_to_dial(self) -> int:
        """
        Calculate how many calls to dial right now
        
        Returns:
            int: Number of calls to place
        """
        metrics = self.get_metrics()
        
        if metrics.agents_available == 0 and metrics.agents_wrapup == 0:
            return 0
        
        dial_ratio = self.calculate_dial_ratio()
        
        # Calculate target concurrent calls
        effective_agents = metrics.agents_available + (metrics.agents_wrapup * 0.5)
        target_calls = effective_agents * dial_ratio
        
        # Subtract calls already in progress/ringing
        current_calls = metrics.calls_in_progress + metrics.calls_in_queue
        calls_needed = target_calls - current_calls
        
        # Don't dial negative
        calls_to_dial = max(0, int(calls_needed))
        
        # Adaptive pacing: smooth out spikes
        if self.config.adaptive_pacing:
            # Don't dial more than 2x available agents at once
            max_burst = max(2, metrics.agents_available * 2)
            calls_to_dial = min(calls_to_dial, max_burst)
        
        return calls_to_dial
    
    def get_dialer_status(self) -> Dict:
        """
        Get comprehensive dialer status for monitoring
        
        Returns:
            dict: Dialer status including metrics and recommendations
        """
        metrics = self.get_metrics(force_refresh=True)
        dial_ratio = self.calculate_dial_ratio()
        calls_to_dial = self.get_calls_to_dial()
        
        # Calculate efficiency metrics
        agent_utilization = 0
        if metrics.agents_total > 0:
            agent_utilization = (metrics.agents_busy / metrics.agents_total) * 100
        
        # Determine health status
        health = 'good'
        warnings = []
        
        if metrics.abandon_rate > self.config.max_abandon_rate:
            health = 'critical'
            warnings.append(f'Abandon rate {metrics.abandon_rate:.1f}% exceeds maximum')
        elif metrics.abandon_rate > self.config.target_abandon_rate:
            health = 'warning'
            warnings.append(f'Abandon rate {metrics.abandon_rate:.1f}% above target')
        
        if agent_utilization < 50 and metrics.agents_available > 2:
            warnings.append('Low agent utilization - consider increasing dial ratio')
        
        if metrics.answer_rate < 20:
            warnings.append('Low answer rate - check lead quality')
        
        return {
            'campaign_id': self.campaign_id,
            'timestamp': timezone.now().isoformat(),
            'health': health,
            'warnings': warnings,
            'metrics': {
                'agents_available': metrics.agents_available,
                'agents_busy': metrics.agents_busy,
                'agents_wrapup': metrics.agents_wrapup,
                'agents_total': metrics.agents_total,
                'agent_utilization': round(agent_utilization, 1),
                'calls_in_progress': metrics.calls_in_progress,
                'calls_in_queue': metrics.calls_in_queue,
                'answer_rate': round(metrics.answer_rate, 1),
                'abandon_rate': round(metrics.abandon_rate, 1),
                'amd_rate': round(metrics.amd_rate, 1),
                'avg_talk_time': int(metrics.avg_talk_time),
                'avg_wrapup_time': int(metrics.avg_wrapup_time),
            },
            'dialing': {
                'dial_ratio': dial_ratio,
                'calls_to_dial': calls_to_dial,
                'mode': 'predictive' if self.config.predictive_enabled else 'power',
                'amd_enabled': self.config.amd_enabled,
            },
            'config': {
                'target_abandon_rate': self.config.target_abandon_rate,
                'max_abandon_rate': self.config.max_abandon_rate,
                'min_dial_ratio': self.config.min_dial_ratio,
                'max_dial_ratio': self.config.max_dial_ratio,
            }
        }


class DialerManager:
    """
    Manages multiple campaign dialers
    
    Usage:
        manager = DialerManager()
        status = manager.get_all_campaigns_status()
        manager.dial_for_campaign(campaign_id)
    """
    
    _dialers: Dict[int, PredictiveDialer] = {}
    
    @classmethod
    def get_dialer(cls, campaign_id: int) -> PredictiveDialer:
        """Get or create dialer for campaign"""
        if campaign_id not in cls._dialers:
            cls._dialers[campaign_id] = PredictiveDialer(campaign_id)
        return cls._dialers[campaign_id]
    
    @classmethod
    def dial_for_campaign(cls, campaign_id: int) -> int:
        """
        Dial calls for a campaign based on predictive algorithm
        
        Returns:
            int: Number of calls initiated
        """
        from campaigns.services import HopperService
        
        dialer = cls.get_dialer(campaign_id)
        calls_to_dial = dialer.get_calls_to_dial()
        
        if calls_to_dial <= 0:
            return 0
        
        # Get leads from hopper and initiate calls
        initiated = HopperService.dial_leads(campaign_id, calls_to_dial)
        
        logger.info(f"Campaign {campaign_id}: Dialed {initiated} calls (requested {calls_to_dial})")
        
        return initiated
    
    @classmethod
    def get_all_campaigns_status(cls) -> List[Dict]:
        """Get status for all active campaigns"""
        from campaigns.models import Campaign
        
        statuses = []
        
        for campaign in Campaign.objects.filter(status='active'):
            dialer = cls.get_dialer(campaign.id)
            status = dialer.get_dialer_status()
            status['campaign_name'] = campaign.name
            statuses.append(status)
        
        return statuses


# ============================================================================
# Celery Task for Predictive Dialing
# ============================================================================

"""
Add to campaigns/tasks.py:

from campaigns.predictive_dialer import DialerManager

@shared_task
def predictive_dial():
    '''
    Predictive dialing task - runs every second
    
    Schedule: Every 1 second
    '''
    from campaigns.models import Campaign
    
    total_dialed = 0
    
    for campaign in Campaign.objects.filter(status='active', dial_mode='predictive'):
        try:
            dialed = DialerManager.dial_for_campaign(campaign.id)
            total_dialed += dialed
        except Exception as e:
            logger.error(f"Error dialing for campaign {campaign.id}: {e}")
    
    return {'dialed': total_dialed}


# Add to CELERY_BEAT_SCHEDULE:
'predictive-dial': {
    'task': 'campaigns.tasks.predictive_dial',
    'schedule': 1.0,  # Every second
},
"""
