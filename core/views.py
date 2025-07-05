# core/views.py

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from campaigns.models import Campaign
from leads.models import Lead
from calls.models import CallLog
from users.models import UserProfile

@login_required
def dashboard(request):
    """
    Main dashboard view
    """
    context = {}
    
    # Get statistics based on user role
    if request.user.is_staff:
        # Manager/Admin dashboard
        context.update({
            'total_campaigns': Campaign.objects.count(),
            'active_campaigns': Campaign.objects.filter(status='active').count(),
            'total_leads': Lead.objects.count(),
            'today_calls': CallLog.objects.filter(
                start_time__date=timezone.now().date()
            ).count(),
            'recent_campaigns': Campaign.objects.order_by('-created_at')[:5],
        })
    else:
        # Agent dashboard
        today = timezone.now().date()
        context.update({
            'my_calls_today': CallLog.objects.filter(
                agent=request.user,
                start_time__date=today
            ).count(),
            'my_dispositioned_calls': CallLog.objects.filter(
                agent=request.user,
                start_time__date=today,
                disposition__isnull=False
            ).count(),
        })
    
    return render(request, 'core/dashboard.html', context)


