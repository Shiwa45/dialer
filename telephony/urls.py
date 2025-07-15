# telephony/urls.py

from django.urls import path
from . import views

app_name = 'telephony'

urlpatterns = [
    # Main dashboard
    path('', views.telephony_dashboard, name='dashboard'),
    
    # Asterisk Server Management
    path('servers/', views.AsteriskServerListView.as_view(), name='asterisk_servers'),
    path('servers/create/', views.AsteriskServerCreateView.as_view(), name='create_asterisk_server'),
    path('servers/<int:pk>/', views.AsteriskServerDetailView.as_view(), name='asterisk_server_detail'),
    path('servers/<int:pk>/edit/', views.AsteriskServerUpdateView.as_view(), name='update_asterisk_server'),
    path('servers/<int:pk>/delete/', views.AsteriskServerDeleteView.as_view(), name='delete_asterisk_server'),
    path('servers/<int:pk>/test/', views.test_asterisk_connection, name='test_asterisk_connection'),
    
    # Carrier Management
    path('carriers/', views.CarrierListView.as_view(), name='carriers'),
    path('carriers/create/', views.CarrierCreateView.as_view(), name='create_carrier'),
    path('carriers/<int:pk>/', views.CarrierDetailView.as_view(), name='carrier_detail'),
    path('carriers/<int:pk>/edit/', views.CarrierUpdateView.as_view(), name='update_carrier'),
    path('carriers/<int:pk>/delete/', views.CarrierDeleteView.as_view(), name='delete_carrier'),
    
    # DID Management
    path('dids/', views.DIDListView.as_view(), name='dids'),
    path('dids/create/', views.DIDCreateView.as_view(), name='create_did'),
    path('dids/<int:pk>/', views.DIDDetailView.as_view(), name='did_detail'),
    path('dids/<int:pk>/edit/', views.DIDUpdateView.as_view(), name='update_did'),
    path('dids/<int:pk>/delete/', views.DIDDeleteView.as_view(), name='delete_did'),
    path('dids/bulk-import/', views.BulkDIDImportView.as_view(), name='bulk_import_dids'),
    
    # Phone/Extension Management (Enhanced with Asterisk Auto-Sync)
    path('phones/', views.PhoneListView.as_view(), name='phones'),
    path('phones/create/', views.PhoneCreateView.as_view(), name='create_phone'),
    path('phones/<int:pk>/', views.PhoneDetailView.as_view(), name='phone_detail'),
    path('phones/<int:pk>/edit/', views.PhoneUpdateView.as_view(), name='update_phone'),
    path('phones/<int:pk>/delete/', views.PhoneDeleteView.as_view(), name='delete_phone'),
    path('phones/bulk-create/', views.BulkPhoneCreateView.as_view(), name='bulk_create_phones'),
    
    # Phone Status and Control
    path('phones/<int:pk>/status/', views.phone_status, name='phone_status'),
    path('phones/<int:pk>/config/', views.phone_config, name='phone_config'),
    path('phones/<int:pk>/reset-secret/', views.reset_phone_secret, name='reset_phone_secret'),
    path('phones/<int:pk>/toggle-status/', views.toggle_phone_status, name='toggle_phone_status'),
    path('phones/<int:pk>/confirm-delete/', views.phone_confirm_delete, name='phone_confirm_delete'),
    
    # Asterisk Sync Management
    path('phones/sync-all/', views.sync_all_phones_to_asterisk, name='sync_all_phones'),
    path('phones/cleanup-orphans/', views.cleanup_asterisk_orphans, name='cleanup_orphans'),
    
    # IVR Management
    path('ivrs/', views.IVRListView.as_view(), name='ivrs'),
    path('ivrs/create/', views.IVRCreateView.as_view(), name='create_ivr'),
    path('ivrs/<int:pk>/', views.IVRDetailView.as_view(), name='ivr_detail'),
    path('ivrs/<int:pk>/edit/', views.IVRUpdateView.as_view(), name='update_ivr'),
    path('ivrs/<int:pk>/delete/', views.IVRDeleteView.as_view(), name='delete_ivr'),
    path('ivrs/<int:pk>/options/', views.IVROptionManagementView.as_view(), name='ivr_options'),
    path('ivrs/<int:ivr_pk>/options/create/', views.IVROptionCreateView.as_view(), name='create_ivr_option'),
    path('ivr-options/<int:pk>/edit/', views.IVROptionUpdateView.as_view(), name='update_ivr_option'),
    path('ivr-options/<int:pk>/delete/', views.IVROptionDeleteView.as_view(), name='delete_ivr_option'),
    
    # Call Queue Management
    path('queues/', views.CallQueueListView.as_view(), name='queues'),
    path('queues/create/', views.CallQueueCreateView.as_view(), name='create_queue'),
    path('queues/<int:pk>/', views.CallQueueDetailView.as_view(), name='queue_detail'),
    path('queues/<int:pk>/edit/', views.CallQueueUpdateView.as_view(), name='update_queue'),
    path('queues/<int:pk>/delete/', views.CallQueueDeleteView.as_view(), name='delete_queue'),
    path('queues/<int:pk>/members/', views.QueueMemberManagementView.as_view(), name='queue_members'),
    path('queues/<int:queue_pk>/members/add/', views.QueueMemberAddView.as_view(), name='add_queue_member'),
    path('queue-members/<int:pk>/delete/', views.QueueMemberDeleteView.as_view(), name='delete_queue_member'),
    
    # Recording Management
    path('recordings/', views.RecordingListView.as_view(), name='recordings'),
    path('recordings/<int:pk>/', views.RecordingDetailView.as_view(), name='recording_detail'),
    path('recordings/<int:pk>/download/', views.download_recording, name='download_recording'),
    path('recordings/<int:pk>/play/', views.play_recording, name='play_recording'),
    path('recordings/<int:pk>/delete/', views.RecordingDeleteView.as_view(), name='delete_recording'),
    
    # Dialplan Management
    path('dialplan/contexts/', views.DialplanContextListView.as_view(), name='dialplan_contexts'),
    path('dialplan/contexts/create/', views.DialplanContextCreateView.as_view(), name='create_dialplan_context'),
    path('dialplan/contexts/<int:pk>/', views.DialplanContextDetailView.as_view(), name='dialplan_context_detail'),
    path('dialplan/contexts/<int:pk>/edit/', views.DialplanContextUpdateView.as_view(), name='update_dialplan_context'),
    path('dialplan/contexts/<int:pk>/delete/', views.DialplanContextDeleteView.as_view(), name='delete_dialplan_context'),
    path('dialplan/contexts/<int:context_pk>/extensions/create/', views.DialplanExtensionCreateView.as_view(), name='create_dialplan_extension'),
    path('dialplan/extensions/<int:pk>/edit/', views.DialplanExtensionUpdateView.as_view(), name='update_dialplan_extension'),
    path('dialplan/extensions/<int:pk>/delete/', views.DialplanExtensionDeleteView.as_view(), name='delete_dialplan_extension'),
    
    # WebRTC Management
    path('webrtc/config/', views.webrtc_config, name='webrtc_config'),
    path('webrtc/phone-config/', views.WebRTCPhoneConfigView.as_view(), name='webrtc_phone_config'),
    
    # Call Control
    path('calls/originate/', views.originate_call, name='originate_call'),
    path('calls/hangup/', views.hangup_call, name='hangup_call'),
    path('calls/transfer/', views.transfer_call, name='transfer_call'),
    path('calls/park/', views.park_call, name='park_call'),
    
    # API Endpoints
    path('api/stats/', views.telephony_stats_api, name='stats_api'),
    path('api/servers/<int:pk>/status/', views.server_status_api, name='server_status_api'),
    path('api/phones/available/', views.available_phones_api, name='available_phones_api'),
    path('api/extensions/validate/', views.validate_extension_api, name='validate_extension_api'),
    path('api/dids/check/', views.check_did_availability_api, name='check_did_availability_api'),
    
    # Real-time monitoring
    path('monitor/servers/', views.ServerMonitorView.as_view(), name='monitor_servers'),
    path('monitor/calls/', views.CallMonitorView.as_view(), name='monitor_calls'),
    path('monitor/queues/', views.QueueMonitorView.as_view(), name='monitor_queues'),
    
    # Configuration export/import
    path('config/export/', views.export_telephony_config, name='export_config'),
    path('config/import/', views.ImportTelephonyConfigView.as_view(), name='import_config'),
    
    # System diagnostics
    path('diagnostics/', views.TelephonyDiagnosticsView.as_view(), name='diagnostics'),
    path('diagnostics/connectivity/', views.connectivity_test, name='connectivity_test'),
    path('diagnostics/performance/', views.performance_test, name='performance_test'),
]