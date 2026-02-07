# leads/urls.py

from django.urls import path
from . import views

app_name = 'leads'

urlpatterns = [
    # Lead management
    path('', views.LeadListView.as_view(), name='list'),
    path('create/', views.LeadCreateView.as_view(), name='create'),
    path('<int:pk>/', views.LeadDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.LeadUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.LeadDeleteView.as_view(), name='delete'),
    
    # Lead List management
    path('lists/', views.LeadListListView.as_view(), name='lead_lists'),
    path('lists/create/', views.LeadListCreateView.as_view(), name='create_lead_list'),
    path('lists/<int:pk>/', views.LeadListDetailView.as_view(), name='lead_list_detail'),
    path('lists/<int:pk>/edit/', views.LeadListUpdateView.as_view(), name='update_lead_list'),
    path('lists/<int:pk>/delete/', views.LeadListDeleteView.as_view(), name='delete_lead_list'),
    path('lists/<int:pk>/leads/', views.LeadListLeadsView.as_view(), name='lead_list_leads'),
    path('lists/<int:pk>/recycle/', views.RecycleLeadsView.as_view(), name='recycle_leads'),
    
    # Lead Import/Export
    path('import/', views.LeadImportView.as_view(), name='import'),
    path('import/<int:pk>/', views.LeadImportDetailView.as_view(), name='import_detail'),
    path('import/<int:pk>/status/', views.lead_import_status, name='import_status'),
    path('export/', views.lead_export, name='export'),
    path('lists/<int:pk>/export/', views.lead_list_export, name='lead_list_export'),
    
    # DNC Management
    path('listsdnc/', views.DNCListView.as_view(), name='dnc_list'),
    path('dnc/create/', views.DNCCreateView.as_view(), name='create_dnc'),
    path('dnc/export/', views.dnc_export, name='export_dnc'),
    path('dnc/check/', views.dnc_check, name='check_dnc'),
    
    # Callbacks
    path('callbacks/', views.CallbackListView.as_view(), name='callbacks'),
    path('callbacks/create/', views.CallbackCreateView.as_view(), name='create_callback'),
    path('callbacks/<int:pk>/complete/', views.complete_callback, name='complete_callback'),
    path('callbacks/upcoming/', views.upcoming_callbacks, name='upcoming_callbacks'),
    
    # AJAX endpoints
    path('ajax/search/', views.lead_search_ajax, name='search_ajax'),
    path('ajax/validate-phone/', views.validate_phone_ajax, name='validate_phone'),
    path('ajax/duplicate-check/', views.duplicate_check_ajax, name='duplicate_check'),
    path('ajax/bulk-action/', views.bulk_action_ajax, name='bulk_action'),
    
    # API endpoints for real-time updates
    path('api/stats/', views.lead_stats_api, name='stats_api'),
    path('api/import-progress/<int:pk>/', views.import_progress_api, name='import_progress_api'),
]

# Phase 2.4: Lead Recycle & Progress Tracking
from . import views_progress

urlpatterns += [
    path('lists/<int:list_id>/progress/', views_progress.lead_list_detail_with_progress, name='list_progress'),
    path('api/lists/<int:list_id>/progress/', views_progress.lead_list_progress_api, name='list_progress_api'),
    path('lists/<int:list_id>/recycle/', views_progress.recycle_list_leads, name='recycle_list_leads'),
    path('recycle-rules/', views_progress.recycle_rules_list, name='recycle_rules'),
    path('recycle-rules/create/', views_progress.create_recycle_rule, name='create_recycle_rule'),
    path('recycle-rules/<int:rule_id>/toggle/', views_progress.toggle_recycle_rule, name='toggle_recycle_rule'),
    path('recycle-rules/<int:rule_id>/delete/', views_progress.delete_recycle_rule, name='delete_recycle_rule'),
]