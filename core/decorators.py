from functools import wraps
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages

def role_required(role_name):
    """
    Decorator to check if user has specific role (group)
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.groups.filter(name=role_name).exists() or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            else:
                messages.error(request, f"Access denied. {role_name} role required.")
                return redirect('dashboard')
        return wrapper
    return decorator

def agent_required(view_func):
    """
    Decorator to check if user is an agent
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if (request.user.groups.filter(name__in=['Agent', 'Supervisor', 'Manager']).exists() 
            or request.user.is_superuser):
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "Access denied. Agent role required.")
            return redirect('dashboard')
    return wrapper

def supervisor_required(view_func):
    """
    Decorator to check if user is a supervisor or manager
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if (request.user.groups.filter(name__in=['Supervisor', 'Manager']).exists() 
            or request.user.is_superuser):
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "Access denied. Supervisor role required.")
            return redirect('dashboard')
    return wrapper
