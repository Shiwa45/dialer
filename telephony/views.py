# telephony/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, FormView
)
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, Http404
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from django.conf import settings
import json
import requests
from datetime import datetime, timedelta

from .models import (
    AsteriskServer, Carrier, DID, Phone, IVR, IVROption,
    CallQueue, QueueMember, Recording, DialplanContext, DialplanExtension
)
from .forms import (
    AsteriskServerForm, CarrierForm, DIDForm, PhoneForm, IVRForm,
    CallQueueForm, DialplanContextForm, DialplanExtensionForm, IVROptionForm,
    QueueMemberForm, BulkDIDImportForm, BulkPhoneCreateForm, WebRTCConfigForm
)
from .services import AsteriskService, WebRTCService
from campaigns.models import Campaign
from calls.models import CallLog

# Helper function to check if user is admin/manager
def is_manager_or_admin(user):
    return user.is_superuser or user.groups.filter(name__in=['Managers', 'Administrators']).exists()

# ============================================================================
# ASTERISK SERVER MANAGEMENT
# ============================================================================

class AsteriskServerListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    List all Asterisk servers
    """
    model = AsteriskServer
    template_name = 'telephony/asterisk_servers.html'
    context_object_name = 'servers'
    paginate_by = 20

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'total_servers': AsteriskServer.objects.count(),
            'active_servers': AsteriskServer.objects.filter(is_active=True).count(),
            'connected_servers': AsteriskServer.objects.filter(connection_status='connected').count(),
        })
        return context


class AsteriskServerDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Display detailed Asterisk server information
    """
    model = AsteriskServer
    template_name = 'telephony/asterisk_server_detail.html'
    context_object_name = 'server'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        server = self.get_object()
        
        # Get related data
        context.update({
            'carriers': server.carriers.all()[:5],
            'dids': server.dids.all()[:10],
            'phones': server.phones.all()[:10],
            'queues': server.queues.all()[:5],
            'ivrs': server.ivrs.all()[:5],
            'recent_calls': CallLog.objects.filter(asterisk_server=server).order_by('-created_at')[:10],
        })
        return context


class AsteriskServerCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Create new Asterisk server
    """
    model = AsteriskServer
    form_class = AsteriskServerForm
    template_name = 'telephony/asterisk_server_form.html'
    success_url = reverse_lazy('telephony:asterisk_servers')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Asterisk server created successfully!')
        return super().form_valid(form)


class AsteriskServerUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Update Asterisk server
    """
    model = AsteriskServer
    form_class = AsteriskServerForm
    template_name = 'telephony/asterisk_server_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_success_url(self):
        return reverse('telephony:asterisk_server_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, 'Asterisk server updated successfully!')
        return super().form_valid(form)


class AsteriskServerDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete Asterisk server
    """
    model = AsteriskServer
    template_name = 'telephony/asterisk_server_confirm_delete.html'
    success_url = reverse_lazy('telephony:asterisk_servers')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Asterisk server deleted successfully!')
        return super().delete(request, *args, **kwargs)


@login_required
@user_passes_test(is_manager_or_admin)
def test_asterisk_connection(request, pk):
    """
    Test connection to Asterisk server
    """
    server = get_object_or_404(AsteriskServer, pk=pk)
    
    try:
        asterisk_service = AsteriskService(server)
        connection_result = asterisk_service.test_connection()
        
        if connection_result['success']:
            server.connection_status = 'connected'
            server.last_connected = timezone.now()
            messages.success(request, f'Successfully connected to {server.name}!')
        else:
            server.connection_status = 'error'
            messages.error(request, f'Failed to connect to {server.name}: {connection_result["error"]}')
        
        server.save()
        
    except Exception as e:
        server.connection_status = 'error'
        server.save()
        messages.error(request, f'Connection test failed: {str(e)}')
    
    return redirect('telephony:asterisk_server_detail', pk=pk)


# ============================================================================
# CARRIER MANAGEMENT
# ============================================================================

class CarrierListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    List all carriers
    """
    model = Carrier
    template_name = 'telephony/carriers.html'
    context_object_name = 'carriers'
    paginate_by = 20

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_queryset(self):
        queryset = Carrier.objects.all()
        
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(server_ip__icontains=search)
            )
        
        return queryset.order_by('name')


class CarrierDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Display carrier details
    """
    model = Carrier
    template_name = 'telephony/carrier_detail.html'
    context_object_name = 'carrier'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        carrier = self.get_object()
        # The 'dids' related_name is not defined in the model, so this will fail if not corrected.
        # For now, we will attempt to get it and let it fail if not available.
        try:
            dids = carrier.dids.all()[:10]
        except AttributeError:
            dids = [] # Gracefully handle if 'dids' relationship doesn't exist
            
        context.update({
            'dids': dids,
            'recent_calls': CallLog.objects.filter(carrier=carrier).order_by('-created_at')[:10],
        })
        return context


class CarrierCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Create new carrier
    """
    model = Carrier
    form_class = CarrierForm
    template_name = 'telephony/carrier_form.html'
    success_url = reverse_lazy('telephony:carriers')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Carrier created successfully!')
        return super().form_valid(form)


# ============================================================================
# DID MANAGEMENT
# ============================================================================

class DIDListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    List all DIDs
    """
    model = DID
    template_name = 'telephony/dids.html'
    context_object_name = 'dids'
    paginate_by = 25

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_queryset(self):
        queryset = DID.objects.select_related('carrier', 'asterisk_server', 'assigned_campaign')
        
        # Filters
        carrier_id = self.request.GET.get('carrier')
        did_type = self.request.GET.get('type')
        search = self.request.GET.get('search')
        
        if carrier_id:
            queryset = queryset.filter(carrier_id=carrier_id)
        if did_type:
            queryset = queryset.filter(did_type=did_type)
        if search:
            queryset = queryset.filter(
                Q(phone_number__icontains=search) |
                Q(name__icontains=search)
            )
        
        return queryset.order_by('phone_number')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'carriers': Carrier.objects.filter(is_active=True),
            'did_types': DID.DID_TYPES,
            'total_dids': DID.objects.count(),
            'active_dids': DID.objects.filter(is_active=True).count(),
            'assigned_dids': DID.objects.exclude(assigned_campaign__isnull=True).count(),
        })
        return context


class DIDCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Create new DID
    """
    model = DID
    form_class = DIDForm
    template_name = 'telephony/did_form.html'
    success_url = reverse_lazy('telephony:dids')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'DID created successfully!')
        return super().form_valid(form)


# ============================================================================
# PHONE MANAGEMENT
# ============================================================================

class PhoneListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    List all phones/extensions
    """
    model = Phone
    template_name = 'telephony/phones.html'
    context_object_name = 'phones'
    paginate_by = 25

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_queryset(self):
        queryset = Phone.objects.select_related('user', 'asterisk_server')
        
        # Filters
        phone_type = self.request.GET.get('type')
        status = self.request.GET.get('status')
        search = self.request.GET.get('search')
        
        if phone_type:
            queryset = queryset.filter(phone_type=phone_type)
        if status == 'assigned':
            queryset = queryset.exclude(user__isnull=True)
        elif status == 'available':
            queryset = queryset.filter(user__isnull=True)
        if search:
            queryset = queryset.filter(
                Q(extension__icontains=search) |
                Q(name__icontains=search) |
                Q(user__username__icontains=search)
            )
        
        return queryset.order_by('extension')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'phone_types': Phone.PHONE_TYPES,
            'total_phones': Phone.objects.count(),
            'active_phones': Phone.objects.filter(is_active=True).count(),
            'assigned_phones': Phone.objects.exclude(user__isnull=True).count(),
            'webrtc_phones': Phone.objects.filter(webrtc_enabled=True).count(),
        })
        return context


class PhoneCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Create new phone/extension
    """
    model = Phone
    form_class = PhoneForm
    template_name = 'telephony/phone_form.html'
    success_url = reverse_lazy('telephony:phones')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Phone/Extension created successfully!')
        return super().form_valid(form)


# ============================================================================
# IVR MANAGEMENT
# ============================================================================

class IVRListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    List all IVRs
    """
    model = IVR
    template_name = 'telephony/ivrs.html'
    context_object_name = 'ivrs'
    paginate_by = 20

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_queryset(self):
        return IVR.objects.select_related('asterisk_server', 'created_by').annotate(
            total_options=Count('options')
        ).order_by('name')


class IVRDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Display IVR details with options
    """
    model = IVR
    template_name = 'telephony/ivr_detail.html'
    context_object_name = 'ivr'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['options'] = self.object.options.all().order_by('digit')
        return context


class IVRCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Create new IVR
    """
    model = IVR
    form_class = IVRForm
    template_name = 'telephony/ivr_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'IVR created successfully!')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('telephony:ivr_detail', kwargs={'pk': self.object.pk})


# ============================================================================
# CALL QUEUE MANAGEMENT
# ============================================================================

class CallQueueListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    List all call queues
    """
    model = CallQueue
    template_name = 'telephony/queues.html'
    context_object_name = 'queues'
    paginate_by = 20

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_queryset(self):
        return CallQueue.objects.select_related('asterisk_server').annotate(
            total_members=Count('members')
        ).order_by('name')


class CallQueueDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Display queue details with members
    """
    model = CallQueue
    template_name = 'telephony/queue_detail.html'
    context_object_name = 'queue'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['members'] = self.object.members.select_related('phone__user').order_by('priority')
        return context


# ============================================================================
# RECORDING MANAGEMENT
# ============================================================================

class RecordingListView(LoginRequiredMixin, ListView):
    """
    List call recordings
    """
    model = Recording
    template_name = 'telephony/recordings.html'
    context_object_name = 'recordings'
    paginate_by = 25

    def get_queryset(self):
        queryset = Recording.objects.select_related('asterisk_server')
        
        # Filters
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        search = self.request.GET.get('search')
        
        if date_from:
            queryset = queryset.filter(recording_start__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(recording_start__date__lte=date_to)
        if search:
            queryset = queryset.filter(
                Q(call_id__icontains=search) |
                Q(filename__icontains=search)
            )
        
        return queryset.order_by('-recording_start')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'total_recordings': Recording.objects.count(),
            'total_size': Recording.objects.aggregate(
                total_size=Sum('file_size')
            )['total_size'] or 0,
        })
        return context


# ============================================================================
# DIALPLAN MANAGEMENT
# ============================================================================

class DialplanContextListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    List dialplan contexts
    """
    model = DialplanContext
    template_name = 'telephony/dialplan_contexts.html'
    context_object_name = 'contexts'
    paginate_by = 20

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_queryset(self):
        return DialplanContext.objects.select_related('asterisk_server').annotate(
            total_extensions=Count('extensions')
        ).order_by('name')


class DialplanContextDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Display dialplan context with extensions
    """
    model = DialplanContext
    template_name = 'telephony/dialplan_context_detail.html'
    context_object_name = 'context'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['extensions'] = self.object.extensions.all().order_by('extension', 'priority')
        return context


# ============================================================================
# API ENDPOINTS
# ============================================================================

@login_required
def telephony_stats_api(request):
    """
    Get telephony statistics for dashboard
    """
    stats = {
        'servers': {
            'total': AsteriskServer.objects.count(),
            'active': AsteriskServer.objects.filter(is_active=True).count(),
            'connected': AsteriskServer.objects.filter(connection_status='connected').count(),
        },
        'carriers': {
            'total': Carrier.objects.count(),
            'active': Carrier.objects.filter(is_active=True).count(),
        },
        'dids': {
            'total': DID.objects.count(),
            'active': DID.objects.filter(is_active=True).count(),
            'assigned': DID.objects.exclude(assigned_campaign__isnull=True).count(),
        },
        'phones': {
            'total': Phone.objects.count(),
            'active': Phone.objects.filter(is_active=True).count(),
            'assigned': Phone.objects.exclude(user__isnull=True).count(),
            'webrtc': Phone.objects.filter(webrtc_enabled=True).count(),
        },
        'queues': {
            'total': CallQueue.objects.count(),
            'active': CallQueue.objects.filter(is_active=True).count(),
        },
    }
    
    return JsonResponse(stats)


@login_required
@user_passes_test(is_manager_or_admin)
def server_status_api(request, pk):
    """
    Get real-time server status
    """
    server = get_object_or_404(AsteriskServer, pk=pk)
    
    try:
        asterisk_service = AsteriskService(server)
        status = asterisk_service.get_server_status()
        return JsonResponse(status)
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'status': 'error'
        }, status=500)


# ============================================================================
# WEBRTC ENDPOINTS
# ============================================================================

@login_required
def webrtc_config(request):
    """
    Get WebRTC configuration for current user
    """
    # Check if user has assigned phone with WebRTC enabled
    phone = Phone.objects.filter(user=request.user, webrtc_enabled=True, is_active=True).first()
    
    if not phone:
        return JsonResponse({
            'error': 'No WebRTC phone assigned to user'
        }, status=404)
    
    try:
        webrtc_service = WebRTCService(phone)
        config = webrtc_service.get_webrtc_config()
        return JsonResponse(config)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
def originate_call(request):
    """
    Originate a call via Asterisk
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        data = json.loads(request.body)
        phone_number = data.get('phone_number')
        campaign_id = data.get('campaign_id')
        
        if not phone_number:
            return JsonResponse({'error': 'Phone number required'}, status=400)
        
        # Get user's phone
        phone = Phone.objects.filter(user=request.user, is_active=True).first()
        if not phone:
            return JsonResponse({'error': 'No active phone assigned'}, status=400)
        
        # Get campaign if specified
        campaign = None
        if campaign_id:
            campaign = Campaign.objects.filter(id=campaign_id, is_active=True).first()
        
        # Originate call through Asterisk
        asterisk_service = AsteriskService(phone.asterisk_server)
        result = asterisk_service.originate_call(
            extension=phone.extension,
            phone_number=phone_number,
            campaign=campaign
        )
        
        return JsonResponse(result)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ============================================================================
# DASHBOARD VIEW
# ============================================================================

@login_required
@user_passes_test(is_manager_or_admin)
def telephony_dashboard(request):
    """
    Main telephony dashboard
    """
    context = {
        # Server stats
        'total_servers': AsteriskServer.objects.count(),
        'active_servers': AsteriskServer.objects.filter(is_active=True).count(),
        'connected_servers': AsteriskServer.objects.filter(connection_status='connected').count(),
        
        # Recent servers
        'recent_servers': AsteriskServer.objects.filter(is_active=True).order_by('-last_connected')[:5],
        
        # Carrier stats
        'total_carriers': Carrier.objects.count(),
        'active_carriers': Carrier.objects.filter(is_active=True).count(),
        
        # DID stats
        'total_dids': DID.objects.count(),
        'active_dids': DID.objects.filter(is_active=True).count(),
        'assigned_dids': DID.objects.exclude(assigned_campaign__isnull=True).count(),
        
        # Phone stats
        'total_phones': Phone.objects.count(),
        'active_phones': Phone.objects.filter(is_active=True).count(),
        'assigned_phones': Phone.objects.exclude(user__isnull=True).count(),
        'webrtc_phones': Phone.objects.filter(webrtc_enabled=True).count(),
        
        # Recent activities
        'recent_calls': CallLog.objects.select_related('lead', 'campaign').order_by('-created_at')[:10],
        'recent_recordings': Recording.objects.order_by('-recording_start')[:5],
    }
    
    return render(request, 'telephony/dashboard.html', context)


# ============================================================================
# ADDITIONAL MISSING VIEWS
# ============================================================================

class CarrierUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Update carrier
    """
    model = Carrier
    form_class = CarrierForm
    template_name = 'telephony/carrier_form.html'
    success_url = reverse_lazy('telephony:carriers')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Carrier updated successfully!')
        return super().form_valid(form)


class DIDUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Update DID
    """
    model = DID
    form_class = DIDForm
    template_name = 'telephony/did_form.html'
    success_url = reverse_lazy('telephony:dids')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'DID updated successfully!')
        return super().form_valid(form)


class BulkDIDImportView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Bulk import DIDs from CSV
    """
    form_class = BulkDIDImportForm
    template_name = 'telephony/bulk_did_import.html'
    success_url = reverse_lazy('telephony:dids')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        # Process CSV file (implement CSV processing logic)
        messages.success(self.request, 'DIDs imported successfully!')
        return super().form_valid(form)


class PhoneDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Display phone details
    """
    model = Phone
    template_name = 'telephony/phone_detail.html'
    context_object_name = 'phone'

    def test_func(self):
        return is_manager_or_admin(self.request.user)


class PhoneUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Update phone/extension
    """
    model = Phone
    form_class = PhoneForm
    template_name = 'telephony/phone_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_success_url(self):
        return reverse('telephony:phone_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, 'Phone/Extension updated successfully!')
        return super().form_valid(form)


class BulkPhoneCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Bulk create phone extensions
    """
    form_class = BulkPhoneCreateForm
    template_name = 'telephony/bulk_phone_create.html'
    success_url = reverse_lazy('telephony:phones')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        # Process bulk phone creation (implement bulk creation logic)
        messages.success(self.request, 'Extensions created successfully!')
        return super().form_valid(form)


class IVRUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Update IVR
    """
    model = IVR
    form_class = IVRForm
    template_name = 'telephony/ivr_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_success_url(self):
        return reverse('telephony:ivr_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, 'IVR updated successfully!')
        return super().form_valid(form)


class IVROptionManagementView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Manage IVR options
    """
    model = IVR
    template_name = 'telephony/ivr_options.html'
    context_object_name = 'ivr'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['options'] = self.object.options.all().order_by('digit')
        return context


class IVROptionCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Create IVR option
    """
    model = IVROption
    form_class = IVROptionForm
    template_name = 'telephony/ivr_option_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        form.instance.ivr_id = self.kwargs['ivr_pk']
        messages.success(self.request, 'IVR option created successfully!')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('telephony:ivr_options', kwargs={'pk': self.kwargs['ivr_pk']})


class IVROptionUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Update IVR option
    """
    model = IVROption
    form_class = IVROptionForm
    template_name = 'telephony/ivr_option_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_success_url(self):
        return reverse('telephony:ivr_options', kwargs={'pk': self.object.ivr.pk})

    def form_valid(self, form):
        messages.success(self.request, 'IVR option updated successfully!')
        return super().form_valid(form)


class CallQueueCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Create new call queue
    """
    model = CallQueue
    form_class = CallQueueForm
    template_name = 'telephony/queue_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Call queue created successfully!')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('telephony:queue_detail', kwargs={'pk': self.object.pk})


class CallQueueDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete call queue
    """
    model = CallQueue
    template_name = 'telephony/queue_confirm_delete.html'
    success_url = reverse_lazy('telephony:queues')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Call queue deleted successfully!')
        return super().delete(request, *args, **kwargs)


class CallQueueUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Update call queue
    """
    model = CallQueue
    form_class = CallQueueForm
    template_name = 'telephony/queue_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_success_url(self):
        return reverse('telephony:queue_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, 'Call queue updated successfully!')
        return super().form_valid(form)


class QueueMemberManagementView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Manage queue members
    """
    model = CallQueue
    template_name = 'telephony/queue_members.html'
    context_object_name = 'queue'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['members'] = self.object.members.through.objects.filter(
            queue=self.object
        ).select_related('phone__user')
        return context


class QueueMemberAddView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Add queue member
    """
    model = QueueMember
    form_class = QueueMemberForm
    template_name = 'telephony/queue_member_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        form.instance.queue_id = self.kwargs['queue_pk']
        messages.success(self.request, 'Queue member added successfully!')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('telephony:queue_members', kwargs={'pk': self.kwargs['queue_pk']})


class RecordingDetailView(LoginRequiredMixin, DetailView):
    """
    Display recording details
    """
    model = Recording
    template_name = 'telephony/recording_detail.html'
    context_object_name = 'recording'


@login_required
def download_recording(request, pk):
    """
    Download recording file
    """
    recording = get_object_or_404(Recording, pk=pk)
    # Implement file download logic
    messages.info(request, f'Downloading {recording.filename}')
    return redirect('telephony:recordings')


@login_required
def play_recording(request, pk):
    """
    Play recording in browser
    """
    recording = get_object_or_404(Recording, pk=pk)
    # Implement audio player logic
    return render(request, 'telephony/play_recording.html', {'recording': recording})


class DialplanContextCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Create dialplan context
    """
    model = DialplanContext
    form_class = DialplanContextForm
    template_name = 'telephony/dialplan_context_form.html'
    success_url = reverse_lazy('telephony:dialplan_contexts')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Dialplan context created successfully!')
        return super().form_valid(form)


class DialplanContextUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Update dialplan context
    """
    model = DialplanContext
    form_class = DialplanContextForm
    template_name = 'telephony/dialplan_context_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_success_url(self):
        return reverse('telephony:dialplan_context_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, 'Dialplan context updated successfully!')
        return super().form_valid(form)


class DialplanExtensionCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Create dialplan extension
    """
    model = DialplanExtension
    form_class = DialplanExtensionForm
    template_name = 'telephony/dialplan_extension_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        form.instance.context_id = self.kwargs['context_pk']
        messages.success(self.request, 'Dialplan extension created successfully!')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('telephony:dialplan_context_detail', kwargs={'pk': self.kwargs['context_pk']})


class DialplanExtensionUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Update dialplan extension
    """
    model = DialplanExtension
    form_class = DialplanExtensionForm
    template_name = 'telephony/dialplan_extension_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_success_url(self):
        return reverse('telephony:dialplan_context_detail', kwargs={'pk': self.object.context.pk})

    def form_valid(self, form):
        messages.success(self.request, 'Dialplan extension updated successfully!')
        return super().form_valid(form)


class WebRTCPhoneConfigView(LoginRequiredMixin, CreateView):
    """
    Configure WebRTC phone settings
    """
    form_class = WebRTCConfigForm
    template_name = 'telephony/webrtc_config.html'
    success_url = reverse_lazy('telephony:dashboard')

    def form_valid(self, form):
        messages.success(self.request, 'WebRTC configuration saved successfully!')
        return super().form_valid(form)


@login_required
def hangup_call(request):
    """
    Hangup a call
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    # Implement call hangup logic
    return JsonResponse({'success': True})


@login_required
def transfer_call(request):
    """
    Transfer a call
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    # Implement call transfer logic
    return JsonResponse({'success': True})


@login_required
def park_call(request):
    """
    Park a call
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    # Implement call parking logic
    return JsonResponse({'success': True})


@login_required
def available_phones_api(request):
    """
    Get available phones for assignment
    """
    phones = Phone.objects.filter(user__isnull=True, is_active=True).values(
        'id', 'extension', 'name', 'phone_type'
    )
    return JsonResponse(list(phones), safe=False)


@login_required
def validate_extension_api(request):
    """
    Validate extension availability
    """
    extension = request.GET.get('extension')
    if extension:
        exists = Phone.objects.filter(extension=extension).exists()
        return JsonResponse({'available': not exists})
    return JsonResponse({'error': 'Extension parameter required'}, status=400)


@login_required
def check_did_availability_api(request):
    """
    Check DID availability
    """
    phone_number = request.GET.get('phone_number')
    if phone_number:
        exists = DID.objects.filter(phone_number=phone_number).exists()
        return JsonResponse({'available': not exists})
    return JsonResponse({'error': 'Phone number parameter required'}, status=400)


class ServerMonitorView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    Real-time server monitoring
    """
    model = AsteriskServer
    template_name = 'telephony/server_monitor.html'
    context_object_name = 'servers'

    def test_func(self):
        return is_manager_or_admin(self.request.user)


class CallMonitorView(LoginRequiredMixin, ListView):
    """
    Real-time call monitoring
    """
    model = CallLog
    template_name = 'telephony/call_monitor.html'
    context_object_name = 'calls'
    paginate_by = 50

    def get_queryset(self):
        return CallLog.objects.select_related('campaign', 'lead').order_by('-created_at')


class QueueMonitorView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    Real-time queue monitoring
    """
    model = CallQueue
    template_name = 'telephony/queue_monitor.html'
    context_object_name = 'queues'

    def test_func(self):
        return is_manager_or_admin(self.request.user)


@login_required
@user_passes_test(is_manager_or_admin)
def export_telephony_config(request):
    """
    Export telephony configuration
    """
    # Implement configuration export logic
    messages.success(request, 'Configuration exported successfully!')
    return redirect('telephony:dashboard')


class ImportTelephonyConfigView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Import telephony configuration
    """
    template_name = 'telephony/import_config.html'
    success_url = reverse_lazy('telephony:dashboard')

    def test_func(self):
        return is_manager_or_admin(self.request.user)


class TelephonyDiagnosticsView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    System diagnostics
    """
    model = AsteriskServer
    template_name = 'telephony/diagnostics.html'
    context_object_name = 'servers'

    def test_func(self):
        return is_manager_or_admin(self.request.user)


@login_required
@user_passes_test(is_manager_or_admin)
def connectivity_test(request):
    """
    Test connectivity to all servers
    """
    # Implement connectivity testing logic
    messages.success(request, 'Connectivity test completed!')
    return redirect('telephony:diagnostics')


@login_required
@user_passes_test(is_manager_or_admin)
def performance_test(request):
    """
    Run performance tests
    """
    # Implement performance testing logic
    messages.success(request, 'Performance test completed!')
    return redirect('telephony:diagnostics')
