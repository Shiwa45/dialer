"""
Phase 4 URL Patterns

URL patterns for Phase 4 features:
- Analytics dashboard and API
- Supervisor monitoring
- Agent scorecards
- Dialer status

Add these to your main urls.py or include in reports/urls.py
"""

from django.urls import path
from . import views_phase4 as views

app_name = 'reports'

# Phase 4 URL patterns
phase4_urlpatterns = [
    # ========================================
    # Phase 4.3: Analytics Dashboard
    # ========================================
    
    # Main analytics page
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    
    # Analytics API endpoints
    path('api/analytics/trends/', views.analytics_trends_api, name='analytics_trends_api'),
    path('api/analytics/hourly/', views.analytics_hourly_api, name='analytics_hourly_api'),
    path('api/analytics/leaderboard/', views.leaderboard_api, name='leaderboard_api'),
    path('api/analytics/roi/', views.roi_api, name='roi_api'),
    path('api/analytics/compare/', views.compare_periods_api, name='compare_periods_api'),
    
    # Export
    path('export/', views.export_report, name='export_report'),
    
    # ========================================
    # Phase 4.2: Supervisor Monitoring
    # ========================================
    
    # Monitoring dashboard
    path('monitoring/', views.monitoring_dashboard, name='monitoring_dashboard'),
    
    # Monitoring API endpoints
    path('api/monitoring/agents/', views.monitoring_agents_api, name='monitoring_agents_api'),
    path('api/monitoring/start/', views.start_monitoring, name='start_monitoring'),
    path('api/monitoring/stop/', views.stop_monitoring, name='stop_monitoring'),
    path('api/monitoring/mode/', views.switch_monitoring_mode, name='switch_monitoring_mode'),
    
    # ========================================
    # Phase 4.2: Agent Scorecards
    # ========================================
    
    path('api/scorecard/', views.agent_scorecard_api, name='agent_scorecard_api'),
    path('api/my-scorecard/', views.my_scorecard, name='my_scorecard'),
    
    # ========================================
    # Phase 4.1: Dialer Status
    # ========================================
    
    path('api/dialer/status/', views.dialer_status_api, name='dialer_status_api'),
    path('api/dialer/status/<int:campaign_id>/', views.campaign_dialer_status_api, name='campaign_dialer_status_api'),
]


# ========================================
# Integration Instructions
# ========================================

"""
To integrate these URLs, add the following to your main urls.py:

from django.urls import path, include

urlpatterns = [
    # ... existing patterns ...
    
    # Phase 4 reports
    path('reports/', include('reports.urls_phase4')),
]

Or add to existing reports/urls.py:

from . import views_phase4

urlpatterns = [
    # ... existing patterns ...
    
    # Phase 4: Analytics
    path('analytics/', views_phase4.analytics_dashboard, name='analytics_dashboard'),
    path('api/analytics/trends/', views_phase4.analytics_trends_api, name='analytics_trends_api'),
    # ... etc
]
"""
