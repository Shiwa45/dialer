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