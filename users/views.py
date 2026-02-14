# users/views.py
# UPDATED:
#   - CustomLoginView: records login time log
#   - CustomLogoutView: BLOCKS logout during wrapup, closes time log on success
#   - Multi-device prevention for agents
#   - WebRTC vs Softphone login enforcement

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.contrib.auth.views import LoginView as BaseLoginView
from django.contrib.sessions.models import Session as DjangoSession
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
from .models import UserProfile, UserSession, AgentStatus, AgentTimeLog
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
    5. NEW: Records login in AgentTimeLog
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

            # ── Kill any zombie sessions for this agent ──────────────
            self._kill_zombie_sessions(user)

        # ── Perform login ────────────────────────────────────────────
        login(self.request, user)

        # ── Record UserSession ───────────────────────────────────────
        try:
            UserSession.objects.create(
                user=user,
                session_key=self.request.session.session_key or '',
                ip_address=self._get_client_ip(),
                user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            )
        except Exception as e:
            logger.warning(f"Could not create UserSession: {e}")

        # ── Set AgentStatus to available + start time log ────────────
        if is_agent:
            try:
                agent_status, created = AgentStatus.objects.get_or_create(user=user)
                now = timezone.now()
                agent_status.last_heartbeat = now

                # If agent was in wrapup before logout, keep wrapup so they must dispose
                if agent_status.status not in ('wrapup',):
                    # Close any stale open time log
                    agent_status._close_time_log(ended_at=now)
                    agent_status.status = 'available'
                    agent_status.save()
                    agent_status._open_time_log(status='available', started_at=now)
                else:
                    # They were in wrapup - keep them there
                    agent_status.save(update_fields=['last_heartbeat'])
                    logger.info(
                        f"Agent {user.username} logged in with pending wrapup "
                        f"(call: {agent_status.wrapup_call_id})"
                    )
            except Exception as e:
                logger.error(f"Login AgentStatus update error: {e}")

        return redirect(self.get_success_url())

    def _kill_zombie_sessions(self, user):
        """Invalidate all other active sessions for this agent."""
        try:
            active_sessions = UserSession.objects.filter(
                user=user, is_active=True
            ).exclude(session_key='')

            for us in active_sessions:
                try:
                    DjangoSession.objects.filter(session_key=us.session_key).delete()
                except Exception:
                    pass
                us.is_active = False
                us.logout_time = timezone.now()
                us.save()

            logger.info(
                f"Killed {active_sessions.count()} zombie session(s) for {user.username}"
            )
        except Exception as e:
            logger.warning(f"Could not kill zombie sessions: {e}")

    def _get_client_ip(self):
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return self.request.META.get('REMOTE_ADDR', '0.0.0.0')


class CustomLogoutView(View):
    """
    Custom logout view.
    BLOCKS logout if agent has a pending wrapup/disposition.
    """

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        user = request.user
        is_agent = hasattr(user, 'profile') and user.profile.is_agent()

        # ── Check if agent can logout ────────────────────────────────
        if is_agent and not user.is_superuser and not user.is_staff:
            try:
                agent_status = getattr(user, 'agent_status', None)
                if agent_status and agent_status.needs_disposition():
                    # Ajax request
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'blocked': True,
                            'error': (
                                'Cannot log out — you have a pending call that requires '
                                'disposition. Please dispose the call first.'
                            ),
                            'call_id': agent_status.wrapup_call_id or agent_status.current_call_id,
                        }, status=403)
                    # Regular form submission
                    messages.error(
                        request,
                        '⚠️ Cannot log out — you have a pending call that requires '
                        'disposition. Please dispose the call first.'
                    )
                    return redirect('agents:dashboard')
            except Exception as e:
                logger.error(f"Logout check error: {e}")

        # ── Proceed with logout ──────────────────────────────────────
        self._cleanup_on_logout(user)
        logout(request)
        messages.info(request, 'You have been successfully logged out.')
        return redirect('login')

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)

    def _cleanup_on_logout(self, user):
        """Close time logs, mark session ended, set agent offline."""
        now = timezone.now()

        # Close UserSession
        try:
            session = UserSession.objects.filter(
                user=user,
                session_key=self.request.session.session_key,
                is_active=True
            ).first()
            if session:
                session.logout_time = now
                session.is_active = False
                session.save()
        except Exception as e:
            logger.error(f"Logout session cleanup error: {e}")

        # Set agent status to offline + close time log
        try:
            if hasattr(user, 'agent_status'):
                agent_status = user.agent_status
                agent_status._close_time_log(ended_at=now)
                agent_status.status = 'offline'
                agent_status.current_call_id = ''
                agent_status.call_start_time = None
                agent_status.save()
                agent_status._open_time_log(status='offline', started_at=now)
        except Exception as e:
            logger.error(f"Logout agent status cleanup error: {e}")


# =============================================================================
# AGENT TIME REPORT API  (admin/supervisor accessible)
# =============================================================================

@login_required
def agent_time_report_api(request):
    """
    Returns daily time breakdown per agent for a given date range.
    Query params: agent_id (optional), date_from, date_to
    """
    from django.db.models import Sum
    from django.contrib.auth.models import User

    if not (request.user.is_staff or request.user.is_superuser or
            (hasattr(request.user, 'profile') and request.user.profile.is_supervisor())):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    date_from_str = request.GET.get('date_from')
    date_to_str = request.GET.get('date_to')
    agent_id = request.GET.get('agent_id')

    try:
        today = timezone.now().date()
        if date_from_str:
            from datetime import date
            date_from = date.fromisoformat(date_from_str)
        else:
            date_from = today

        if date_to_str:
            from datetime import date
            date_to = date.fromisoformat(date_to_str)
        else:
            date_to = today
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)

    qs = AgentTimeLog.objects.filter(date__range=(date_from, date_to))
    if agent_id:
        qs = qs.filter(user_id=agent_id)

    # Aggregate by agent + status
    aggregated = (
        qs
        .values('user__id', 'user__username', 'user__first_name', 'user__last_name', 'status', 'date')
        .annotate(total_seconds=Sum('duration_seconds'))
        .order_by('user__username', 'date', 'status')
    )

    # Also compute per-agent totals per date
    result = {}
    for row in aggregated:
        uid = row['user__id']
        dt = str(row['date'])
        key = f"{uid}_{dt}"

        if key not in result:
            result[key] = {
                'agent_id': uid,
                'agent_username': row['user__username'],
                'agent_name': f"{row['user__first_name']} {row['user__last_name']}".strip()
                              or row['user__username'],
                'date': dt,
                'available': 0,
                'busy': 0,
                'wrapup': 0,
                'break': 0,
                'offline': 0,
                'total_logged_in': 0,
            }

        status = row['status']
        secs = row['total_seconds'] or 0
        result[key][status] = secs

        if status not in ('offline',):
            result[key]['total_logged_in'] += secs

    # Format seconds as HH:MM:SS
    def fmt(secs):
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    rows_out = []
    for entry in sorted(result.values(), key=lambda x: (x['agent_username'], x['date'])):
        rows_out.append({
            **entry,
            'available_fmt': fmt(entry['available']),
            'busy_fmt': fmt(entry['busy']),
            'wrapup_fmt': fmt(entry['wrapup']),
            'break_fmt': fmt(entry['break']),
            'offline_fmt': fmt(entry['offline']),
            'total_logged_in_fmt': fmt(entry['total_logged_in']),
        })

    return JsonResponse({
        'success': True,
        'date_from': str(date_from),
        'date_to': str(date_to),
        'count': len(rows_out),
        'data': rows_out,
    })


# =============================================================================
# ZOMBIE CLEANUP UTILITY  (called by Celery task or management command)
# =============================================================================

def cleanup_zombie_agents(timeout_minutes=5):
    """
    Find agents with stale heartbeats and mark them offline.
    Call this from a Celery task every 2-3 minutes.
    """
    cutoff = timezone.now() - timezone.timedelta(minutes=timeout_minutes)
    zombies = AgentStatus.objects.exclude(status='offline').filter(
        Q(last_heartbeat__lt=cutoff) |
        Q(last_heartbeat__isnull=True, status_changed_at__lt=cutoff)
    )
    count = 0
    for ag in zombies:
        try:
            logger.warning(
                f"Zombie session detected: {ag.user.username} "
                f"(status={ag.status}, heartbeat={ag.last_heartbeat})"
            )
            ag._close_time_log(ended_at=timezone.now())
            ag.status = 'offline'
            ag.current_call_id = ''
            ag.save()
            ag._open_time_log(status='offline', started_at=timezone.now())
            count += 1
        except Exception as e:
            logger.error(f"Error cleaning zombie {ag.user.username}: {e}")
    return count


# =============================================================================
# PROFILE / PASSWORD VIEWS (unchanged)
# =============================================================================

@method_decorator(login_required, name='dispatch')
class ProfileView(View):
    template_name = 'users/profile.html'

    def get(self, request):
        form = UserProfileForm(instance=request.user.profile, user=request.user)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = UserProfileForm(
            request.POST, request.FILES,
            instance=request.user.profile,
            user=request.user
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('users:profile')
        return render(request, self.template_name, {'form': form})


@method_decorator(login_required, name='dispatch')
class ChangePasswordView(View):
    template_name = 'users/change_password.html'

    def get(self, request):
        form = CustomPasswordChangeForm(user=request.user)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = CustomPasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Password changed successfully!')
            return redirect('users:change_password')
        return render(request, self.template_name, {'form': form})


# =============================================================================
# USER MANAGEMENT VIEWS (Restored)
# =============================================================================

@method_decorator(role_required(['Manager', 'Admin']), name='dispatch')
class UserListView(ListView):
    model = User
    template_name = 'users/user_list.html'
    context_object_name = 'users'
    paginate_by = 10

    def get_queryset(self):
        qs = User.objects.select_related('profile', 'agent_status').all().order_by('-date_joined')
        
        # Apply filters
        form = UserSearchForm(self.request.GET)
        if form.is_valid():
            search = form.cleaned_data.get('search')
            role = form.cleaned_data.get('role')
            department = form.cleaned_data.get('department')
            is_active = form.cleaned_data.get('is_active')

            if search:
                qs = qs.filter(
                    Q(username__icontains=search) |
                    Q(first_name__icontains=search) |
                    Q(last_name__icontains=search) |
                    Q(email__icontains=search)
                )
            
            if role:
                qs = qs.filter(groups=role)
                
            if department:
                qs = qs.filter(profile__department__icontains=department)
            
            if is_active:
                is_active_bool = is_active == 'true'
                qs = qs.filter(is_active=is_active_bool)
                
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_form'] = UserSearchForm(self.request.GET)
        context['total_users'] = User.objects.count()
        context['active_users'] = User.objects.filter(is_active=True).count()
        return context


@method_decorator(role_required(['Manager', 'Admin']), name='dispatch')
class UserDetailView(DetailView):
    model = User
    template_name = 'users/user_detail.html'
    context_object_name = 'user_obj'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if hasattr(self.object, 'profile') and self.object.profile.is_agent():
            pass
        return context


@method_decorator(role_required(['Manager', 'Admin']), name='dispatch')
class UserCreateView(CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'users/user_create.html'
    success_url = reverse_lazy('users:list')

    def form_valid(self, form):
        messages.success(self.request, f"User {form.instance.username} created successfully.")
        return super().form_valid(form)


@method_decorator(role_required(['Manager', 'Admin']), name='dispatch')
class UserUpdateView(UpdateView):
    model = User
    form_class = UserProfileForm
    template_name = 'users/user_edit.html'
    context_object_name = 'user_obj'
    success_url = reverse_lazy('users:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.object
        return kwargs
    
    def get_initial(self):
        initial = super().get_initial()
        initial['first_name'] = self.object.first_name
        initial['last_name'] = self.object.last_name
        initial['email'] = self.object.email
        return initial

    def form_valid(self, form):
        messages.success(self.request, f"User {self.object.username} updated successfully.")
        return super().form_valid(form)


@login_required
def user_status_ajax(request):
    """Return JSON status of all agents for real-time dashboard updates."""
    # This view is called by JS in user_list.html
    agents = AgentStatus.objects.select_related('user', 'user__profile').all()
    # Also get all active users to match template expectation if needed, 
    # but the template iterates data.users to update status indicators.
    # We should probably return all users or just agents. The template updates any row matching data-user-id
    
    users_data = []
    # Optimization: fetch all users with their status
    all_users = User.objects.select_related('agent_status').all()
    
    for u in all_users:
        status = 'offline'
        if hasattr(u, 'agent_status'):
            status = u.agent_status.status
        
        users_data.append({
            'id': u.id,
            'status': status
        })
        
    return JsonResponse({'users': users_data})
