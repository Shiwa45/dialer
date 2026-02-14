from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_index, name='index'),
    path('summary/', views.summary_report, name='summary'),
    path('realtime/', views.realtime, name='realtime'),
    path('monitor/', views.monitor_dashboard, name='monitor_dashboard'),
    path('monitor/api/', views.monitor_api, name='monitor_api'),

    # Analytical reports
    path('campaign-performance/', views.campaign_performance, name='campaign_performance'),
    path('agent-performance/', views.agent_performance, name='agent_performance'),
    path('call-analytics/', views.call_analytics, name='call_analytics'),
    path('lead-dispositions/', views.lead_dispositions, name='lead_dispositions'),

    # Dashboards & schedules
    path('dashboards/', views.dashboard_list, name='dashboards'),
    path('dashboards/<int:dashboard_id>/', views.dashboard_detail, name='dashboard_detail'),
    path('schedules/', views.schedule_list, name='schedules'),

    # Exports
    path('export/<str:report>/<str:fmt>/', views.export_report, name='export'),
]

# Phase 3.2: Real-time Reports
from . import realtime_views

urlpatterns += [
    path('realtime-new/', realtime_views.realtime_dashboard, name='realtime_dashboard'),
    path('api/realtime/agents/', realtime_views.realtime_agents_api, name='realtime_agents_api'),
    path('api/realtime/stats/', realtime_views.realtime_campaign_stats_api, name='realtime_stats_api'),
    path('api/realtime/queue/', realtime_views.realtime_call_queue_api, name='realtime_queue_api'),
]

# Phase 4.2: Supervisor Monitoring
urlpatterns += [
    # path('monitoring/', views.monitoring_dashboard, name='monitoring_dashboard'), # Using existing monitor_dashboard for now or new one? Guide says monitoring_dashboard.
    # The existing 'monitor/' uses 'monitor_dashboard'. I'll stick to the existing one for the main dashboard view if it overlaps, 
    # but the Phase 4 guide specifies 'monitoring_dashboard'. I will add it.
    path('supervisor/monitoring/', views.monitoring_dashboard, name='supervisor_monitoring'),
    path('api/monitoring/start/', views.start_monitoring, name='start_monitoring'),
    # path('api/monitoring/stop/', views.stop_monitoring, name='stop_monitoring'), # Only start is commonly needed if stop is implicit or explicit
    # path('api/monitoring/mode/', views.switch_monitoring_mode, name='switch_monitoring_mode'),
]

# Phase 4.3: Advanced Analytics
urlpatterns += [
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    path('analytics/export/', views.export_report_v2, name='export_report_v2'),
    # path('api/leaderboard/', views.leaderboard_api, name='leaderboard_api'), # If I implemented it
]

# ── NEW: Agent Time Monitoring ────────────────────────────────────────
from . import agent_time_views
urlpatterns += [
    path('agent-time/', agent_time_views.agent_time_report_page, name='agent_time_report'),
    path('api/agent-time/', agent_time_views.agent_time_report_api, name='agent_time_api'),
    path('api/agent-realtime/', agent_time_views.agent_realtime_status, name='agent_realtime_status'),
]
