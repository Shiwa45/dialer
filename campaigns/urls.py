# campaigns/urls.py

from django.urls import path
from . import views

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
]