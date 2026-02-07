"""
Call Scoring and Quality Monitoring - Phase 4.2

This module provides:
1. Automated call scoring based on metrics
2. Supervisor call monitoring (listen, whisper, barge)
3. Quality scorecards for agents
4. Call flagging for review
"""

import logging
from datetime import timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from django.utils import timezone
from django.db import models
from django.db.models import Avg, Count, Sum, Q, F

logger = logging.getLogger(__name__)


# ============================================================================
# Call Scoring System
# ============================================================================

class ScoreCategory(Enum):
    """Call score categories"""
    EXCELLENT = 'excellent'
    GOOD = 'good'
    AVERAGE = 'average'
    POOR = 'poor'
    CRITICAL = 'critical'


@dataclass
class ScoringCriteria:
    """Criteria for automated call scoring"""
    # Duration scoring
    min_talk_time: int = 30  # seconds
    optimal_talk_time_min: int = 120
    optimal_talk_time_max: int = 300
    max_talk_time: int = 600
    
    # Hold time scoring
    max_hold_time: int = 60
    hold_penalty_per_minute: int = 5
    
    # Disposition scoring
    sale_bonus: int = 30
    callback_bonus: int = 15
    dnc_penalty: int = 10
    
    # First call resolution bonus
    first_call_bonus: int = 10


class CallScorer:
    """
    Automated Call Scoring System
    
    Phase 4.2: Scores calls based on multiple criteria
    
    Usage:
        scorer = CallScorer()
        score = scorer.score_call(call_log)
        category = scorer.get_category(score)
    """
    
    def __init__(self, criteria: ScoringCriteria = None):
        self.criteria = criteria or ScoringCriteria()
    
    def score_call(self, call_log) -> Dict:
        """
        Score a call based on multiple factors
        
        Args:
            call_log: CallLog instance
        
        Returns:
            dict: Score breakdown
        """
        scores = {
            'duration_score': self._score_duration(call_log),
            'hold_score': self._score_hold_time(call_log),
            'disposition_score': self._score_disposition(call_log),
            'resolution_score': self._score_resolution(call_log),
        }
        
        # Calculate total (weighted average)
        weights = {
            'duration_score': 0.3,
            'hold_score': 0.2,
            'disposition_score': 0.35,
            'resolution_score': 0.15,
        }
        
        total_score = sum(
            scores[key] * weights[key] 
            for key in scores
        )
        
        scores['total_score'] = round(total_score, 1)
        scores['category'] = self.get_category(total_score).value
        
        return scores
    
    def _score_duration(self, call_log) -> float:
        """Score based on talk duration"""
        duration = call_log.talk_duration or 0
        
        if duration < self.criteria.min_talk_time:
            # Too short
            return 40
        elif duration < self.criteria.optimal_talk_time_min:
            # Below optimal
            ratio = duration / self.criteria.optimal_talk_time_min
            return 40 + (ratio * 30)
        elif duration <= self.criteria.optimal_talk_time_max:
            # Optimal range
            return 100
        elif duration <= self.criteria.max_talk_time:
            # Above optimal but acceptable
            overage = duration - self.criteria.optimal_talk_time_max
            max_overage = self.criteria.max_talk_time - self.criteria.optimal_talk_time_max
            penalty = (overage / max_overage) * 30
            return 100 - penalty
        else:
            # Too long
            return 50
    
    def _score_hold_time(self, call_log) -> float:
        """Score based on hold time"""
        hold_time = getattr(call_log, 'hold_duration', 0) or 0
        
        if hold_time == 0:
            return 100
        elif hold_time <= self.criteria.max_hold_time:
            penalty = (hold_time / self.criteria.max_hold_time) * 30
            return 100 - penalty
        else:
            # Excessive hold time
            minutes_over = (hold_time - self.criteria.max_hold_time) / 60
            penalty = 30 + (minutes_over * self.criteria.hold_penalty_per_minute)
            return max(30, 100 - penalty)
    
    def _score_disposition(self, call_log) -> float:
        """Score based on disposition"""
        base_score = 70
        
        if not call_log.disposition:
            return 50  # No disposition is bad
        
        disposition = call_log.disposition
        
        # Check disposition attributes
        if getattr(disposition, 'is_sale', False):
            return base_score + self.criteria.sale_bonus
        elif getattr(disposition, 'is_callback', False):
            return base_score + self.criteria.callback_bonus
        elif getattr(disposition, 'is_dnc', False):
            return base_score - self.criteria.dnc_penalty
        else:
            return base_score
    
    def _score_resolution(self, call_log) -> float:
        """Score based on first call resolution"""
        if not call_log.lead:
            return 70
        
        lead = call_log.lead
        
        # Check if this was the first successful contact
        if lead.call_count <= 1:
            if call_log.disposition and getattr(call_log.disposition, 'is_sale', False):
                return 100  # First call sale!
            elif call_log.talk_duration and call_log.talk_duration > 60:
                return 90  # First call meaningful contact
        
        return 70
    
    def get_category(self, score: float) -> ScoreCategory:
        """Get score category"""
        if score >= 90:
            return ScoreCategory.EXCELLENT
        elif score >= 75:
            return ScoreCategory.GOOD
        elif score >= 60:
            return ScoreCategory.AVERAGE
        elif score >= 40:
            return ScoreCategory.POOR
        else:
            return ScoreCategory.CRITICAL


# ============================================================================
# Agent Quality Scorecard
# ============================================================================

class AgentScorecard:
    """
    Agent Performance Scorecard
    
    Calculates comprehensive quality metrics for agents
    
    Usage:
        scorecard = AgentScorecard(agent_id)
        metrics = scorecard.get_daily_metrics()
        weekly = scorecard.get_weekly_summary()
    """
    
    def __init__(self, agent_id: int):
        self.agent_id = agent_id
        self.scorer = CallScorer()
    
    def get_daily_metrics(self, date=None) -> Dict:
        """
        Get agent metrics for a specific day
        
        Args:
            date: Date to get metrics for (defaults to today)
        
        Returns:
            dict: Daily metrics
        """
        from calls.models import CallLog
        
        if date is None:
            date = timezone.now().date()
        
        calls = CallLog.objects.filter(
            agent_id=self.agent_id,
            start_time__date=date
        )
        
        total_calls = calls.count()
        answered_calls = calls.filter(answer_time__isnull=False).count()
        
        # Get averages
        agg = calls.filter(talk_duration__gt=0).aggregate(
            avg_talk_time=Avg('talk_duration'),
            total_talk_time=Sum('talk_duration'),
            avg_score=Avg('quality_score')
        )
        
        # Get disposition breakdown
        dispositions = calls.exclude(disposition__isnull=True).values(
            'disposition__name'
        ).annotate(count=Count('id'))
        
        # Get sales count
        sales = calls.filter(disposition__is_sale=True).count()
        
        # Calculate rates
        contact_rate = (answered_calls / total_calls * 100) if total_calls > 0 else 0
        conversion_rate = (sales / answered_calls * 100) if answered_calls > 0 else 0
        
        return {
            'date': date.isoformat(),
            'agent_id': self.agent_id,
            'total_calls': total_calls,
            'answered_calls': answered_calls,
            'sales': sales,
            'contact_rate': round(contact_rate, 1),
            'conversion_rate': round(conversion_rate, 1),
            'avg_talk_time': int(agg['avg_talk_time'] or 0),
            'total_talk_time': int(agg['total_talk_time'] or 0),
            'avg_quality_score': round(agg['avg_score'] or 0, 1),
            'dispositions': {d['disposition__name']: d['count'] for d in dispositions}
        }
    
    def get_weekly_summary(self, end_date=None) -> Dict:
        """
        Get weekly performance summary
        
        Args:
            end_date: End date of week (defaults to today)
        
        Returns:
            dict: Weekly summary with trends
        """
        if end_date is None:
            end_date = timezone.now().date()
        
        start_date = end_date - timedelta(days=7)
        
        daily_metrics = []
        current_date = start_date
        
        while current_date <= end_date:
            metrics = self.get_daily_metrics(current_date)
            daily_metrics.append(metrics)
            current_date += timedelta(days=1)
        
        # Calculate weekly totals
        total_calls = sum(d['total_calls'] for d in daily_metrics)
        total_sales = sum(d['sales'] for d in daily_metrics)
        total_talk_time = sum(d['total_talk_time'] for d in daily_metrics)
        
        avg_scores = [d['avg_quality_score'] for d in daily_metrics if d['avg_quality_score'] > 0]
        avg_quality_score = sum(avg_scores) / len(avg_scores) if avg_scores else 0
        
        # Calculate trend (compare first half to second half)
        first_half = daily_metrics[:4]
        second_half = daily_metrics[4:]
        
        first_half_calls = sum(d['total_calls'] for d in first_half)
        second_half_calls = sum(d['total_calls'] for d in second_half)
        
        if first_half_calls > 0:
            calls_trend = ((second_half_calls - first_half_calls) / first_half_calls) * 100
        else:
            calls_trend = 0
        
        return {
            'period': f"{start_date.isoformat()} to {end_date.isoformat()}",
            'agent_id': self.agent_id,
            'total_calls': total_calls,
            'total_sales': total_sales,
            'total_talk_time': total_talk_time,
            'total_talk_time_formatted': self._format_duration(total_talk_time),
            'avg_quality_score': round(avg_quality_score, 1),
            'calls_trend': round(calls_trend, 1),
            'daily_breakdown': daily_metrics
        }
    
    def get_quality_ranking(self) -> Dict:
        """
        Get agent's ranking compared to peers
        
        Returns:
            dict: Ranking information
        """
        from calls.models import CallLog
        from django.contrib.auth.models import User
        
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        # Get all agents' average scores
        agent_scores = CallLog.objects.filter(
            start_time__date__gte=week_ago,
            quality_score__isnull=False
        ).values('agent_id').annotate(
            avg_score=Avg('quality_score'),
            total_calls=Count('id')
        ).filter(total_calls__gte=10).order_by('-avg_score')
        
        # Find this agent's rank
        rank = 1
        total_agents = len(agent_scores)
        agent_score = None
        
        for idx, score in enumerate(agent_scores):
            if score['agent_id'] == self.agent_id:
                rank = idx + 1
                agent_score = score['avg_score']
                break
        
        percentile = ((total_agents - rank) / total_agents * 100) if total_agents > 0 else 0
        
        return {
            'rank': rank,
            'total_agents': total_agents,
            'percentile': round(percentile, 1),
            'avg_score': round(agent_score, 1) if agent_score else 0
        }
    
    def _format_duration(self, seconds: int) -> str:
        """Format seconds as HH:MM:SS"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m {secs}s"


# ============================================================================
# Supervisor Monitoring
# ============================================================================

class MonitorMode(Enum):
    """Call monitoring modes"""
    LISTEN = 'listen'     # Listen only
    WHISPER = 'whisper'   # Speak to agent only
    BARGE = 'barge'       # Speak to both parties
    COACH = 'coach'       # Listen with ability to whisper


class SupervisorMonitor:
    """
    Supervisor Call Monitoring Service
    
    Phase 4.2: Listen, whisper, barge functionality
    
    Usage:
        monitor = SupervisorMonitor(asterisk_service)
        monitor.start_monitoring(supervisor_channel, agent_channel, MonitorMode.LISTEN)
    """
    
    def __init__(self, asterisk_service=None):
        self.asterisk_service = asterisk_service
        self._active_sessions = {}
    
    def start_monitoring(
        self, 
        supervisor_channel: str,
        target_channel: str,
        mode: MonitorMode = MonitorMode.LISTEN
    ) -> Dict:
        """
        Start monitoring a call
        
        Args:
            supervisor_channel: Supervisor's channel ID
            target_channel: Channel to monitor (agent's channel)
            mode: Monitoring mode
        
        Returns:
            dict: Monitoring session info
        """
        if not self.asterisk_service:
            raise ValueError("Asterisk service not configured")
        
        session_id = f"mon_{supervisor_channel}_{target_channel}"
        
        try:
            # Configure monitoring based on mode
            if mode == MonitorMode.LISTEN:
                # ChanSpy with listen-only (q = quiet, w = whisper disabled)
                spy_options = 'q'
            elif mode == MonitorMode.WHISPER:
                # ChanSpy with whisper mode (w = whisper to spied channel)
                spy_options = 'qw'
            elif mode == MonitorMode.BARGE:
                # ChanSpy with barge mode (B = barge, both can hear)
                spy_options = 'qB'
            elif mode == MonitorMode.COACH:
                # ChanSpy with whisper, can toggle
                spy_options = 'qw'
            
            # Get the channel prefix to spy on
            # ChanSpy takes a channel name prefix
            channel_prefix = self._get_channel_prefix(target_channel)
            
            # Execute ChanSpy via ARI or AMI
            self.asterisk_service.execute_application(
                supervisor_channel,
                'ChanSpy',
                f'{channel_prefix},{spy_options}'
            )
            
            # Track session
            self._active_sessions[session_id] = {
                'supervisor_channel': supervisor_channel,
                'target_channel': target_channel,
                'mode': mode.value,
                'started_at': timezone.now().isoformat()
            }
            
            logger.info(f"Started monitoring: {supervisor_channel} -> {target_channel} ({mode.value})")
            
            return {
                'success': True,
                'session_id': session_id,
                'mode': mode.value
            }
            
        except Exception as e:
            logger.error(f"Error starting monitoring: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def change_mode(self, session_id: str, new_mode: MonitorMode) -> Dict:
        """
        Change monitoring mode mid-session
        
        Args:
            session_id: Monitoring session ID
            new_mode: New monitoring mode
        
        Returns:
            dict: Result
        """
        if session_id not in self._active_sessions:
            return {'success': False, 'error': 'Session not found'}
        
        session = self._active_sessions[session_id]
        
        # Stop current monitoring and restart with new mode
        self.stop_monitoring(session_id)
        
        return self.start_monitoring(
            session['supervisor_channel'],
            session['target_channel'],
            new_mode
        )
    
    def stop_monitoring(self, session_id: str) -> Dict:
        """
        Stop monitoring session
        
        Args:
            session_id: Monitoring session ID
        
        Returns:
            dict: Result
        """
        if session_id not in self._active_sessions:
            return {'success': False, 'error': 'Session not found'}
        
        session = self._active_sessions.pop(session_id)
        
        try:
            # Hangup supervisor's monitoring channel
            self.asterisk_service.hangup_channel(session['supervisor_channel'])
            
            logger.info(f"Stopped monitoring session: {session_id}")
            
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error stopping monitoring: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_active_sessions(self) -> List[Dict]:
        """Get all active monitoring sessions"""
        return list(self._active_sessions.values())
    
    def _get_channel_prefix(self, channel_id: str) -> str:
        """Extract channel prefix for ChanSpy"""
        # Channel IDs are like PJSIP/1001-00000001
        # ChanSpy needs the prefix like PJSIP/1001
        parts = channel_id.split('-')
        if len(parts) > 1:
            return parts[0]
        return channel_id


# ============================================================================
# Quality Models
# ============================================================================

"""
Add these models to calls/models.py:

class CallQualityScore(models.Model):
    '''Detailed quality scoring for calls'''
    call = models.OneToOneField(
        'CallLog',
        on_delete=models.CASCADE,
        related_name='quality_details'
    )
    
    # Individual scores (0-100)
    duration_score = models.FloatField(default=0)
    hold_score = models.FloatField(default=0)
    disposition_score = models.FloatField(default=0)
    resolution_score = models.FloatField(default=0)
    
    # Total score
    total_score = models.FloatField(default=0)
    category = models.CharField(max_length=20, default='average')
    
    # Flags
    flagged_for_review = models.BooleanField(default=False)
    flag_reason = models.CharField(max_length=200, blank=True)
    
    # Review
    reviewed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_calls'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    review_score = models.FloatField(null=True, blank=True)  # Manual score override
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Call Quality Score'
        verbose_name_plural = 'Call Quality Scores'


class SupervisorMonitorLog(models.Model):
    '''Log of supervisor monitoring sessions'''
    supervisor = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='monitoring_sessions'
    )
    agent = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='monitored_sessions'
    )
    call = models.ForeignKey(
        'CallLog',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    mode = models.CharField(max_length=20)  # listen, whisper, barge
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True)  # seconds
    
    notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = 'Monitor Log'
        verbose_name_plural = 'Monitor Logs'
        ordering = ['-started_at']


# Add to CallLog model:
class CallLog(models.Model):
    # ... existing fields ...
    
    # Phase 4.2: Quality fields
    quality_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Automated quality score (0-100)"
    )
    hold_duration = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total hold time in seconds"
    )
"""
