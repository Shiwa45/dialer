# agents/urls.py
# UPDATED: adds heartbeat, wrapup-state, can-logout endpoints

from django.urls import path
from . import views_simple

app_name = 'agents'

urlpatterns = [
    # ── Dashboard ──────────────────────────────────────────────────────────
    path('', views_simple.simple_dashboard, name='dashboard'),
    path('dashboard/', views_simple.simple_dashboard, name='simple_dashboard'),

    # ── Status Management ──────────────────────────────────────────────────
    path('api/update-status/', views_simple.update_status, name='update_status'),
    path('api/status/', views_simple.get_call_status, name='get_status'),

    # ── Call Management ────────────────────────────────────────────────────
    path('api/call-status/', views_simple.get_call_status, name='call_status'),
    path('api/set-disposition/', views_simple.set_disposition, name='set_disposition'),
    path('api/hangup/', views_simple.hangup_call, name='hangup'),

    # ── Lead Information ───────────────────────────────────────────────────
    path('api/lead-info/', views_simple.get_lead_info, name='get_lead_info'),

    # ── Statistics ─────────────────────────────────────────────────────────
    path('api/statistics/', views_simple.agent_statistics, name='statistics'),

    # ── WebRTC Configuration ───────────────────────────────────────────────
    path('api/webrtc-config/', views_simple.get_webrtc_config, name='get_webrtc_config'),

    # ── NEW: Heartbeat (zombie prevention) ────────────────────────────────
    path('api/heartbeat/', views_simple.agent_heartbeat, name='heartbeat'),

    # ── NEW: Wrapup state (call persistence across refresh) ───────────────
    path('api/wrapup-state/', views_simple.get_wrapup_state, name='wrapup_state'),

    # ── Pre-logout check (blocks logout during wrapup) ───────────────────
    path('api/can-logout/',   views_simple.can_logout,         name='can_logout'),

    # ── Agent own status-info (seeds panel timer accurately) ─────────────
    path('api/status-info/',  views_simple.agent_status_info,  name='status_info'),

    # ── Force logout — supervisor/admin only ─────────────────────────────
    path('api/force-logout/', views_simple.force_logout_agent, name='force_logout'),
]

# ── Call History Module (Phase 2.2) ───────────────────────────────────────
# ── Call History Module (Phase 2.2) ───────────────────────────────────────
from . import views_call_history  # noqa: E402

urlpatterns += [
    path('call-history/', views_call_history.call_history_page, name='call_history_page'),
    path('api/history-full/', views_call_history.call_history_api, name='call_history_api'),
    path('api/history-stats/', views_call_history.call_history_stats, name='call_history_stats'),
    path('api/call-details/<int:call_id>/', views_call_history.call_details_api, name='call_details_api'),
    path('api/schedule-callback/', views_call_history.schedule_callback, name='schedule_callback'),
]

# ── Admin Agent History (Phase 6) ─────────────────────────────────────────
from . import views_admin_history

urlpatterns += [
    path('admin/history/', views_admin_history.agent_history_index, name='agent_history_index'),
    path('admin/history/<int:agent_id>/', views_admin_history.agent_history_detail, name='agent_history_detail'),
    path('admin/history/<int:agent_id>/export/', views_admin_history.agent_history_export, name='agent_history_export'),
    path('api/admin/history/<int:agent_id>/', views_admin_history.agent_history_api, name='agent_history_api'),
]
