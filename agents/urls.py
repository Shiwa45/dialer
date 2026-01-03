from django.urls import path
from . import views_simple

app_name = 'agents'

urlpatterns = [
    path('', views_simple.agent_dashboard, name='dashboard'),
    path('status/update/', views_simple.update_status, name='update_status'),
    path('call/status/', views_simple.call_status, name='call_status'),
    path('dial/manual/', views_simple.manual_dial, name='manual_dial'),
    path('call/hangup/', views_simple.hangup_call, name='hangup_call'),
    path('call/answer/', views_simple.answer_call, name='answer_call'),
    path('call/transfer/', views_simple.transfer_call, name='transfer_call'),
    path('call/hold/', views_simple.hold_call, name='hold_call'),
    path('call/disposition/', views_simple.set_disposition, name='set_disposition'),
    path('call/next_lead/', views_simple.get_next_lead, name='get_next_lead'),
    path('lead/info/', views_simple.get_lead_info, name='get_lead_info'),
    path('lead/save/', views_simple.save_lead_info, name='save_lead_info'),
    path('callbacks/pending/', views_simple.pending_callbacks, name='pending_callbacks'),
    path('callbacks/complete/', views_simple.complete_callback, name='complete_callback'),
    path('callbacks/reschedule/', views_simple.reschedule_callback, name='reschedule_callback'),
    path('callback/schedule/', views_simple.schedule_callback, name='schedule_callback'),
    path('statistics/', views_simple.agent_statistics, name='statistics'),
    path('call/make/', views_simple.make_call, name='make_call'),
    path('phone/register/', views_simple.register_phone, name='register_phone'),
    path('webrtc/config/', views_simple.get_webrtc_config, name='get_webrtc_config'),
]
