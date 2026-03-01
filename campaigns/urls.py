# campaigns/urls.py

from django.urls import path
from . import views
from . import views_ai

app_name = 'campaigns'

urlpatterns = [
    # Main campaign views
    path('', views.CampaignListView.as_view(), name='list'),
    path('create/', views.CampaignCreateView.as_view(), name='create'),
    path('<int:pk>/', views.CampaignDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.CampaignUpdateView.as_view(), name='update'),
    
    # Campaign control
    path('<int:pk>/control/', views.campaign_control, name='control'),
    path('<int:pk>/clone/', views.clone_campaign, name='clone'),
    
    # Agent management
    path('<int:pk>/agents/', views.CampaignAgentManagementView.as_view(), name='agents'),
    
    # Script management
    path('<int:pk>/scripts/', views.script_management, name='scripts'),
    
    # Disposition management
    path('<int:pk>/dispositions/', views.DispositionManagementView.as_view(), name='dispositions'),
    
    # API endpoints
    path('<int:pk>/api/stats/', views.campaign_stats_api, name='stats_api'),
    
    # Additional management views (we'll add these later)
    # path('<int:pk>/hours/', views.CampaignHoursView.as_view(), name='hours'),
    # path('<int:pk>/leads/', views.CampaignLeadsView.as_view(), name='leads'),
    # path('<int:pk>/reports/', views.CampaignReportsView.as_view(), name='reports'),
    
    # Phase 8.3: AI Agent Configurations
    path('<int:campaign_id>/ai-config/', views_ai.ai_agent_config, name='ai_agent_config'),
    path('<int:campaign_id>/ai-toggle/', views_ai.toggle_ai_enabled, name='toggle_ai_enabled'),
    path('<int:campaign_id>/test-ai-call/', views_ai.test_ai_call, name='test_ai_call'),
    path('<int:campaign_id>/ai-calls/', views_ai.ai_call_history, name='ai_call_history'),
    path('ai-calls/<int:call_id>/transcript/', views_ai.ai_call_transcript, name='ai_call_transcript'),
    path('<int:campaign_id>/ai-stats/', views_ai.ai_stats_api, name='ai_stats_api'),
]