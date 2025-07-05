# campaigns/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, Avg
from django.http import JsonResponse
from django.utils import timezone
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views import View
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods
from datetime import timedelta, datetime
import json

from .models import (
    Campaign, CampaignAgent, Disposition, CampaignDisposition, 
    Script, CampaignStats, CampaignHours
)
from .forms import (
    CampaignCreateForm, CampaignUpdateForm, CampaignAgentForm,
    ScriptForm, CampaignHoursFormSet, CampaignSearchForm
)
from leads.models import Lead, LeadList
from core.decorators import manager_required, supervisor_required


class CampaignListView(LoginRequiredMixin, ListView):
    """
    List all campaigns with filtering and search
    """
    model = Campaign
    template_name = 'campaigns/campaign_list.html'
    context_object_name = 'campaigns'
    paginate_by = 20

    def get_queryset(self):
        queryset = Campaign.objects.select_related('created_by').prefetch_related(
            'assigned_users', 'daily_stats'
        ).annotate(
            assigned_agents_count=Count('assigned_users'),
            total_calls_made=Sum('daily_stats__calls_made'),
            total_sales=Sum('daily_stats__calls_answered', filter=Q(daily_stats__calls_answered__gt=0))
        )

        # Apply filters
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(campaign_id__icontains=search_query)
            )

        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        campaign_type = self.request.GET.get('campaign_type')
        if campaign_type:
            queryset = queryset.filter(campaign_type=campaign_type)

        created_by = self.request.GET.get('created_by')
        if created_by:
            queryset = queryset.filter(created_by_id=created_by)

        # Role-based filtering
        user = self.request.user
        if not user.is_staff:
            if hasattr(user, 'profile') and user.profile.is_supervisor():
                # Supervisors see campaigns they created or are assigned to
                queryset = queryset.filter(
                    Q(created_by=user) | Q(assigned_users=user)
                ).distinct()
            elif hasattr(user, 'profile') and user.profile.is_agent():
                # Agents see only campaigns assigned to them
                queryset = queryset.filter(assigned_users=user)

        return queryset.distinct().order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Statistics
        context['total_campaigns'] = Campaign.objects.count()
        context['active_campaigns'] = Campaign.objects.filter(status='active').count()
        context['paused_campaigns'] = Campaign.objects.filter(status='paused').count()
        context['completed_campaigns'] = Campaign.objects.filter(status='completed').count()
        
        # Search form
        context['search_form'] = CampaignSearchForm(self.request.GET)
        
        # Managers for filter dropdown
        context['managers'] = User.objects.filter(
            Q(is_staff=True) | Q(groups__name='Manager')
        ).distinct()
        
        return context


class CampaignDetailView(LoginRequiredMixin, DetailView):
    """
    Detailed view of a campaign
    """
    model = Campaign
    template_name = 'campaigns/campaign_detail.html'
    context_object_name = 'campaign'

    def get_queryset(self):
        queryset = Campaign.objects.select_related('created_by').prefetch_related(
            'assigned_users__profile',
            'scripts',
            'dispositions__disposition',
            'daily_stats',
            'operating_hours'
        )
        
        # Role-based access control
        user = self.request.user
        if not user.is_staff:
            if hasattr(user, 'profile') and user.profile.is_supervisor():
                queryset = queryset.filter(
                    Q(created_by=user) | Q(assigned_users=user)
                )
            elif hasattr(user, 'profile') and user.profile.is_agent():
                queryset = queryset.filter(assigned_users=user)
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        campaign = self.object
        
        # Performance statistics
        today = timezone.now().date()
        last_7_days = today - timedelta(days=7)
        
        # Today's stats
        today_stats = CampaignStats.objects.filter(
            campaign=campaign,
            date=today
        ).first()
        
        # Weekly stats
        weekly_stats = CampaignStats.objects.filter(
            campaign=campaign,
            date__gte=last_7_days
        ).aggregate(
            total_calls=Sum('calls_made'),
            total_answered=Sum('calls_answered'),
            total_sales=Sum('calls_answered', filter=Q(calls_answered__gt=0)),  # Simplified for now
            avg_duration=Avg('average_call_duration')
        )
        
        # Agent performance
        agent_performance = CampaignAgent.objects.filter(
            campaign=campaign,
            is_active=True
        ).select_related('user__profile').order_by('-calls_made')
        
        # Recent activity (this would come from call logs when implemented)
        # For now, we'll use a placeholder
        
        context.update({
            'today_stats': today_stats,
            'weekly_stats': weekly_stats,
            'agent_performance': agent_performance,
            'can_edit': self.can_edit_campaign(campaign),
            'can_manage_agents': self.can_manage_agents(campaign),
        })
        
        return context
    
    def can_edit_campaign(self, campaign):
        """Check if user can edit this campaign"""
        user = self.request.user
        return (
            user.is_staff or 
            campaign.created_by == user or
            (hasattr(user, 'profile') and user.profile.is_manager())
        )
    
    def can_manage_agents(self, campaign):
        """Check if user can manage campaign agents"""
        user = self.request.user
        return (
            user.is_staff or 
            campaign.created_by == user or
            (hasattr(user, 'profile') and user.profile.is_supervisor())
        )


class CampaignCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Create a new campaign
    """
    model = Campaign
    form_class = CampaignCreateForm
    template_name = 'campaigns/campaign_create.html'
    success_url = reverse_lazy('campaigns:list')

    def test_func(self):
        """Only managers and staff can create campaigns"""
        user = self.request.user
        return (
            user.is_staff or 
            (hasattr(user, 'profile') and user.profile.is_manager())
        )

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        
        # Create default operating hours (Monday-Friday, 9 AM - 5 PM)
        campaign = self.object
        for day in range(5):  # Monday to Friday
            CampaignHours.objects.create(
                campaign=campaign,
                day_of_week=day,
                start_time='09:00',
                end_time='17:00'
            )
        
        # Add default dispositions
        default_dispositions = Disposition.objects.filter(is_active=True)[:5]
        for i, disposition in enumerate(default_dispositions):
            CampaignDisposition.objects.create(
                campaign=campaign,
                disposition=disposition,
                sort_order=i + 1
            )
        
        messages.success(
            self.request, 
            f'Campaign "{campaign.name}" created successfully!'
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create New Campaign'
        context['available_agents'] = User.objects.filter(
            Q(groups__name='Agent') | Q(groups__name='Supervisor')
        ).select_related('profile')
        return context


class CampaignUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Update an existing campaign
    """
    model = Campaign
    form_class = CampaignUpdateForm
    template_name = 'campaigns/campaign_update.html'

    def test_func(self):
        """Check if user can edit this campaign"""
        campaign = self.get_object()
        user = self.request.user
        return (
            user.is_staff or 
            campaign.created_by == user or
            (hasattr(user, 'profile') and user.profile.is_manager())
        )

    def get_success_url(self):
        return reverse_lazy('campaigns:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, 
            f'Campaign "{self.object.name}" updated successfully!'
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit Campaign: {self.object.name}'
        return context


@login_required
@require_http_methods(["POST"])
def campaign_control(request, pk):
    """
    Control campaign status (start, stop, pause)
    """
    campaign = get_object_or_404(Campaign, pk=pk)
    
    # Check permissions
    user = request.user
    if not (user.is_staff or campaign.created_by == user or 
            (hasattr(user, 'profile') and user.profile.is_supervisor())):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        action = data.get('action')
        
        if action == 'start':
            campaign.start_campaign()
            message = f'Campaign "{campaign.name}" started successfully!'
        elif action == 'stop':
            campaign.stop_campaign()
            message = f'Campaign "{campaign.name}" stopped successfully!'
        elif action == 'pause':
            campaign.pause_campaign()
            message = f'Campaign "{campaign.name}" paused successfully!'
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)
        
        return JsonResponse({
            'success': True,
            'message': message,
            'status': campaign.get_status_display(),
            'status_code': campaign.status
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


class CampaignAgentManagementView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Manage campaign agents (assign/remove agents)
    """
    template_name = 'campaigns/campaign_agents.html'

    def test_func(self):
        """Check if user can manage agents for this campaign"""
        campaign = get_object_or_404(Campaign, pk=self.kwargs['pk'])
        user = self.request.user
        return (
            user.is_staff or 
            campaign.created_by == user or
            (hasattr(user, 'profile') and user.profile.is_supervisor())
        )

    def get(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        
        # Get assigned agents
        assigned_agents = CampaignAgent.objects.filter(
            campaign=campaign
        ).select_related('user__profile').order_by('user__username')
        
        # Get available agents (not assigned to this campaign)
        assigned_user_ids = assigned_agents.values_list('user_id', flat=True)
        available_agents = User.objects.filter(
            Q(groups__name='Agent') | Q(groups__name='Supervisor')
        ).exclude(id__in=assigned_user_ids).select_related('profile')
        
        context = {
            'campaign': campaign,
            'assigned_agents': assigned_agents,
            'available_agents': available_agents,
        }
        
        return render(request, self.template_name, context)

    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        action = request.POST.get('action')
        
        if action == 'assign':
            user_ids = request.POST.getlist('user_ids')
            max_calls = request.POST.get('max_calls_per_day')
            priority = request.POST.get('priority', 1)
            
            assigned_count = 0
            for user_id in user_ids:
                try:
                    user = User.objects.get(id=user_id)
                    campaign_agent, created = CampaignAgent.objects.get_or_create(
                        campaign=campaign,
                        user=user,
                        defaults={
                            'max_calls_per_day': int(max_calls) if max_calls else None,
                            'priority': int(priority),
                            'is_active': True
                        }
                    )
                    if created:
                        assigned_count += 1
                except (User.DoesNotExist, ValueError):
                    continue
            
            messages.success(
                request, 
                f'{assigned_count} agent(s) assigned to campaign "{campaign.name}"'
            )
            
        elif action == 'remove':
            agent_ids = request.POST.getlist('agent_ids')
            removed_count = CampaignAgent.objects.filter(
                campaign=campaign,
                id__in=agent_ids
            ).delete()[0]
            
            messages.success(
                request, 
                f'{removed_count} agent(s) removed from campaign "{campaign.name}"'
            )
        
        return redirect('campaigns:agents', pk=pk)


@login_required
@require_http_methods(["GET"])
def campaign_stats_api(request, pk):
    """
    API endpoint for real-time campaign statistics
    """
    campaign = get_object_or_404(Campaign, pk=pk)
    
    # Check permissions
    user = request.user
    if not (user.is_staff or campaign.created_by == user or 
            campaign.assigned_users.filter(id=user.id).exists()):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    today = timezone.now().date()
    
    # Get today's stats
    today_stats = CampaignStats.objects.filter(
        campaign=campaign,
        date=today
    ).first()
    
    # Get agent status
    active_agents = CampaignAgent.objects.filter(
        campaign=campaign,
        is_active=True,
        user__agent_status__status='available'
    ).count()
    
    stats = {
        'calls_made_today': today_stats.calls_made if today_stats else 0,
        'calls_answered_today': today_stats.calls_answered if today_stats else 0,
        'active_agents': active_agents,
        'campaign_status': campaign.status,
        'total_leads': campaign.total_leads,
        'leads_remaining': campaign.leads_remaining,
        'last_updated': timezone.now().isoformat(),
    }
    
    return JsonResponse(stats)


@login_required
def script_management(request, pk):
    """
    Manage campaign scripts
    """
    campaign = get_object_or_404(Campaign, pk=pk)
    
    # Check permissions
    user = request.user
    if not (user.is_staff or campaign.created_by == user or 
            (hasattr(user, 'profile') and user.profile.is_supervisor())):
        messages.error(request, 'Permission denied')
        return redirect('campaigns:detail', pk=pk)
    
    if request.method == 'POST':
        form = ScriptForm(request.POST)
        if form.is_valid():
            script = form.save(commit=False)
            script.created_by = request.user
            script.save()
            script.campaigns.add(campaign)
            
            messages.success(
                request, 
                f'Script "{script.name}" added to campaign successfully!'
            )
            return redirect('campaigns:scripts', pk=pk)
    else:
        form = ScriptForm()
    
    # Get existing scripts for this campaign
    campaign_scripts = campaign.scripts.filter(is_active=True)
    
    # Get available scripts not yet assigned
    available_scripts = Script.objects.filter(
        is_active=True
    ).exclude(campaigns=campaign)
    
    context = {
        'campaign': campaign,
        'form': form,
        'campaign_scripts': campaign_scripts,
        'available_scripts': available_scripts,
    }
    
    return render(request, 'campaigns/campaign_scripts.html', context)


class DispositionManagementView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Manage campaign dispositions
    """
    template_name = 'campaigns/campaign_dispositions.html'

    def test_func(self):
        """Check permissions"""
        campaign = get_object_or_404(Campaign, pk=self.kwargs['pk'])
        user = self.request.user
        return (
            user.is_staff or 
            campaign.created_by == user or
            (hasattr(user, 'profile') and user.profile.is_supervisor())
        )

    def get(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        
        # Get campaign dispositions
        campaign_dispositions = CampaignDisposition.objects.filter(
            campaign=campaign
        ).select_related('disposition').order_by('sort_order')
        
        # Get available dispositions
        assigned_disposition_ids = campaign_dispositions.values_list('disposition_id', flat=True)
        available_dispositions = Disposition.objects.filter(
            is_active=True
        ).exclude(id__in=assigned_disposition_ids)
        
        context = {
            'campaign': campaign,
            'campaign_dispositions': campaign_dispositions,
            'available_dispositions': available_dispositions,
        }
        
        return render(request, self.template_name, context)

    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        action = request.POST.get('action')
        
        if action == 'add':
            disposition_ids = request.POST.getlist('disposition_ids')
            for disposition_id in disposition_ids:
                try:
                    disposition = Disposition.objects.get(id=disposition_id)
                    CampaignDisposition.objects.get_or_create(
                        campaign=campaign,
                        disposition=disposition,
                        defaults={'sort_order': 999}
                    )
                except Disposition.DoesNotExist:
                    continue
            
            messages.success(request, 'Dispositions added successfully!')
            
        elif action == 'remove':
            disposition_ids = request.POST.getlist('campaign_disposition_ids')
            CampaignDisposition.objects.filter(
                campaign=campaign,
                id__in=disposition_ids
            ).delete()
            
            messages.success(request, 'Dispositions removed successfully!')
        
        return redirect('campaigns:dispositions', pk=pk)


@login_required
@require_http_methods(["POST"])
def clone_campaign(request, pk):
    """
    Clone an existing campaign
    """
    original_campaign = get_object_or_404(Campaign, pk=pk)
    
    # Check permissions
    user = request.user
    if not (user.is_staff or 
            (hasattr(user, 'profile') and user.profile.is_manager())):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        # Clone the campaign
        cloned_campaign = Campaign.objects.get(pk=original_campaign.pk)
        cloned_campaign.pk = None
        cloned_campaign.name = f"{original_campaign.name} (Copy)"
        cloned_campaign.campaign_id = None  # Will be auto-generated
        cloned_campaign.status = 'inactive'
        cloned_campaign.is_active = False
        cloned_campaign.created_by = user
        cloned_campaign.total_leads = 0
        cloned_campaign.leads_called = 0
        cloned_campaign.leads_remaining = 0
        cloned_campaign.calls_today = 0
        cloned_campaign.save()
        
        # Clone operating hours
        for hours in original_campaign.operating_hours.all():
            CampaignHours.objects.create(
                campaign=cloned_campaign,
                day_of_week=hours.day_of_week,
                start_time=hours.start_time,
                end_time=hours.end_time,
                is_active=hours.is_active
            )
        
        # Clone dispositions
        for camp_disp in original_campaign.dispositions.all():
            CampaignDisposition.objects.create(
                campaign=cloned_campaign,
                disposition=camp_disp.disposition,
                sort_order=camp_disp.sort_order,
                is_active=camp_disp.is_active
            )
        
        # Clone scripts
        for script in original_campaign.scripts.all():
            script.campaigns.add(cloned_campaign)
        
        return JsonResponse({
            'success': True,
            'message': f'Campaign cloned successfully as "{cloned_campaign.name}"',
            'campaign_id': cloned_campaign.id,
            'redirect_url': reverse_lazy('campaigns:detail', kwargs={'pk': cloned_campaign.id})
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)