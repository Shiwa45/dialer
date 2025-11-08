from django.urls import path
from . import views_simple as views

app_name = 'agents'

urlpatterns = [
    # Main agent dashboard - integrated with telephony
    path('', views.agent_dashboard, name='dashboard'),

    # Simplified dialing (on-demand); removed persistent session routes
    path('dial/manual/', views.manual_dial, name='manual_dial'),
    
    # Phone registration and setup
    path('phone/register/', views.register_phone, name='register_phone'),
    path('phone/status/', views.call_status, name='call_status'),
    
    # Call management (integrated with telephony system)
    path('call/make/', views.make_call, name='make_call'),
    path('call/answer/', views.answer_call, name='answer_call'),
    path('call/hangup/', views.hangup_call, name='hangup_call'),
    path('call/transfer/', views.transfer_call, name='transfer_call'),
    path('call/hold/', views.hold_call, name='hold_call'),
    
    # Lead management for dialing
    path('lead/next/', views.get_next_lead, name='get_next_lead'),
    path('lead/save/', views.save_lead_info, name='save_lead_info'),
    path('lead/get/', views.get_lead_info, name='get_lead_info'),
    
    # Status management  
    path('status/update/', views.update_status, name='update_status'),
    
    # Callback management
    path('callbacks/', views.pending_callbacks, name='pending_callbacks'),
    path('callbacks/complete/', views.complete_callback, name='complete_callback'),
    path('callbacks/reschedule/', views.reschedule_callback, name='reschedule_callback'),
    
    # Statistics
    path('stats/', views.agent_statistics, name='agent_statistics'),
]
