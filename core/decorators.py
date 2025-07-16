# core/decorators.py

from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages


def role_required(role_name):
    """
    Decorator to require specific role for view access
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            
            # Superusers always have access
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # Check if user has the required role
            if user.groups.filter(name=role_name).exists():
                return view_func(request, *args, **kwargs)
            
            # Check for hierarchical roles
            if role_name == 'Agent' and user.groups.filter(name__in=['Supervisor', 'Manager']).exists():
                return view_func(request, *args, **kwargs)
            elif role_name == 'Supervisor' and user.groups.filter(name='Manager').exists():
                return view_func(request, *args, **kwargs)
            
            messages.error(request, f'Access denied. {role_name} role required.')
            return redirect('core:dashboard')
        
        return _wrapped_view
    return decorator


def manager_required(view_func):
    """
    Decorator to require manager role or staff status
    """
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        
        if (user.is_staff or user.is_superuser or 
            user.groups.filter(name='Manager').exists()):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Access denied. Manager privileges required.')
        return redirect('core:dashboard')
    
    return _wrapped_view


def supervisor_required(view_func):
    """
    Decorator to require supervisor role or higher
    """
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        
        if (user.is_staff or user.is_superuser or 
            user.groups.filter(name__in=['Manager', 'Supervisor']).exists()):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Access denied. Supervisor privileges required.')
        return redirect('core:dashboard')
    
    return _wrapped_view


def agent_required(view_func):
    """
    Decorator to require agent role or higher
    """
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        
        if (user.is_staff or user.is_superuser or 
            user.groups.filter(name__in=['Manager', 'Supervisor', 'Agent']).exists()):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Access denied. Agent privileges required.')
        return redirect('core:dashboard')
    
    return _wrapped_view


def ajax_required(view_func):
    """
    Decorator to require AJAX requests
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            raise PermissionDenied("This view requires AJAX request")
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def campaign_access_required(view_func):
    """
    Decorator to check if user has access to a specific campaign
    """
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        from campaigns.models import Campaign
        
        # Get campaign from URL parameters
        campaign_id = kwargs.get('pk') or kwargs.get('campaign_id')
        if not campaign_id:
            messages.error(request, 'Campaign not specified.')
            return redirect('campaigns:list')
        
        try:
            campaign = Campaign.objects.get(pk=campaign_id)
        except Campaign.DoesNotExist:
            messages.error(request, 'Campaign not found.')
            return redirect('campaigns:list')
        
        user = request.user
        
        # Check access permissions
        has_access = (
            user.is_staff or
            user.is_superuser or
            campaign.created_by == user or
            campaign.assigned_users.filter(id=user.id).exists() or
            user.groups.filter(name__in=['Manager', 'Supervisor']).exists()
        )
        
        if not has_access:
            messages.error(request, 'Access denied to this campaign.')
            return redirect('campaigns:list')
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def campaign_edit_required(view_func):
    """
    Decorator to check if user can edit a specific campaign
    """
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        from campaigns.models import Campaign
        
        campaign_id = kwargs.get('pk') or kwargs.get('campaign_id')
        if not campaign_id:
            messages.error(request, 'Campaign not specified.')
            return redirect('campaigns:list')
        
        try:
            campaign = Campaign.objects.get(pk=campaign_id)
        except Campaign.DoesNotExist:
            messages.error(request, 'Campaign not found.')
            return redirect('campaigns:list')
        
        user = request.user
        
        # Check edit permissions
        can_edit = (
            user.is_staff or
            user.is_superuser or
            campaign.created_by == user or
            user.groups.filter(name='Manager').exists()
        )
        
        if not can_edit:
            messages.error(request, 'Permission denied. Cannot edit this campaign.')
            return redirect('campaigns:detail', pk=campaign_id)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def api_key_required(view_func):
    """
    Decorator for API views that require authentication via API key
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # This would check for API key in headers
        # For now, we'll just check if user is authenticated
        if not request.user.is_authenticated:
            from django.http import JsonResponse
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def throttle_requests(max_requests=60, window_seconds=60):
    """
    Simple rate limiting decorator
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Simple in-memory rate limiting
            # In production, you'd use Redis or similar
            import time
            from django.core.cache import cache
            
            client_ip = request.META.get('REMOTE_ADDR')
            cache_key = f'rate_limit_{client_ip}_{view_func.__name__}'
            
            requests = cache.get(cache_key, [])
            now = time.time()
            
            # Remove old requests outside the window
            requests = [req_time for req_time in requests if now - req_time < window_seconds]
            
            if len(requests) >= max_requests:
                from django.http import JsonResponse
                return JsonResponse({'error': 'Rate limit exceeded'}, status=429)
            
            requests.append(now)
            cache.set(cache_key, requests, window_seconds)
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    return decorator




# core/decorators.py

from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps


def role_required(*roles):
    """
    Decorator to require specific user roles
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            user_groups = request.user.groups.values_list('name', flat=True)
            
            if request.user.is_superuser or any(role in user_groups for role in roles):
                return view_func(request, *args, **kwargs)
            
            messages.error(request, 'You do not have permission to access this page.')
            raise PermissionDenied
        
        return _wrapped_view
    return decorator


def agent_required(view_func):
    """
    Decorator to require agent role (Agent, Supervisor, or Manager)
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Check if user has agent profile and appropriate role
        if hasattr(request.user, 'profile'):
            profile = request.user.profile
            if profile.is_agent() or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
        
        # Also check groups
        user_groups = request.user.groups.values_list('name', flat=True)
        agent_roles = ['Agent', 'Supervisor', 'Manager']
        
        if request.user.is_superuser or any(role in user_groups for role in agent_roles):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You need agent permissions to access this page.')
        return redirect('core:dashboard')
    
    return _wrapped_view


def supervisor_required(view_func):
    """
    Decorator to require supervisor role (Supervisor or Manager)
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Check if user has supervisor profile
        if hasattr(request.user, 'profile'):
            profile = request.user.profile
            if profile.is_supervisor() or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
        
        # Also check groups
        user_groups = request.user.groups.values_list('name', flat=True)
        supervisor_roles = ['Supervisor', 'Manager']
        
        if request.user.is_superuser or any(role in user_groups for role in supervisor_roles):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You need supervisor permissions to access this page.')
        return redirect('core:dashboard')
    
    return _wrapped_view


def manager_required(view_func):
    """
    Decorator to require manager role
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Check if user has manager profile
        if hasattr(request.user, 'profile'):
            profile = request.user.profile
            if profile.is_manager() or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
        
        # Also check groups
        user_groups = request.user.groups.values_list('name', flat=True)
        
        if request.user.is_superuser or 'Manager' in user_groups or request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You need manager permissions to access this page.')
        return redirect('core:dashboard')
    
    return _wrapped_view


def ajax_required(view_func):
    """
    Decorator to require AJAX requests
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            raise PermissionDenied("This endpoint requires an AJAX request.")
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def active_session_required(view_func):
    """
    Decorator to require an active agent session
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Check if user has an active agent session
        from calls.models import AgentSession
        active_session = AgentSession.objects.filter(
            agent=request.user,
            status='active'
        ).first()
        
        if not active_session:
            messages.warning(request, 'You need to start an agent session first.')
            return redirect('agents:dashboard')
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def campaign_access_required(view_func):
    """
    Decorator to check if user has access to specific campaign
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        campaign_id = kwargs.get('campaign_id') or request.GET.get('campaign_id') or request.POST.get('campaign_id')
        
        if not campaign_id:
            return view_func(request, *args, **kwargs)
        
        # Superusers and managers have access to all campaigns
        if request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.is_manager()):
            return view_func(request, *args, **kwargs)
        
        # Check if user is assigned to the campaign
        from campaigns.models import Campaign
        from agents.models import AgentQueue
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            
            # Check if agent is assigned to this campaign
            agent_queue = AgentQueue.objects.filter(
                agent=request.user,
                campaign=campaign,
                is_active=True
            ).exists()
            
            if agent_queue:
                return view_func(request, *args, **kwargs)
            
        except Campaign.DoesNotExist:
            pass
        
        messages.error(request, 'You do not have access to this campaign.')
        return redirect('agents:dashboard')
    
    return _wrapped_view


def phone_session_required(view_func):
    """
    Decorator to require an active phone session
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Check if user has an active WebRTC session
        from agents.models import AgentWebRTCSession
        webrtc_session = AgentWebRTCSession.objects.filter(
            agent=request.user,
            status='connected'
        ).first()
        
        if not webrtc_session:
            messages.warning(request, 'You need to connect your phone first.')
            return redirect('agents:phone_interface')
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def check_user_status(allowed_statuses):
    """
    Decorator to check if user has allowed status
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            # Get user's current status
            from users.models import AgentStatus
            agent_status = getattr(request.user, 'agent_status', None)
            
            if not agent_status:
                messages.warning(request, 'Agent status not found. Please contact administrator.')
                return redirect('agents:dashboard')
            
            if agent_status.status not in allowed_statuses:
                messages.warning(request, f'This action requires agent status to be one of: {", ".join(allowed_statuses)}')
                return redirect('agents:dashboard')
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    return decorator


def available_only(view_func):
    """
    Decorator to require agent to be available
    """
    return check_user_status(['available'])(view_func)


def not_offline(view_func):
    """
    Decorator to require agent to not be offline
    """
    return check_user_status(['available', 'busy', 'break', 'lunch', 'training', 'meeting'])(view_func)


class RoleRequiredMixin:
    """
    Mixin for class-based views to require specific roles
    """
    required_roles = []
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if not self.required_roles:
            return super().dispatch(request, *args, **kwargs)
        
        user_groups = request.user.groups.values_list('name', flat=True)
        
        if request.user.is_superuser or any(role in user_groups for role in self.required_roles):
            return super().dispatch(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to access this page.')
        raise PermissionDenied


class AgentRequiredMixin(RoleRequiredMixin):
    """
    Mixin for views that require agent permissions
    """
    required_roles = ['Agent', 'Supervisor', 'Manager']


class SupervisorRequiredMixin(RoleRequiredMixin):
    """
    Mixin for views that require supervisor permissions
    """
    required_roles = ['Supervisor', 'Manager']


class ManagerRequiredMixin(RoleRequiredMixin):
    """
    Mixin for views that require manager permissions
    """
    required_roles = ['Manager']


def permission_required_with_message(perm, message=None):
    """
    Permission required decorator with custom message
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            if request.user.has_perm(perm) or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            error_message = message or f'You need {perm} permission to access this page.'
            messages.error(request, error_message)
            raise PermissionDenied
        
        return _wrapped_view
    return decorator


def throttle_requests(max_requests=60, window_seconds=60):
    """
    Simple request throttling decorator
    """
    from django.core.cache import cache
    from django.http import HttpResponse
    import time
    
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Create unique key for this user
            cache_key = f"throttle_{request.user.id if request.user.is_authenticated else request.META.get('REMOTE_ADDR', 'unknown')}"
            
            # Get current request count
            current_requests = cache.get(cache_key, [])
            now = time.time()
            
            # Remove old requests outside the window
            current_requests = [req_time for req_time in current_requests if now - req_time < window_seconds]
            
            # Check if limit exceeded
            if len(current_requests) >= max_requests:
                return HttpResponse('Rate limit exceeded. Please try again later.', status=429)
            
            # Add current request
            current_requests.append(now)
            cache.set(cache_key, current_requests, window_seconds)
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    return decorator