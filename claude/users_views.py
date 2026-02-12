# users/views.py
#
# UPDATED: WebRTC vs Softphone login enforcement
# - WebRTC agents: always allowed (browser registers JsSIP after login)
# - Non-WebRTC agents: must have softphone registered on Asterisk
# - Superusers/staff: always allowed
#
# IMPORTANT: Replace ONLY the CustomLoginView class in your existing users/views.py.
# Keep all other views (CustomLogoutView, user management, etc.) unchanged.

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.contrib.auth.views import LoginView as BaseLoginView, LogoutView as BaseLogoutView
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views import View
from django.urls import reverse_lazy
from django.utils import timezone
from core.decorators import supervisor_required, role_required
from .models import UserProfile, UserSession, AgentStatus
from .forms import CustomUserCreationForm, UserProfileForm, CustomPasswordChangeForm, UserSearchForm
import logging
import json

logger = logging.getLogger(__name__)


class CustomLoginView(BaseLoginView):
    """
    Custom login view with phone registration enforcement.

    Logic:
    - Superusers / staff → always allowed
    - Agent with NO extension → blocked
    - Agent with WebRTC-enabled phone → allowed (browser registers via JsSIP)
    - Agent with non-WebRTC phone → check Asterisk for softphone registration
    """
    template_name = 'users/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        user = form.get_user()

        # Skip all checks for superusers and staff (admin/supervisor)
        if not user.is_superuser and not user.is_staff:
            if hasattr(user, 'profile') and user.profile.is_agent():
                extension = (user.profile.extension or '').strip()

                if not extension:
                    messages.error(
                        self.request,
                        'Your account does not have an extension assigned. '
                        'Please contact your supervisor.'
                    )
                    return self.form_invalid(form)

                # Find agent's phone record
                from telephony.models import Phone
                phone = Phone.objects.filter(user=user, is_active=True).first()
                if not phone:
                    phone = Phone.objects.filter(extension=extension, is_active=True).first()

                if phone and phone.webrtc_enabled:
                    # WebRTC agent → allow login, JsSIP registers in browser
                    pass
                else:
                    # Non-WebRTC agent → must have softphone registered
                    from telephony.models import AsteriskServer
                    from telephony.services import AsteriskService

                    try:
                        server = AsteriskServer.objects.filter(is_active=True).first()
                        if server:
                            service = AsteriskService(server)
                            status = service.get_endpoint_status(extension)

                            if not status.get('registered', False):
                                messages.error(
                                    self.request,
                                    f'Your extension ({extension}) is not registered. '
                                    f'Please connect your softphone before logging in.'
                                )
                                return self.form_invalid(form)
                    except Exception as e:
                        # Fail open: if Asterisk is unreachable, allow login
                        logger.error(f"Extension check failed for {user.username}: {e}")

        # Log the user in
        response = super().form_valid(form)

        # Create user session record
        UserSession.objects.create(
            user=self.request.user,
            session_key=self.request.session.session_key,
            ip_address=self.get_client_ip(),
            user_agent=self.request.META.get('HTTP_USER_AGENT', '')[:500]
        )

        # Set agent status to available
        if hasattr(self.request.user, 'profile') and self.request.user.profile.is_agent():
            agent_status, _ = AgentStatus.objects.get_or_create(user=self.request.user)
            agent_status.set_status('available')

        messages.success(
            self.request,
            f'Welcome back, {self.request.user.get_full_name() or self.request.user.username}!'
        )
        return response

    def get_client_ip(self):
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return self.request.META.get('REMOTE_ADDR')


class CustomLogoutView(View):
    """Custom logout view with session cleanup"""
    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            try:
                session = UserSession.objects.filter(
                    user=request.user,
                    session_key=request.session.session_key,
                    is_active=True
                ).first()
                if session:
                    session.logout_time = timezone.now()
                    session.is_active = False
                    session.save()
            except Exception as e:
                logger.error(f"Logout cleanup error: {e}")

            try:
                if hasattr(request.user, 'agent_status'):
                    request.user.agent_status.set_status('offline')
            except Exception:
                pass

        logout(request)
        messages.info(request, 'You have been successfully logged out.')
        return redirect('login')

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)
