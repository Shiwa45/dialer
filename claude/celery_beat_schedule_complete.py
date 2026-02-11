"""
Celery Beat Schedule Configuration - Phase 1 & 2 Complete

Add these entries to your CELERY_BEAT_SCHEDULE in settings.py or celery.py
"""

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    
    # ========================================================================
    # PHASE 1.1: Auto Wrapup Timeout Checking
    # ========================================================================
    
    'check-auto-wrapup-timeouts': {
        'task': 'campaigns.tasks.check_auto_wrapup_timeouts',
        'schedule': 5.0,  # Every 5 seconds
        'options': {
            'expires': 10,
        }
    },
    
    # ========================================================================
    # Predictive Dialing
    # ========================================================================
    
    'predictive-dial': {
        'task': 'campaigns.tasks.predictive_dial',
        'schedule': 1.0,  # Every second
        'options': {
            'expires': 2,
        }
    },
    
    # ========================================================================
    # PHASE 2: Lead Recycling & Status Management
    # ========================================================================
    
    'recycle-failed-calls': {
        'task': 'campaigns.tasks.recycle_failed_calls',
        'schedule': 300.0,  # Every 5 minutes
    },
    
    'retry-dropped-calls': {
        'task': 'campaigns.tasks.retry_dropped_calls',
        'schedule': 120.0,  # Every 2 minutes
    },
    
    'reconcile-lead-status': {
        'task': 'campaigns.tasks.reconcile_lead_status',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    
    'sync-call-log-to-lead-status': {
        'task': 'campaigns.tasks.sync_call_log_to_lead_status',
        'schedule': 600.0,  # Every 10 minutes
    },
    
    # ========================================================================
    # Hopper Management
    # ========================================================================
    
    'fill-hopper': {
        'task': 'campaigns.tasks.fill_hopper',
        'schedule': 60.0,  # Every minute
    },
    
    'cleanup-stale-hopper-entries': {
        'task': 'campaigns.tasks.cleanup_stale_hopper_entries',
        'schedule': 300.0,  # Every 5 minutes
    },
    
    # ========================================================================
    # Recording Management
    # ========================================================================
    
    'sync-call-recordings': {
        'task': 'campaigns.tasks.sync_call_recordings',
        'schedule': 300.0,  # Every 5 minutes
    },
    
    'cleanup-old-recordings': {
        'task': 'campaigns.tasks.cleanup_old_recordings',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
        'kwargs': {'days': 90},
    },
    
    # ========================================================================
    # Agent Session Management
    # ========================================================================
    
    'check-offline-agents': {
        'task': 'campaigns.tasks.check_offline_agents',
        'schedule': 30.0,  # Every 30 seconds
    },
    
    # ========================================================================
    # System Health Monitoring
    # ========================================================================
    
    'monitor-system-health': {
        'task': 'campaigns.tasks.monitor_system_health',
        'schedule': 300.0,  # Every 5 minutes
    },
}


# ========================================================================
# Example usage in settings.py or celery.py
# ========================================================================

"""
# In autodialer/settings.py or autodialer/celery.py

from celery.schedules import crontab

# Celery Configuration
CELERY_TIMEZONE = 'Asia/Kolkata'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_BROKER_URL = 'redis://localhost:6379/0'

# Import beat schedule
from .celery_beat_schedule import CELERY_BEAT_SCHEDULE

# Task settings
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_RESULT_EXPIRES = 3600
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
"""
