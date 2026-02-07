"""
URL Patterns for Phase 2 Features

This file contains all URL patterns needed for Phase 2 features.
Add these to your respective urls.py files.
"""

# ============================================================================
# agents/urls.py
# ============================================================================
"""
from django.urls import path
from . import views_simple
from . import views_call_history  # New file for Phase 2.2

app_name = 'agents'

urlpatterns = [
    # Existing URLs
    path('', views_simple.simple_dashboard, name='dashboard'),
    path('dashboard/', views_simple.simple_dashboard, name='simple_dashboard'),
    path('api/update-status/', views_simple.update_status, name='update_status'),
    path('api/set-disposition/', views_simple.set_disposition, name='set_disposition'),
    path('api/hangup/', views_simple.hangup_call, name='hangup'),
    path('api/lead-info/', views_simple.get_lead_info, name='get_lead_info'),
    path('api/call-status/', views_simple.get_call_status, name='call_status'),
    path('api/statistics/', views_simple.agent_statistics, name='statistics'),
    path('api/webrtc-config/', views_simple.get_webrtc_config, name='get_webrtc_config'),
    
    # Phase 2.2: Call History
    path('call-history/', views_call_history.call_history_page, name='call_history_page'),
    path('api/call-history/', views_call_history.call_history_api, name='call_history_api'),
    path('api/call-history/stats/', views_call_history.call_history_stats, name='call_history_stats'),
    path('api/call-details/<int:call_id>/', views_call_history.call_details_api, name='call_details_api'),
    path('api/schedule-callback/', views_call_history.schedule_callback, name='schedule_callback'),
]
"""

# ============================================================================
# leads/urls.py
# ============================================================================
"""
from django.urls import path
from . import views
from . import views_progress  # New file for Phase 2.4

app_name = 'leads'

urlpatterns = [
    # Existing URLs
    path('', views.lead_list, name='list'),
    path('lists/', views.lead_lists, name='lists'),
    path('lists/<int:list_id>/', views.lead_list_detail, name='list_detail'),
    path('lists/<int:list_id>/leads/', views.list_leads, name='list_leads'),
    path('<int:pk>/', views.lead_detail, name='detail'),
    path('import/', views.import_leads, name='import'),
    path('export/<int:list_id>/', views.export_list, name='export_list'),
    
    # Phase 2.4: Progress Tracking
    path('lists/<int:list_id>/progress/', views_progress.lead_list_detail_with_progress, name='list_progress'),
    path('api/lists/<int:list_id>/progress/', views_progress.lead_list_progress_api, name='list_progress_api'),
    
    # Phase 2.4: Recycling
    path('lists/<int:list_id>/recycle/', views_progress.recycle_list_leads, name='recycle_list_leads'),
    path('recycle-rules/', views_progress.recycle_rules_list, name='recycle_rules'),
    path('recycle-rules/create/', views_progress.create_recycle_rule, name='create_recycle_rule'),
    path('recycle-rules/<int:rule_id>/toggle/', views_progress.toggle_recycle_rule, name='toggle_recycle_rule'),
    path('recycle-rules/<int:rule_id>/delete/', views_progress.delete_recycle_rule, name='delete_recycle_rule'),
]
"""

# ============================================================================
# telephony/urls.py
# ============================================================================
"""
from django.urls import path
from . import views
from . import views_recording  # New file for Phase 2.5

app_name = 'telephony'

urlpatterns = [
    # Existing URLs
    path('', views.dashboard, name='dashboard'),
    path('servers/', views.server_list, name='servers'),
    path('servers/<int:pk>/', views.server_detail, name='server_detail'),
    path('phones/', views.phone_list, name='phones'),
    
    # Phase 2.5: Recordings
    path('recordings/<int:call_id>/stream/', views_recording.stream_recording, name='stream_recording'),
    path('recordings/<int:call_id>/download/', views_recording.download_recording, name='download_recording'),
    path('api/recordings/', views_recording.recording_list, name='recording_list'),
    path('api/recordings/stats/', views_recording.recording_stats, name='recording_stats'),
]
"""

# ============================================================================
# Main Project urls.py
# ============================================================================
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('agents/', include('agents.urls')),
    path('campaigns/', include('campaigns.urls')),
    path('leads/', include('leads.urls')),
    path('calls/', include('calls.urls')),
    path('telephony/', include('telephony.urls')),
    path('reports/', include('reports.urls')),
    path('users/', include('users.urls')),
]
"""
