# core/context_processors.py

from django.conf import settings
from django.utils import timezone
from campaigns.models import Campaign
from leads.models import Lead
from calls.models import CallLog
from users.models import AgentStatus
from django.db.models import Count, Q


def global_settings(request):
    """
    Add global settings and statistics to template context
    """
    context = {
        'COMPANY_NAME': getattr(settings, 'COMPANY_NAME', 'AutoDialer Pro'),
        'VERSION': getattr(settings, 'VERSION', '1.0.0'),
        'SITE_NAME': getattr(settings, 'SITE_NAME', 'AutoDialer System'),
        'current_year': timezone.now().year,
    }
    
    # Add system-wide statistics for authenticated users
    if request.user.is_authenticated:
        today = timezone.now().date()
        
        # Basic system stats
        context.update({
            'system_stats': {
                'total_campaigns': Campaign.objects.count(),
                'active_campaigns': Campaign.objects.filter(status='active').count(),
                'total_leads': Lead.objects.count(),
                'calls_today': CallLog.objects.filter(start_time__date=today).count(),
                'agents_online': AgentStatus.objects.filter(
                    status='available',
                    status_changed_at__gte=timezone.now() - timezone.timedelta(minutes=5)
                ).count(),
            }
        })
        
        # User-specific context
        if hasattr(request.user, 'profile'):
            profile = request.user.profile
            context.update({
                'user_role': profile.get_role_display() if hasattr(profile, 'get_role_display') else 'User',
                'user_permissions': {
                    'is_manager': profile.is_manager() if hasattr(profile, 'is_manager') else request.user.is_staff,
                    'is_supervisor': profile.is_supervisor() if hasattr(profile, 'is_supervisor') else False,
                    'is_agent': profile.is_agent() if hasattr(profile, 'is_agent') else False,
                    'can_manage_users': request.user.is_staff or request.user.is_superuser,
                    'can_manage_campaigns': request.user.is_staff or (hasattr(profile, 'is_manager') and profile.is_manager()),
                    'can_view_reports': request.user.is_staff or (hasattr(profile, 'is_supervisor') and profile.is_supervisor()),
                }
            })
    
    return context


def navigation_context(request):
    """
    Add navigation-specific context
    """
    context = {}
    
    if request.user.is_authenticated:
        # Get unread notifications count (when notifications module is implemented)
        context['unread_notifications'] = 0  # Placeholder
        
        # Get user's active campaigns
        if hasattr(request.user, 'profile') and hasattr(request.user.profile, 'is_agent'):
            if request.user.profile.is_agent():
                context['my_active_campaigns'] = Campaign.objects.filter(
                    assigned_users=request.user,
                    status='active'
                ).count()
        
        # Quick stats for sidebar
        if request.user.is_staff:
            context['quick_stats'] = {
                'pending_leads': Lead.objects.filter(status='new').count(),
                'active_calls': CallLog.objects.filter(end_time__isnull=True).count(),
            }
    
    return context