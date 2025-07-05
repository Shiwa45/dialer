# core/middleware.py

import json
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser
from .models import UserActivity

class UserActivityMiddleware:
    """
    Middleware to track user activities
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Track user activity if authenticated
        if (hasattr(request, 'user') and 
            not isinstance(request.user, AnonymousUser) and 
            request.method == 'POST'):
            
            try:
                UserActivity.objects.create(
                    user=request.user,
                    action=f"{request.method} {request.path}",
                    details={
                        'status_code': response.status_code,
                        'path': request.path,
                        'method': request.method
                    },
                    ip_address=self.get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
                )
            except Exception:
                pass  # Silently fail to avoid breaking the request
        
        return response
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

