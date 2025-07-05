# core/views.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum, Avg
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from datetime import timedelta, datetime
import json

# Import your models
from campaigns.models import Campaign, CampaignStats, Disposition
from leads.models import Lead, LeadList
from calls.models import CallLog
from users.models import UserProfile, AgentStatus
from telephony.models import AsteriskServer, Phone


@login_required
def dashboard(request):
    """
    Main dashboard view with role-based content
    """
    user = request.user
    today = timezone.now().date()
    
    context = {
        'user': user,
        'today': today,
    }
    
    if user.is_staff or hasattr(user, 'profile') and user.profile.is_manager():
        # Manager/Admin Dashboard
        context.update(get_manager_dashboard_data(today))
    elif hasattr(user, 'profile') and user.profile.is_supervisor():
        # Supervisor Dashboard
        context.update(get_supervisor_dashboard_data(user, today))
    else:
        # Agent Dashboard
        context.update(get_agent_dashboard_data(user, today))
    
    return render(request, 'core/dashboard.html', context)


def get_manager_dashboard_data(today):
    """Get dashboard data for managers/admins"""
    
    # Basic statistics
    total_campaigns = Campaign.objects.count()
    active_campaigns = Campaign.objects.filter(status='active').count()
    total_leads = Lead.objects.count()
    total_agents = User.objects.filter(profile__is_active_agent=True).count()
    
    # Today's statistics
    today_calls = CallLog.objects.filter(start_time__date=today).count()
    today_answered = CallLog.objects.filter(
        start_time__date=today, 
        disposition__isnull=False
    ).count()
    today_sales = CallLog.objects.filter(
        start_time__date=today,
        disposition__is_sale=True
    ).count()
    
    # Online agents
    online_agents = AgentStatus.objects.filter(
        status='available',
        status_changed_at__gte=timezone.now() - timedelta(minutes=5)
    ).count()
    
    # Recent activity
    recent_campaigns = Campaign.objects.order_by('-created_at')[:5]
    recent_calls = CallLog.objects.select_related(
        'agent', 'lead', 'campaign', 'disposition'
    ).order_by('-start_time')[:10]
    
    # Performance metrics
    last_7_days = timezone.now().date() - timedelta(days=7)
    weekly_stats = CallLog.objects.filter(
        start_time__date__gte=last_7_days
    ).aggregate(
        total_calls=Count('id'),
        total_answered=Count('id', filter=Q(disposition__isnull=False)),
        total_sales=Count('id', filter=Q(disposition__is_sale=True)),
        avg_duration=Avg('talk_duration')
    )
    
    # Calculate rates
    contact_rate = 0
    conversion_rate = 0
    if weekly_stats['total_calls'] > 0:
        contact_rate = (weekly_stats['total_answered'] / weekly_stats['total_calls']) * 100
        if weekly_stats['total_answered'] > 0:
            conversion_rate = (weekly_stats['total_sales'] / weekly_stats['total_answered']) * 100
    
    # System health
    telephony_servers = AsteriskServer.objects.filter(is_active=True)
    system_health = {
        'telephony_ok': telephony_servers.filter(connection_status='connected').count(),
        'telephony_total': telephony_servers.count(),
        'database_ok': True,  # You can add actual health checks here
        'celery_ok': True,    # You can add actual health checks here
    }
    
    return {
        'dashboard_type': 'manager',
        'stats': {
            'total_campaigns': total_campaigns,
            'active_campaigns': active_campaigns,
            'total_leads': total_leads,
            'total_agents': total_agents,
            'today_calls': today_calls,
            'today_answered': today_answered,
            'today_sales': today_sales,
            'online_agents': online_agents,
            'contact_rate': round(contact_rate, 1),
            'conversion_rate': round(conversion_rate, 1),
            'avg_duration': int(weekly_stats['avg_duration'] or 0),
        },
        'recent_campaigns': recent_campaigns,
        'recent_calls': recent_calls,
        'weekly_stats': weekly_stats,
        'system_health': system_health,
    }


def get_supervisor_dashboard_data(user, today):
    """Get dashboard data for supervisors"""
    
    # Get campaigns this supervisor manages
    managed_campaigns = Campaign.objects.filter(
        Q(created_by=user) | Q(assigned_users=user)
    ).distinct()
    
    # Get agents under supervision
    supervised_agents = User.objects.filter(
        profile__is_active_agent=True,
        assigned_campaigns__in=managed_campaigns
    ).distinct()
    
    # Statistics for managed campaigns
    campaign_calls_today = CallLog.objects.filter(
        campaign__in=managed_campaigns,
        start_time__date=today
    ).count()
    
    campaign_sales_today = CallLog.objects.filter(
        campaign__in=managed_campaigns,
        start_time__date=today,
        disposition__is_sale=True
    ).count()
    
    # Agent performance
    agent_performance = []
    for agent in supervised_agents[:10]:  # Top 10 agents
        agent_stats = CallLog.objects.filter(
            agent=agent,
            start_time__date=today
        ).aggregate(
            calls=Count('id'),
            sales=Count('id', filter=Q(disposition__is_sale=True))
        )
        
        agent_performance.append({
            'agent': agent,
            'calls': agent_stats['calls'],
            'sales': agent_stats['sales'],
            'status': getattr(agent.profile, 'agent_status', None),
        })
    
    return {
        'dashboard_type': 'supervisor',
        'stats': {
            'managed_campaigns': managed_campaigns.count(),
            'active_campaigns': managed_campaigns.filter(status='active').count(),
            'supervised_agents': supervised_agents.count(),
            'online_agents': supervised_agents.filter(
                profile__agent_status__status='available'
            ).count(),
            'campaign_calls_today': campaign_calls_today,
            'campaign_sales_today': campaign_sales_today,
        },
        'managed_campaigns': managed_campaigns[:5],
        'agent_performance': agent_performance,
        'supervised_agents': supervised_agents,
    }


def get_agent_dashboard_data(user, today):
    """Get dashboard data for agents"""
    
    # Agent's personal statistics
    my_calls_today = CallLog.objects.filter(
        agent=user,
        start_time__date=today
    ).count()
    
    my_answered_today = CallLog.objects.filter(
        agent=user,
        start_time__date=today,
        disposition__isnull=False
    ).count()
    
    my_sales_today = CallLog.objects.filter(
        agent=user,
        start_time__date=today,
        disposition__is_sale=True
    ).count()
    
    # This week's performance
    week_start = today - timedelta(days=today.weekday())
    weekly_calls = CallLog.objects.filter(
        agent=user,
        start_time__date__gte=week_start
    ).count()
    
    # Available campaigns
    my_campaigns = Campaign.objects.filter(
        assigned_users=user,
        status='active'
    )
    
    # Recent calls
    recent_calls = CallLog.objects.filter(agent=user).select_related(
        'lead', 'campaign', 'disposition'
    ).order_by('-start_time')[:10]
    
    # Next callbacks
    next_callbacks = CallLog.objects.filter(
        agent=user,
        disposition__requires_callback=True,
        callback_datetime__gte=timezone.now(),
        callback_completed=False
    ).order_by('callback_datetime')[:5]
    
    # Agent status
    agent_status = getattr(user.profile, 'agent_status', None)
    
    return {
        'dashboard_type': 'agent',
        'stats': {
            'my_calls_today': my_calls_today,
            'my_answered_today': my_answered_today,
            'my_sales_today': my_sales_today,
            'weekly_calls': weekly_calls,
            'contact_rate': round((my_answered_today / my_calls_today * 100) if my_calls_today > 0 else 0, 1),
            'conversion_rate': round((my_sales_today / my_answered_today * 100) if my_answered_today > 0 else 0, 1),
        },
        'my_campaigns': my_campaigns,
        'recent_calls': recent_calls,
        'next_callbacks': next_callbacks,
        'agent_status': agent_status,
    }


@login_required
@require_http_methods(["GET"])
def dashboard_stats_api(request):
    """API endpoint for real-time dashboard statistics"""
    
    today = timezone.now().date()
    user = request.user
    
    if user.is_staff:
        # Real-time stats for managers
        stats = {
            'active_calls': CallLog.objects.filter(
                end_time__isnull=True
            ).count(),
            'agents_online': AgentStatus.objects.filter(
                status='available'
            ).count(),
            'calls_today': CallLog.objects.filter(
                start_time__date=today
            ).count(),
            'server_status': 'online',  # You can implement actual server checks
        }
    else:
        # Real-time stats for agents
        stats = {
            'my_status': getattr(user.profile, 'agent_status', {}).get('status', 'offline'),
            'calls_in_queue': 0,  # Implement queue logic
            'my_calls_today': CallLog.objects.filter(
                agent=user,
                start_time__date=today
            ).count(),
        }
    
    return JsonResponse(stats)


@login_required
@require_http_methods(["GET"])
def dashboard_chart_data(request):
    """API endpoint for dashboard chart data"""
    
    chart_type = request.GET.get('type', 'calls')
    days = int(request.GET.get('days', 7))
    
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days-1)
    
    data = []
    
    if chart_type == 'calls':
        # Daily call volume
        for i in range(days):
            date = start_date + timedelta(days=i)
            call_count = CallLog.objects.filter(start_time__date=date).count()
            data.append({
                'date': date.strftime('%Y-%m-%d'),
                'value': call_count,
                'label': date.strftime('%m/%d')
            })
    
    elif chart_type == 'performance':
        # Daily performance metrics
        for i in range(days):
            date = start_date + timedelta(days=i)
            day_stats = CallLog.objects.filter(start_time__date=date).aggregate(
                total=Count('id'),
                answered=Count('id', filter=Q(disposition__isnull=False)),
                sales=Count('id', filter=Q(disposition__is_sale=True))
            )
            
            contact_rate = 0
            conversion_rate = 0
            if day_stats['total'] > 0:
                contact_rate = (day_stats['answered'] / day_stats['total']) * 100
                if day_stats['answered'] > 0:
                    conversion_rate = (day_stats['sales'] / day_stats['answered']) * 100
            
            data.append({
                'date': date.strftime('%Y-%m-%d'),
                'contact_rate': round(contact_rate, 1),
                'conversion_rate': round(conversion_rate, 1),
                'label': date.strftime('%m/%d')
            })
    
    elif chart_type == 'dispositions':
        # Disposition breakdown for the period
        dispositions = Disposition.objects.filter(
            calllog__start_time__date__gte=start_date,
            calllog__start_time__date__lte=end_date
        ).annotate(
            count=Count('calllog')
        ).order_by('-count')[:10]
        
        data = [{
            'name': disp.name,
            'value': disp.count,
            'color': disp.color
        } for disp in dispositions]
    
    return JsonResponse({'data': data})


@login_required 
def system_status(request):
    """System status page for administrators"""
    if not request.user.is_staff:
        return redirect('core:dashboard')
    
    # Check various system components
    status_data = {
        'database': check_database_status(),
        'telephony': check_telephony_status(),
        'celery': check_celery_status(),
        'storage': check_storage_status(),
    }
    
    return render(request, 'core/system_status.html', {'status_data': status_data})


def check_database_status():
    """Check database connectivity and performance"""
    try:
        # Simple query to test database
        User.objects.count()
        return {
            'status': 'healthy',
            'message': 'Database connection OK',
            'details': 'All database operations functioning normally'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': 'Database connection failed',
            'details': str(e)
        }


def check_telephony_status():
    """Check telephony server status"""
    try:
        servers = AsteriskServer.objects.filter(is_active=True)
        if not servers.exists():
            return {
                'status': 'warning',
                'message': 'No telephony servers configured',
                'details': 'Please configure at least one Asterisk server'
            }
        
        connected_servers = servers.filter(connection_status='connected').count()
        total_servers = servers.count()
        
        if connected_servers == 0:
            return {
                'status': 'error',
                'message': 'No telephony servers online',
                'details': f'0 of {total_servers} servers connected'
            }
        elif connected_servers < total_servers:
            return {
                'status': 'warning',
                'message': 'Some telephony servers offline',
                'details': f'{connected_servers} of {total_servers} servers connected'
            }
        else:
            return {
                'status': 'healthy',
                'message': 'All telephony servers online',
                'details': f'{connected_servers} servers connected'
            }
    except Exception as e:
        return {
            'status': 'error',
            'message': 'Failed to check telephony status',
            'details': str(e)
        }


def check_celery_status():
    """Check Celery worker status"""
    try:
        # You can implement actual Celery status checking here
        # For now, we'll return a placeholder
        return {
            'status': 'healthy',
            'message': 'Celery workers running',
            'details': 'Background tasks processing normally'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': 'Celery worker issues',
            'details': str(e)
        }


def check_storage_status():
    """Check storage space and file system"""
    try:
        import shutil
        import os
        
        # Check available disk space
        total, used, free = shutil.disk_usage(os.path.dirname(__file__))
        
        # Convert to GB
        free_gb = free // (1024**3)
        total_gb = total // (1024**3)
        used_percent = (used / total) * 100
        
        if free_gb < 1:  # Less than 1GB free
            status = 'error'
            message = 'Critically low disk space'
        elif used_percent > 90:
            status = 'warning' 
            message = 'Low disk space warning'
        else:
            status = 'healthy'
            message = 'Storage space OK'
            
        return {
            'status': status,
            'message': message,
            'details': f'{free_gb}GB free of {total_gb}GB total ({used_percent:.1f}% used)'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': 'Failed to check storage status',
            'details': str(e)
        }