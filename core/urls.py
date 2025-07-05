# core/urls.py

from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Main dashboard
    path('', views.dashboard, name='dashboard'),
    path('index/', views.dashboard, name='index'),
    
    # API endpoints for real-time data
    path('api/stats/', views.dashboard_stats_api, name='dashboard_stats_api'),
    path('api/chart-data/', views.dashboard_chart_data, name='dashboard_chart_data'),
    
    # System administration
    path('system-status/', views.system_status, name='system_status'),
]