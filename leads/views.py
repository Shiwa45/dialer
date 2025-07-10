# leads/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, Avg, F
from django.http import JsonResponse, HttpResponse, Http404
from django.utils import timezone
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views import View
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta, datetime
import json
import csv
import io

from .models import (
    Lead, LeadList, DNCEntry, LeadImport, CallbackSchedule, 
    LeadRecyclingRule, LeadFilter, LeadNote
)
from .forms import (
    LeadCreateForm, LeadUpdateForm, LeadListCreateForm, LeadListUpdateForm,
    LeadImportForm, CallbackCreateForm, LeadSearchForm,
    LeadFilterForm, BulkActionForm
)
from campaigns.models import Campaign


class LeadListView(LoginRequiredMixin, ListView):
    """
    List all leads with filtering and search
    """
    model = Lead
    template_name = 'leads/lead_list.html'
    context_object_name = 'leads'
    paginate_by = 25

    def get_queryset(self):
        queryset = Lead.objects.select_related('lead_list', 'assigned_user').order_by('-created_at')

        # Apply filters
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(phone_number__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(company__icontains=search_query)
            )

        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        lead_list_filter = self.request.GET.get('lead_list')
        if lead_list_filter:
            queryset = queryset.filter(lead_list_id=lead_list_filter)

        campaign_filter = self.request.GET.get('campaign')
        if campaign_filter:
            queryset = queryset.filter(lead_list__campaigns=campaign_filter)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_form'] = LeadSearchForm(self.request.GET)
        context['lead_lists'] = LeadList.objects.all()
        context['campaigns'] = Campaign.objects.filter(is_active=True)
        context['status_choices'] = Lead.STATUS_CHOICES
        
        # Statistics
        context['total_leads'] = Lead.objects.count()
        context['fresh_leads'] = Lead.objects.filter(status='new').count()
        context['contacted_leads'] = Lead.objects.filter(status__in=['contacted', 'callback', 'sale']).count()
        context['dnc_leads'] = Lead.objects.filter(status='dnc').count()
        
        return context


class LeadDetailView(LoginRequiredMixin, DetailView):
    """
    Display detailed lead information
    """
    model = Lead
    template_name = 'leads/lead_detail.html'
    context_object_name = 'lead'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lead = self.get_object()
        
        # Scheduled callbacks
        context['callbacks'] = lead.callbacks.filter(is_completed=False).order_by('scheduled_time')
        
        # Lead notes/comments
        context['notes'] = lead.notes.select_related('user').order_by('-created_at')[:5]
        
        # Related leads (same phone/email)
        context['related_leads'] = Lead.objects.filter(
            Q(phone_number=lead.phone_number) | Q(email=lead.email)
        ).exclude(pk=lead.pk)[:5]
        
        return context


class LeadCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new lead
    """
    model = Lead
    form_class = LeadCreateForm
    template_name = 'leads/lead_create.html'
    success_url = reverse_lazy('leads:list')

    def form_valid(self, form):
        # Check for duplicates
        duplicate_leads = Lead.objects.filter(
            phone_number=form.cleaned_data['phone_number']
        ).exclude(status='dnc')
        
        if duplicate_leads.exists():
            messages.warning(
                self.request,
                f'A lead with this phone number already exists. Consider updating the existing lead.'
            )
        
        messages.success(self.request, 'Lead created successfully!')
        return super().form_valid(form)


class LeadUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update an existing lead
    """
    model = Lead
    form_class = LeadUpdateForm
    template_name = 'leads/lead_update.html'

    def get_success_url(self):
        return reverse_lazy('leads:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, 'Lead updated successfully!')
        return super().form_valid(form)


class LeadDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete a lead (manager required)
    """
    model = Lead
    template_name = 'leads/lead_delete.html'
    success_url = reverse_lazy('leads:list')

    def test_func(self):
        return self.request.user.is_superuser or self.request.user.groups.filter(name='Managers').exists()

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Lead deleted successfully!')
        return super().delete(request, *args, **kwargs)


# Lead List Management Views

class LeadListListView(LoginRequiredMixin, ListView):
    """
    List all lead lists
    """
    model = LeadList
    template_name = 'leads/lead_list_list.html'
    context_object_name = 'lead_lists'
    paginate_by = 20

    def get_queryset(self):
        queryset = LeadList.objects.annotate(
            lead_count=Count('leads'),
            active_leads=Count('leads', filter=Q(leads__status='new')),
            contacted_leads=Count('leads', filter=Q(leads__status__in=['contacted', 'callback', 'sale']))
        ).order_by('-created_at')

        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        return queryset


class LeadListDetailView(LoginRequiredMixin, DetailView):
    """
    Display detailed lead list information
    """
    model = LeadList
    template_name = 'leads/lead_list_detail.html'
    context_object_name = 'lead_list'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lead_list = self.get_object()
        
        # Lead statistics
        leads = lead_list.leads.all()
        context['total_leads'] = leads.count()
        context['fresh_leads'] = leads.filter(status='new').count()
        context['contacted_leads'] = leads.filter(status__in=['contacted', 'callback', 'sale']).count()
        context['dnc_leads'] = leads.filter(status='dnc').count()
        
        # Recent leads
        context['recent_leads'] = leads.order_by('-created_at')[:10]
        
        return context


class LeadListCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new lead list
    """
    model = LeadList
    form_class = LeadListCreateForm
    template_name = 'leads/lead_list_create.html'
    success_url = reverse_lazy('leads:lead_lists')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Lead list created successfully!')
        return super().form_valid(form)


class LeadListUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update an existing lead list
    """
    model = LeadList
    form_class = LeadListUpdateForm
    template_name = 'leads/lead_list_update.html'

    def get_success_url(self):
        return reverse_lazy('leads:lead_list_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, 'Lead list updated successfully!')
        return super().form_valid(form)


class LeadListDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete a lead list (manager required)
    """
    model = LeadList
    template_name = 'leads/lead_list_delete.html'
    success_url = reverse_lazy('leads:lead_lists')

    def test_func(self):
        return self.request.user.is_superuser or self.request.user.groups.filter(name='Managers').exists()


class LeadListLeadsView(LoginRequiredMixin, ListView):
    """
    Show leads within a specific lead list
    """
    model = Lead
    template_name = 'leads/lead_list_leads.html'
    context_object_name = 'leads'
    paginate_by = 25

    def get_queryset(self):
        self.lead_list = get_object_or_404(LeadList, pk=self.kwargs['pk'])
        return self.lead_list.leads.select_related('assigned_user').order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lead_list'] = self.lead_list
        return context


# Lead Import/Export Views

class LeadImportView(LoginRequiredMixin, CreateView):
    """
    Import leads from CSV/Excel files
    """
    model = LeadImport
    form_class = LeadImportForm
    template_name = 'leads/lead_import.html'
    success_url = reverse_lazy('leads:list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        lead_import = form.save()
        
        # Start async processing
        from core.tasks import process_lead_import_task
        process_lead_import_task.delay(lead_import.id)
        
        messages.success(
            self.request,
            f'Lead import "{lead_import.name}" started. You will be notified when complete.'
        )
        return redirect('leads:import_detail', pk=lead_import.pk)


class LeadImportDetailView(LoginRequiredMixin, DetailView):
    """
    Show lead import progress and results
    """
    model = LeadImport
    template_name = 'leads/lead_import_detail.html'
    context_object_name = 'lead_import'


@login_required
@require_http_methods(["GET"])
def lead_import_status(request, pk):
    """
    AJAX endpoint for import progress
    """
    lead_import = get_object_or_404(LeadImport, pk=pk)
    
    return JsonResponse({
        'status': lead_import.status,
        'progress': lead_import.progress_percentage(),
        'processed_rows': lead_import.processed_rows,
        'total_rows': lead_import.total_rows,
        'successful_imports': lead_import.successful_imports,
        'failed_imports': lead_import.failed_imports,
        'duplicate_count': lead_import.duplicate_count,
        'error_message': lead_import.error_message,
    })


@login_required
@require_http_methods(["GET"])
def lead_export(request):
    """
    Export leads to CSV
    """
    # Get filter parameters
    status_filter = request.GET.get('status')
    lead_list_filter = request.GET.get('lead_list')
    
    queryset = Lead.objects.select_related('lead_list', 'assigned_user')
    
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if lead_list_filter:
        queryset = queryset.filter(lead_list_id=lead_list_filter)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="leads_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'First Name', 'Last Name', 'Phone Number', 'Email', 'Company',
        'Address', 'City', 'State', 'Zip Code', 'Status', 'Lead List',
        'Assigned User', 'Created Date', 'Last Contact'
    ])
    
    for lead in queryset:
        writer.writerow([
            lead.first_name,
            lead.last_name,
            lead.phone_number,
            lead.email or '',
            lead.company or '',
            lead.address or '',
            lead.city or '',
            lead.state or '',
            lead.zip_code or '',
            lead.get_status_display(),
            lead.lead_list.name if lead.lead_list else '',
            lead.assigned_user.username if lead.assigned_user else '',
            lead.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            lead.last_contact_date.strftime('%Y-%m-%d %H:%M:%S') if lead.last_contact_date else ''
        ])
    
    return response


@login_required
@require_http_methods(["GET"])
def lead_list_export(request, pk):
    """
    Export specific lead list to CSV
    """
    lead_list = get_object_or_404(LeadList, pk=pk)
    leads = lead_list.leads.select_related('assigned_user')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{lead_list.name}_leads.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'First Name', 'Last Name', 'Phone Number', 'Email', 'Company',
        'Address', 'City', 'State', 'Zip Code', 'Status',
        'Assigned User', 'Created Date', 'Last Contact'
    ])
    
    for lead in leads:
        writer.writerow([
            lead.first_name,
            lead.last_name,
            lead.phone_number,
            lead.email or '',
            lead.company or '',
            lead.address or '',
            lead.city or '',
            lead.state or '',
            lead.zip_code or '',
            lead.get_status_display(),
            lead.assigned_user.username if lead.assigned_user else '',
            lead.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            lead.last_contact_date.strftime('%Y-%m-%d %H:%M:%S') if lead.last_contact_date else ''
        ])
    
    return response


# DNC Management Views

class DNCListView(LoginRequiredMixin, ListView):
    """
    List all DNC entries
    """
    model = DNCEntry
    template_name = 'leads/dnc_list.html'
    context_object_name = 'dnc_entries'
    paginate_by = 25

    def get_queryset(self):
        queryset = DNCEntry.objects.select_related('added_by').order_by('-created_at')
        
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(phone_number__icontains=search_query) |
                Q(reason__icontains=search_query)
            )
        
        return queryset


class DNCCreateView(LoginRequiredMixin, CreateView):
    """
    Add phone number to DNC list
    """
    model = DNCEntry
    template_name = 'leads/dnc_create.html'
    fields = ['phone_number', 'reason']
    success_url = reverse_lazy('leads:dnc_list')

    def form_valid(self, form):
        form.instance.added_by = self.request.user
        
        # Mark related leads as DNC
        Lead.objects.filter(phone_number=form.cleaned_data['phone_number']).update(
            status='dnc',
            last_contact_date=timezone.now()
        )
        
        messages.success(self.request, 'Phone number added to DNC list!')
        return super().form_valid(form)


@login_required
@require_http_methods(["GET"])
def dnc_export(request):
    """
    Export DNC list to CSV
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="dnc_list.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Phone Number', 'Reason', 'Added By', 'Date Added'])
    
    for entry in DNCEntry.objects.select_related('added_by'):
        writer.writerow([
            entry.phone_number,
            entry.reason,
            entry.added_by.username if entry.added_by else '',
            entry.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    return response


@login_required
@require_POST
def dnc_check(request):
    """
    AJAX endpoint to check if phone number is in DNC
    """
    phone_number = request.POST.get('phone_number')
    
    if not phone_number:
        return JsonResponse({'error': 'Phone number required'}, status=400)
    
    is_dnc = DNCEntry.objects.filter(phone_number=phone_number).exists()
    
    return JsonResponse({
        'is_dnc': is_dnc,
        'phone_number': phone_number
    })


# Callback Management Views

class CallbackListView(LoginRequiredMixin, ListView):
    """
    List scheduled callbacks
    """
    model = CallbackSchedule
    template_name = 'leads/callback_list.html'
    context_object_name = 'callbacks'
    paginate_by = 25

    def get_queryset(self):
        queryset = CallbackSchedule.objects.select_related('lead', 'agent', 'campaign').order_by('scheduled_time')
        
        # Filter by agent if specified
        agent_filter = self.request.GET.get('agent')
        if agent_filter:
            queryset = queryset.filter(agent_id=agent_filter)
        
        # Filter by completion status
        status_filter = self.request.GET.get('status', 'pending')
        if status_filter == 'pending':
            queryset = queryset.filter(is_completed=False)
        elif status_filter == 'completed':
            queryset = queryset.filter(is_completed=True)
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['agents'] = User.objects.filter(groups__name='Agents')
        context['overdue_count'] = CallbackSchedule.objects.filter(
            is_completed=False,
            scheduled_time__lt=timezone.now()
        ).count()
        return context


class CallbackCreateView(LoginRequiredMixin, CreateView):
    """
    Schedule a callback
    """
    model = CallbackSchedule
    form_class = CallbackCreateForm
    template_name = 'leads/callback_create.html'
    success_url = reverse_lazy('leads:callbacks')

    def form_valid(self, form):
        messages.success(self.request, 'Callback scheduled successfully!')
        return super().form_valid(form)


@login_required
@require_POST
def complete_callback(request, pk):
    """
    Mark callback as completed
    """
    callback = get_object_or_404(CallbackSchedule, pk=pk)
    callback.is_completed = True
    callback.completed_at = timezone.now()
    callback.save()
    
    messages.success(request, 'Callback marked as completed!')
    return redirect('leads:callbacks')


@login_required
@require_http_methods(["GET"])
def upcoming_callbacks(request):
    """
    API endpoint for upcoming callbacks
    """
    callbacks = CallbackSchedule.objects.filter(
        agent=request.user,
        is_completed=False,
        scheduled_time__date=timezone.now().date()
    ).select_related('lead', 'campaign')
    
    callback_data = [{
        'id': cb.id,
        'lead_name': cb.lead.get_full_name(),
        'phone_number': cb.lead.phone_number,
        'scheduled_time': cb.scheduled_time.strftime('%H:%M'),
        'campaign': cb.campaign.name,
        'notes': cb.notes
    } for cb in callbacks]
    
    return JsonResponse({'callbacks': callback_data})


# AJAX Endpoints

@login_required
@require_http_methods(["GET"])
def lead_search_ajax(request):
    """
    AJAX search for leads
    """
    query = request.GET.get('q', '')
    limit = int(request.GET.get('limit', 10))
    
    if len(query) < 2:
        return JsonResponse({'leads': []})
    
    leads = Lead.objects.filter(
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(phone_number__icontains=query) |
        Q(email__icontains=query)
    ).select_related('lead_list')[:limit]
    
    lead_data = [{
        'id': lead.id,
        'name': lead.get_full_name(),
        'phone_number': lead.phone_number,
        'email': lead.email,
        'status': lead.get_status_display(),
        'lead_list': lead.lead_list.name if lead.lead_list else ''
    } for lead in leads]
    
    return JsonResponse({'leads': lead_data})


@login_required
@require_POST
def validate_phone_ajax(request):
    """
    AJAX phone number validation
    """
    phone_number = request.POST.get('phone_number', '')
    
    if not phone_number:
        return JsonResponse({'valid': False, 'message': 'Phone number required'})
    
    # Basic phone validation
    import re
    phone_pattern = re.compile(r'^\+?1?[-.\s]?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})$')
    
    if not phone_pattern.match(phone_number):
        return JsonResponse({
            'valid': False,
            'message': 'Invalid phone number format'
        })
    
    # Check if number is in DNC
    is_dnc = DNCEntry.objects.filter(phone_number=phone_number).exists()
    if is_dnc:
        return JsonResponse({
            'valid': False,
            'message': 'Phone number is in Do Not Call list',
            'is_dnc': True
        })
    
    return JsonResponse({
        'valid': True,
        'message': 'Valid phone number',
        'is_dnc': False
    })


@login_required
@require_POST
def duplicate_check_ajax(request):
    """
    AJAX duplicate lead check
    """
    phone_number = request.POST.get('phone_number', '')
    email = request.POST.get('email', '')
    exclude_id = request.POST.get('exclude_id')
    
    duplicates = Lead.objects.none()
    
    if phone_number:
        phone_duplicates = Lead.objects.filter(phone_number=phone_number)
        if exclude_id:
            phone_duplicates = phone_duplicates.exclude(id=exclude_id)
        duplicates = duplicates | phone_duplicates
    
    if email:
        email_duplicates = Lead.objects.filter(email=email)
        if exclude_id:
            email_duplicates = email_duplicates.exclude(id=exclude_id)
        duplicates = duplicates | email_duplicates
    
    duplicate_data = [{
        'id': lead.id,
        'name': lead.get_full_name(),
        'phone_number': lead.phone_number,
        'email': lead.email,
        'status': lead.get_status_display(),
        'created_at': lead.created_at.strftime('%Y-%m-%d')
    } for lead in duplicates.distinct()[:5]]
    
    return JsonResponse({
        'has_duplicates': len(duplicate_data) > 0,
        'duplicates': duplicate_data
    })


@login_required
@require_POST
def bulk_action_ajax(request):
    """
    Handle bulk actions on leads
    """
    action = request.POST.get('action')
    lead_ids = request.POST.getlist('lead_ids[]')
    
    if not action or not lead_ids:
        return JsonResponse({'success': False, 'message': 'Action and lead IDs required'})
    
    leads = Lead.objects.filter(id__in=lead_ids)
    count = leads.count()
    
    if action == 'delete':
        if not (request.user.is_superuser or request.user.groups.filter(name='Managers').exists()):
            return JsonResponse({'success': False, 'message': 'Permission denied'})
        leads.delete()
        message = f'{count} leads deleted successfully'
    
    elif action == 'mark_dnc':
        leads.update(status='dnc', last_contact_date=timezone.now())
        # Add to DNC list
        for lead in leads:
            DNCEntry.objects.get_or_create(
                phone_number=lead.phone_number,
                defaults={'reason': 'Bulk action', 'added_by': request.user}
            )
        message = f'{count} leads marked as DNC'
    
    elif action == 'assign_list':
        lead_list_id = request.POST.get('lead_list_id')
        if not lead_list_id:
            return JsonResponse({'success': False, 'message': 'Lead list ID required'})
        try:
            lead_list = LeadList.objects.get(id=lead_list_id)
            leads.update(lead_list=lead_list)
            message = f'{count} leads assigned to {lead_list.name}'
        except LeadList.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Lead list not found'})
    
    elif action == 'change_status':
        new_status = request.POST.get('new_status')
        if not new_status:
            return JsonResponse({'success': False, 'message': 'New status required'})
        leads.update(status=new_status, last_contact_date=timezone.now())
        message = f'{count} leads status updated'
    
    else:
        return JsonResponse({'success': False, 'message': 'Invalid action'})
    
    return JsonResponse({'success': True, 'message': message})


# API Endpoints

@login_required
@require_http_methods(["GET"])
def lead_stats_api(request):
    """
    API endpoint for lead statistics
    """
    total_leads = Lead.objects.count()
    fresh_leads = Lead.objects.filter(status='new').count()
    contacted_leads = Lead.objects.filter(status__in=['contacted', 'callback']).count()
    sales = Lead.objects.filter(status='sale').count()
    dnc_leads = Lead.objects.filter(status='dnc').count()
    
    # Today's activity
    today = timezone.now().date()
    today_leads = Lead.objects.filter(created_at__date=today).count()
    today_contacts = Lead.objects.filter(last_contact_date__date=today).count()
    
    return JsonResponse({
        'total_leads': total_leads,
        'fresh_leads': fresh_leads,
        'contacted_leads': contacted_leads,
        'sales': sales,
        'dnc_leads': dnc_leads,
        'today_leads': today_leads,
        'today_contacts': today_contacts,
        'conversion_rate': round((sales / total_leads * 100) if total_leads > 0 else 0, 2),
        'contact_rate': round((contacted_leads / total_leads * 100) if total_leads > 0 else 0, 2)
    })


@login_required
@require_http_methods(["GET"])
def import_progress_api(request, pk):
    """
    API endpoint for import progress updates
    """
    try:
        lead_import = LeadImport.objects.get(pk=pk, user=request.user)
        
        return JsonResponse({
            'status': lead_import.status,
            'progress': lead_import.progress_percentage(),
            'processed_rows': lead_import.processed_rows,
            'total_rows': lead_import.total_rows,
            'successful_imports': lead_import.successful_imports,
            'failed_imports': lead_import.failed_imports,
            'duplicate_count': lead_import.duplicate_count,
            'error_message': lead_import.error_message,
            'created_at': lead_import.created_at.isoformat(),
            'updated_at': lead_import.updated_at.isoformat()
        })
    
    except LeadImport.DoesNotExist:
        return JsonResponse({'error': 'Import not found'}, status=404)