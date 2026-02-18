# core/middleware.py

from django.utils import timezone
from django.contrib.auth.models import AnonymousUser
from users.models import UserProfile, AgentStatus
import logging

logger = logging.getLogger(__name__)


class UserActivityMiddleware:
    """
    Middleware to track user activity and update agent status
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Process the request
        response = self.process_request(request)
        if response:
            return response
            
        response = self.get_response(request)
        
        # Process the response
        self.process_response(request, response)
        
        return response

    def process_request(self, request):
        """
        Process incoming request to track user activity
        """
        if not isinstance(request.user, AnonymousUser) and request.user.is_authenticated:
            try:
                # Update user's last activity
                if hasattr(request.user, 'profile'):
                    profile = request.user.profile
                    profile.last_activity = timezone.now()
                    profile.save(update_fields=['last_activity'])
                    
                    # Update agent status if user is an agent
                    if hasattr(profile, 'is_agent') and profile.is_agent():
                        agent_status, created = AgentStatus.objects.get_or_create(
                            user=request.user,
                            defaults={'status': 'offline'}
                        )
                        
                        # Update last activity for agent status
                        agent_status.status_changed_at = timezone.now()
                        
                        # Auto-set to available if they were offline and it's during work hours
                        if agent_status.status == 'offline' and self.is_work_hours():
                            agent_status.status = 'available'
                            
                        agent_status.save(update_fields=['status_changed_at', 'status'])
                        
            except Exception as e:
                logger.error(f"Error updating user activity: {e}")
        
        return None

    def process_response(self, request, response):
        """
        Process response (currently not used but available for future features)
        """
        return response

    def is_work_hours(self):
        """
        Check if current time is within work hours
        This is a simple implementation - you can make it more sophisticated
        """
        now = timezone.now()
        current_hour = now.hour
        
        # Simple work hours check (9 AM to 6 PM)
        return 9 <= current_hour <= 18


class SecurityMiddleware:
    """
    Additional security middleware for the autodialer system
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Add security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        return response


class APIThrottleMiddleware:
    """
    Simple API rate limiting middleware
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.request_counts = {}

    def __call__(self, request):
        # Check if this is an API request
        if request.path.startswith('/api/'):
            client_ip = self.get_client_ip(request)
            
            # Simple rate limiting logic
            now = timezone.now()
            minute_key = f"{client_ip}_{now.strftime('%Y%m%d%H%M')}"
            
            if minute_key in self.request_counts:
                self.request_counts[minute_key] += 1
                if self.request_counts[minute_key] > 60:  # 60 requests per minute
                    from django.http import JsonResponse
                    return JsonResponse(
                        {'error': 'Rate limit exceeded'}, 
                        status=429
                    )
            else:
                self.request_counts[minute_key] = 1
                
            # Clean old entries (keep only current minute)
            current_minute = now.strftime('%Y%m%d%H%M')
            self.request_counts = {
                k: v for k, v in self.request_counts.items() 
                if k.endswith(current_minute)
            }
        
        response = self.get_response(request)
        return response

    def get_client_ip(self, request):
        """Get the client's IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class TimezoneMiddleware:
    """
    Activate the effective timezone for every authenticated request.
    """
    _DEFAULT = 'Asia/Kolkata'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz_name = self._resolve_timezone(request)
        try:
            import pytz
            timezone.activate(pytz.timezone(tz_name))
        except Exception:
            import pytz
            timezone.activate(pytz.timezone(self._DEFAULT))

        response = self.get_response(request)
        timezone.deactivate()
        return response

    def _resolve_timezone(self, request) -> str:
        import pytz
        # 1. User preference
        if request.user.is_authenticated:
            try:
                # Check for profile and timezone field
                if hasattr(request.user, 'profile') and request.user.profile.timezone:
                    user_tz = request.user.profile.timezone.strip()
                    if user_tz:
                        pytz.timezone(user_tz)   # validate
                        return user_tz
            except Exception:
                pass

        # 2. System setting
        try:
            from core.timezone_utils import get_system_timezone
            return get_system_timezone()
        except Exception:
            pass

        return self._DEFAULT