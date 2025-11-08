from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_index, name='index'),
    path('summary/', views.summary_report, name='summary'),
    path('realtime/', views.realtime, name='realtime'),

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
