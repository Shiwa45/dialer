# users/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.contrib.auth.views import LoginView as BaseLoginView, LogoutView as BaseLogoutView
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


@method_decorator(login_required, name='dispatch')
class ProfileView(View):
    """
    User profile view and edit
    """
    template_name = 'users/profile.html'
    
    def get(self, request):
        form = UserProfileForm(instance=request.user.profile, user=request.user)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = UserProfileForm(
            request.POST, 
            request.FILES, 
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
    """
    Change password view
    """
    template_name = 'users/change_password.html'
    
    def get(self, request):
        form = CustomPasswordChangeForm(user=request.user)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = CustomPasswordChangeForm(user=request.user, data=request.POST)
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Password changed successfully!')
            return redirect('users:profile')
        
        return render(request, self.template_name, {'form': form})

@method_decorator(supervisor_required, name='dispatch')
class UserListView(ListView):
    """
    List all users with search and filtering
    """
    model = User
    template_name = 'users/user_list.html'
    context_object_name = 'users'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = User.objects.select_related('profile').prefetch_related('groups')
        
        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(username__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(profile__employee_id__icontains=search_query)
            )
        
        # Role filter
        role = self.request.GET.get('role')
        if role:
            queryset = queryset.filter(groups__id=role)
        
        # Department filter
        department = self.request.GET.get('department')
        if department:
            queryset = queryset.filter(profile__department__icontains=department)
        
        # Active status filter
        is_active = self.request.GET.get('is_active')
        if is_active == 'true':
            queryset = queryset.filter(is_active=True)
        elif is_active == 'false':
            queryset = queryset.filter(is_active=False)
        
        return queryset.distinct().order_by('username')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_form'] = UserSearchForm(self.request.GET)
        context['total_users'] = User.objects.count()
        context['active_users'] = User.objects.filter(is_active=True).count()
        return context

@method_decorator(role_required('Manager'), name='dispatch')
class UserCreateView(View):
    """
    Create new user
    """
    template_name = 'users/user_create.html'
    
    def get(self, request):
        form = CustomUserCreationForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = CustomUserCreationForm(request.POST)
        
        if form.is_valid():
            user = form.save()
            messages.success(request, f'User {user.username} created successfully!')
            return redirect('users:list')
        
        return render(request, self.template_name, {'form': form})

@method_decorator(supervisor_required, name='dispatch')
class UserDetailView(DetailView):
    """
    User detail view
    """
    model = User
    template_name = 'users/user_detail.html'
    context_object_name = 'user_obj'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.object
        
        # Get user statistics
        context['stats'] = {
            'total_sessions': UserSession.objects.filter(user=user).count(),
            'active_sessions': UserSession.objects.filter(user=user, is_active=True).count(),
            'total_calls': user.profile.total_calls_made + user.profile.total_calls_answered,
            'last_login': user.last_login,
        }
        
        # Get recent sessions
        context['recent_sessions'] = UserSession.objects.filter(user=user).order_by('-login_time')[:10]
        
        return context

@method_decorator(role_required('Manager'), name='dispatch')
class UserUpdateView(View):
    """
    Update user information
    """
    template_name = 'users/user_edit.html'
    
    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        form = UserProfileForm(instance=user.profile, user=user)
        
        # Get user's current groups
        user_groups = user.groups.all()
        available_groups = Group.objects.all()
        
        context = {
            'form': form,
            'user_obj': user,
            'user_groups': user_groups,
            'available_groups': available_groups,
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        form = UserProfileForm(request.POST, request.FILES, instance=user.profile, user=user)
        
        if form.is_valid():
            form.save()
            
            # Update user groups if provided
            new_groups = request.POST.getlist('groups')
            if new_groups:
                user.groups.clear()
                for group_id in new_groups:
                    try:
                        group = Group.objects.get(id=group_id)
                        user.groups.add(group)
                    except Group.DoesNotExist:
                        pass
            
            # Update active status
            is_active = request.POST.get('is_active') == 'on'
            user.is_active = is_active
            user.save()
            
            messages.success(request, f'User {user.username} updated successfully!')
            return redirect('users:detail', pk=user.pk)
        
        context = {
            'form': form,
            'user_obj': user,
            'user_groups': user.groups.all(),
            'available_groups': Group.objects.all(),
        }
        
        return render(request, self.template_name, context)

@login_required
def ajax_user_status(request):
    """
    AJAX endpoint for getting user status
    """
    if request.method == 'GET':
        users_status = []
        
        # Get all active users with their status
        users = User.objects.filter(is_active=True).select_related('profile', 'agent_status')
        
        for user in users:
            status_data = {
                'id': user.id,
                'username': user.username,
                'full_name': user.get_full_name(),
                'status': 'offline',
                'last_activity': None,
            }
            
            if hasattr(user, 'agent_status'):
                status_data['status'] = user.agent_status.status
                status_data['status_changed_at'] = user.agent_status.status_changed_at.isoformat()
            
            if hasattr(user, 'profile'):
                status_data['last_activity'] = user.profile.last_activity.isoformat()
            
            users_status.append(status_data)
        
        return JsonResponse({'users': users_status})
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def set_agent_status(request):
    """
    Set agent status via AJAX
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            status = data.get('status')
            reason = data.get('reason', '')
            
            if not status:
                return JsonResponse({'error': 'Status is required'}, status=400)
            
            agent_status, created = AgentStatus.objects.get_or_create(user=request.user)
            agent_status.set_status(status, reason)
            
            return JsonResponse({
                'success': True,
                'status': agent_status.get_status_display(),
                'status_code': agent_status.status
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)
