# users/views.py
#
# UPDATED v3:
# - Multi-device login prevention for agents
# - WebRTC vs Softphone login enforcement
# - Session invalidation on new login
#
# IMPORTANT: Replace ONLY CustomLoginView and CustomLogoutView.
# Keep all other views unchanged.

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.contrib.auth.views import LoginView as BaseLoginView, LogoutView as BaseLogoutView
from django.contrib import messages
from django.contrib.sessions.models import Session as DjangoSession
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
    Custom login view with:
    1. Multi-device prevention (agents can only be logged in on ONE device)
    2. WebRTC agents: always allowed
    3. Non-WebRTC agents: softphone must be registered
    4. Superusers/staff: always allowed
    """
    template_name = 'users/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        user = form.get_user()
        is_agent = hasattr(user, 'profile') and user.profile.is_agent()

        # ── AGENT CHECKS (skip for superusers/staff) ────────────────
        if not user.is_superuser and not user.is_staff and is_agent:
            extension = (user.profile.extension or '').strip()

            if not extension:
                messages.error(
                    self.request,
                    'Your account does not have an extension assigned. '
                    'Please contact your supervisor.'
                )
                return self.form_invalid(form)

            # ── MULTI-DEVICE CHECK ──────────────────────────────────
            # Kill ALL existing active sessions for this agent
            active_sessions = UserSession.objects.filter(
                user=user, is_active=True
            )
            if active_sessions.exists():
                for old_session in active_sessions:
                    # Invalidate the Django session itself
                    try:
                        DjangoSession.objects.filter(
                            session_key=old_session.session_key
                        ).delete()
                    except Exception:
                        pass
                    old_session.is_active = False
                    old_session.logout_time = timezone.now()
                    old_session.save()

                # Set agent offline on old session
                try:
                    agent_status = AgentStatus.objects.filter(user=user).first()
                    if agent_status:
                        agent_status.set_status('offline')
                except Exception:
                    pass

                logger.info(
                    f"Agent {user.username} had {active_sessions.count()} active "
                    f"session(s) — all terminated for new login from "
                    f"{self.get_client_ip()}"
                )

            # ── PHONE / WEBRTC CHECK ────────────────────────────────
            from telephony.models import Phone
            phone = Phone.objects.filter(user=user, is_active=True).first()
            if not phone:
                phone = Phone.objects.filter(
                    extension=extension, is_active=True
                ).first()

            if phone and phone.webrtc_enabled:
                # WebRTC agent → always allow, browser registers via JsSIP
                pass
            else:
                # Non-WebRTC agent → softphone must be registered
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
                    # Fail open if Asterisk is unreachable
                    logger.error(
                        f"Extension check failed for {user.username}: {e}"
                    )

        # ── LOG THE USER IN ─────────────────────────────────────────
        response = super().form_valid(form)

        # Ensure session exists
        if not self.request.session.session_key:
            self.request.session.create()

        # Create session tracking record
        try:
            UserSession.objects.create(
                user=self.request.user,
                session_key=self.request.session.session_key,
                ip_address=self.get_client_ip(),
                user_agent=self.request.META.get('HTTP_USER_AGENT', '')[:500]
            )
        except Exception as e:
            logger.error(f"Failed to create UserSession: {e}")

        # Set agent status
        if is_agent:
            try:
                agent_status, _ = AgentStatus.objects.get_or_create(
                    user=self.request.user
                )
                agent_status.set_status('available')
            except Exception:
                pass

        messages.success(
            self.request,
            f'Welcome back, '
            f'{self.request.user.get_full_name() or self.request.user.username}!'
        )
        return response

    def get_client_ip(self):
        xff = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return self.request.META.get('REMOTE_ADDR', '0.0.0.0')


class CustomLogoutView(View):
    """Custom logout with session cleanup"""

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            try:
                UserSession.objects.filter(
                    user=request.user,
                    session_key=request.session.session_key,
                    is_active=True
                ).update(
                    is_active=False,
                    logout_time=timezone.now()
                )
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
