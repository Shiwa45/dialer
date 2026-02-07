"""
Agent URLs - Updated with Phase 1 and Phase 2 endpoints

Includes new endpoints for:
- Call history (Phase 2.2)
- Improved disposition handling (Phase 1.2)
"""

from django.urls import path
from . import views_simple

app_name = 'agents'

urlpatterns = [
    # Dashboard
    path('', views_simple.simple_dashboard, name='dashboard'),
    path('dashboard/', views_simple.simple_dashboard, name='simple_dashboard'),
    
    # Status Management
    path('api/update-status/', views_simple.update_status, name='update_status'),
    path('api/status/', views_simple.get_call_status, name='get_status'),
    
    # Call Management
    path('api/call-status/', views_simple.get_call_status, name='call_status'),
    path('api/set-disposition/', views_simple.set_disposition, name='set_disposition'),
    path('api/hangup/', views_simple.hangup_call, name='hangup'),
    
    # Lead Information
    path('api/lead-info/', views_simple.get_lead_info, name='get_lead_info'),
    
    # Statistics
    path('api/statistics/', views_simple.agent_statistics, name='statistics'),
    
    # Call History (Phase 2.2)
    path('api/call-history/', views_simple.agent_call_history, name='call_history'),
    
    # WebRTC Configuration
    path('api/webrtc-config/', views_simple.get_webrtc_config, name='get_webrtc_config'),
]

# Phase 2.2: Full Call History Module
from . import views_call_history

urlpatterns += [
    path('call-history/', views_call_history.call_history_page, name='call_history_page'),
    path('api/history-full/', views_call_history.call_history_api, name='call_history_api'),
    path('api/history-stats/', views_call_history.call_history_stats, name='call_history_stats'),
    path('api/call-details/<int:call_id>/', views_call_history.call_details_api, name='call_details_api'),
    path('api/schedule-callback/', views_call_history.schedule_callback, name='schedule_callback'),
]
