# users/urls.py

from django.urls import path
from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView
from . import views

app_name = 'users'

urlpatterns = [
    # Auth
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),

    # Profile
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change_password'),

    # ── NEW: Agent time monitoring report ─────────────────────────────────
    # ── NEW: Agent time monitoring report ─────────────────────────────────
    path('api/agent-time-report/', views.agent_time_report_api, name='agent_time_report'),

    # User Management
    path('list/', views.UserListView.as_view(), name='list'),
    path('create/', views.UserCreateView.as_view(), name='create'),
    path('<int:pk>/', views.UserDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.UserUpdateView.as_view(), name='edit'),
    path('ajax/status/', views.user_status_ajax, name='ajax_status'),
]
