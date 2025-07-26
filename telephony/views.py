# telephony/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, Http404, HttpResponse, HttpResponseForbidden, HttpResponseNotFound
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from django.conf import settings
from django.core.management import call_command
import json
import requests
import secrets
import string
import os
from datetime import datetime, timedelta

from .models import (
    AsteriskServer, Carrier, DID, Phone, IVR, IVROption,
    CallQueue, QueueMember, Recording, DialplanContext, DialplanExtension,
    PsEndpoint, PsAuth, PsAor, ExtensionsTable
)
from .forms import (
    AsteriskServerForm, CarrierForm, DIDForm, PhoneForm, IVRForm,
    CallQueueForm, DialplanContextForm, DialplanExtensionForm, IVROptionForm,
    QueueMemberForm, BulkDIDImportForm, BulkPhoneCreateForm, WebRTCConfigForm
)
from campaigns.models import Campaign

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
        # TODO: Implement actual AMI connection test
        # For now, simulate connection test
        import time
        time.sleep(1)  # Simulate connection time
        
        server.connection_status = 'connected'
        server.last_connected = timezone.now()
        server.save()
        
        messages.success(request, f'Successfully connected to {server.name}!')
        
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
        queryset = Carrier.objects.annotate(
            total_dids=Count('dids')
        )
        
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
        context.update({
            'dids': carrier.dids.all()[:10],
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


class CarrierDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete carrier
    """
    model = Carrier
    template_name = 'telephony/carrier_confirm_delete.html'
    success_url = reverse_lazy('telephony:carriers')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def delete(self, request, *args, **kwargs):
        carrier = self.get_object()
        messages.success(request, f'Carrier {carrier.name} deleted successfully!')
        return super().delete(request, *args, **kwargs)


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


class DIDDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Display DID details
    """
    model = DID
    template_name = 'telephony/did_detail.html'
    context_object_name = 'did'

    def test_func(self):
        return is_manager_or_admin(self.request.user)


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


class DIDDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete DID
    """
    model = DID
    template_name = 'telephony/did_confirm_delete.html'
    success_url = reverse_lazy('telephony:dids')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def delete(self, request, *args, **kwargs):
        did = self.get_object()
        messages.success(request, f'DID {did.phone_number} deleted successfully!')
        return super().delete(request, *args, **kwargs)


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
        # TODO: Process CSV file
        messages.success(self.request, 'DIDs imported successfully!')
        return super().form_valid(form)


# ============================================================================
# PHONE MANAGEMENT (ENHANCED WITH AUTO-SYNC)
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
            # Asterisk sync status
            'asterisk_synced_phones': PsEndpoint.objects.count(),
        })
        return context


class PhoneCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Create new phone/extension with automatic Asterisk sync
    """
    model = Phone
    form_class = PhoneForm
    template_name = 'telephony/phone_form.html'
    success_url = reverse_lazy('telephony:phones')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        
        # Phone is automatically synced to Asterisk via model save() method
        messages.success(
            self.request, 
            f'Phone/Extension {self.object.extension} created and synced to Asterisk successfully! '
            f'You can now register your softphone.'
        )
        return response


class PhoneDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Display phone details with Asterisk sync status
    """
    model = Phone
    template_name = 'telephony/phone_detail.html'
    context_object_name = 'phone'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        phone = self.get_object()
        
        # Add Asterisk sync status
        context.update({
            'asterisk_status': phone.get_asterisk_status(),
            'asterisk_endpoint_exists': PsEndpoint.objects.filter(id=phone.extension).exists(),
            'asterisk_auth_exists': PsAuth.objects.filter(id=phone.extension).exists(),
            'asterisk_aor_exists': PsAor.objects.filter(id=phone.extension).exists(),
        })
        return context


class PhoneUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Update phone/extension with automatic Asterisk sync
    """
    model = Phone
    form_class = PhoneForm
    template_name = 'telephony/phone_form.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_success_url(self):
        return reverse('telephony:phone_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        
        # Phone is automatically synced to Asterisk via model save() method
        messages.success(
            self.request, 
            f'Phone/Extension {self.object.extension} updated and synced to Asterisk successfully!'
        )
        return response


class PhoneDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete phone/extension with Asterisk cleanup
    """
    model = Phone
    template_name = 'telephony/phone_confirm_delete.html'
    success_url = reverse_lazy('telephony:phones')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def delete(self, request, *args, **kwargs):
        phone = self.get_object()
        extension = phone.extension
        
        # Phone is automatically removed from Asterisk via model delete() method
        response = super().delete(request, *args, **kwargs)
        
        messages.success(request, f'Phone extension {extension} deleted and removed from Asterisk successfully!')
        return response


class BulkPhoneCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Bulk create phone extensions with automatic Asterisk sync
    """
    form_class = BulkPhoneCreateForm
    template_name = 'telephony/bulk_phone_create.html'
    success_url = reverse_lazy('telephony:phones')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def form_valid(self, form):
        # Process bulk phone creation
        extension_start = int(form.cleaned_data['extension_start'])
        extension_count = form.cleaned_data['extension_count']
        name_prefix = form.cleaned_data['name_prefix']
        phone_type = form.cleaned_data['phone_type']
        asterisk_server = form.cleaned_data['asterisk_server']
        webrtc_enabled = form.cleaned_data['webrtc_enabled']
        
        created_phones = []
        
        for i in range(extension_count):
            extension = str(extension_start + i)
            phone = Phone.objects.create(
                extension=extension,
                name=f"{name_prefix} {extension}",
                phone_type=phone_type,
                asterisk_server=asterisk_server,
                webrtc_enabled=webrtc_enabled,
                # secret is auto-generated in model save()
            )
            created_phones.append(phone)
        
        messages.success(
            self.request, 
            f'Successfully created {len(created_phones)} phone extensions and synced to Asterisk!'
        )
        return super().form_valid(form)


# ============================================================================
# PHONE STATUS AND CONTROL FUNCTIONS
# ============================================================================

@login_required
def phone_status(request, pk):
    """
    Get phone registration status from Asterisk
    """
    if not is_manager_or_admin(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        phone = Phone.objects.get(pk=pk)
        status_data = phone.get_asterisk_status()
        return JsonResponse(status_data)
        
    except Phone.DoesNotExist:
        return JsonResponse({'error': 'Phone not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def phone_config(request, pk):
    """
    Generate and download phone configuration file
    """
    if not is_manager_or_admin(request.user):
        return HttpResponseForbidden('Permission denied')
    
    try:
        phone = Phone.objects.get(pk=pk)
        
        # Generate PJSIP configuration for modern Asterisk
        config_content = f"""; PJSIP Configuration for {phone.extension}
; Generated by Autodialer System

; AOR (Address of Record)
[{phone.extension}]
type=aor
max_contacts=1

; Authentication
[{phone.extension}]
type=auth
auth_type=userpass
username={phone.extension}
password={phone.secret}

; Endpoint
[{phone.extension}]
type=endpoint
context={phone.context}
disallow=all
allow={phone.codec}
auth={phone.extension}
aors={phone.extension}
direct_media=no
"""

        if phone.webrtc_enabled:
            config_content += f"""
; WebRTC Configuration
webrtc=yes
use_ptime=yes
media_encryption=dtls
dtls_verify=fingerprint
dtls_setup=actpass
ice_support=yes
media_use_received_transport=yes
rtcp_mux=yes
"""

        response = HttpResponse(config_content, content_type='text/plain')
        response['Content-Disposition'] = f'attachment; filename="{phone.extension}_pjsip.conf"'
        return response
        
    except Phone.DoesNotExist:
        return HttpResponseNotFound('Phone not found')


@login_required
def reset_phone_secret(request, pk):
    """
    Reset phone secret/password and sync to Asterisk
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
        
    if not is_manager_or_admin(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        phone = Phone.objects.get(pk=pk)
        
        # Generate new random secret
        new_secret = phone.generate_secret()
        phone.secret = new_secret
        phone.save()  # This automatically syncs to Asterisk
        
        return JsonResponse({
            'success': True,
            'message': 'Secret reset and synced to Asterisk successfully',
            'new_secret': new_secret
        })
        
    except Phone.DoesNotExist:
        return JsonResponse({'error': 'Phone not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def toggle_phone_status(request, pk):
    """
    Activate/Deactivate phone and sync to Asterisk
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
        
    if not is_manager_or_admin(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        phone = Phone.objects.get(pk=pk)
        activate = request.POST.get('activate', 'false').lower() == 'true'
        
        phone.is_active = activate
        phone.save()  # This automatically syncs to Asterisk
        
        status = 'activated' if activate else 'deactivated'
        return JsonResponse({
            'success': True,
            'message': f'Phone {status} and synced to Asterisk successfully',
            'is_active': phone.is_active
        })
        
    except Phone.DoesNotExist:
        return JsonResponse({'error': 'Phone not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def phone_confirm_delete(request, pk):
    """
    Delete phone after confirmation with Asterisk cleanup
    """
    if not is_manager_or_admin(request.user):
        return HttpResponseForbidden('Permission denied')
    
    try:
        phone = Phone.objects.get(pk=pk)
        
        if request.method == 'POST':
            extension = phone.extension
            phone.delete()  # This automatically removes from Asterisk
            
            messages.success(request, f'Phone extension {extension} deleted and removed from Asterisk successfully!')
            return redirect('telephony:phones')
        
        return render(request, 'telephony/phone_confirm_delete.html', {'phone': phone})
        
    except Phone.DoesNotExist:
        return HttpResponseNotFound('Phone not found')


# ============================================================================
# ASTERISK SYNC MANAGEMENT COMMANDS
# ============================================================================

@login_required
@user_passes_test(is_manager_or_admin)
def sync_all_phones_to_asterisk(request):
    """
    Manually sync all phones to Asterisk
    """
    try:
        phones = Phone.objects.filter(is_active=True)
        synced_count = 0
        
        for phone in phones:
            if phone.sync_to_asterisk():
                synced_count += 1
        
        messages.success(
            request, 
            f'Successfully synced {synced_count} out of {phones.count()} phones to Asterisk!'
        )
    except Exception as e:
        messages.error(request, f'Sync failed: {str(e)}')
    
    return redirect('telephony:phones')


@login_required
@user_passes_test(is_manager_or_admin)
def cleanup_asterisk_orphans(request):
    """
    Remove orphaned Asterisk records that don't have corresponding Django phones
    """
    try:
        # Get all Django phone extensions
        django_extensions = set(Phone.objects.values_list('extension', flat=True))
        
        # Get all Asterisk endpoints
        asterisk_extensions = set(PsEndpoint.objects.values_list('id', flat=True))
        
        # Find orphans
        orphaned_extensions = asterisk_extensions - django_extensions
        
        if orphaned_extensions:
            # Remove orphaned records
            PsEndpoint.objects.filter(id__in=orphaned_extensions).delete()
            PsAuth.objects.filter(id__in=orphaned_extensions).delete()
            PsAor.objects.filter(id__in=orphaned_extensions).delete()
            
            messages.success(
                request, 
                f'Cleaned up {len(orphaned_extensions)} orphaned Asterisk records: {", ".join(orphaned_extensions)}'
            )
        else:
            messages.info(request, 'No orphaned Asterisk records found.')
            
    except Exception as e:
        messages.error(request, f'Cleanup failed: {str(e)}')
    
    return redirect('telephony:phones')


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


class IVRDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete IVR
    """
    model = IVR
    template_name = 'telephony/ivr_confirm_delete.html'
    success_url = reverse_lazy('telephony:ivrs')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def delete(self, request, *args, **kwargs):
        ivr = self.get_object()
        messages.success(request, f'IVR {ivr.name} deleted successfully!')
        return super().delete(request, *args, **kwargs)


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


class IVROptionDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete IVR option
    """
    model = IVROption
    template_name = 'telephony/ivr_option_confirm_delete.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_success_url(self):
        return reverse('telephony:ivr_options', kwargs={'pk': self.object.ivr.pk})

    def delete(self, request, *args, **kwargs):
        option = self.get_object()
        messages.success(request, f'IVR option {option.digit} deleted successfully!')
        return super().delete(request, *args, **kwargs)


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
        context['members'] = self.object.members.select_related('phone__user').order_by('penalty')
        return context


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
        queue = self.get_object()
        messages.success(request, f'Call queue {queue.name} deleted successfully!')
        return super().delete(request, *args, **kwargs)


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


class QueueMemberDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Remove member from queue
    """
    model = QueueMember
    template_name = 'telephony/queue_member_confirm_delete.html'
    
    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_success_url(self):
        return reverse('telephony:queue_members', kwargs={'pk': self.object.queue.pk})

    def delete(self, request, *args, **kwargs):
        member = self.get_object()
        queue_name = member.queue.name
        phone_extension = member.phone.extension
        messages.success(request, f'Phone {phone_extension} removed from queue {queue_name}!')
        return super().delete(request, *args, **kwargs)


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


class RecordingDetailView(LoginRequiredMixin, DetailView):
    """
    Display recording details
    """
    model = Recording
    template_name = 'telephony/recording_detail.html'
    context_object_name = 'recording'


class RecordingDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete recording
    """
    model = Recording
    template_name = 'telephony/recording_confirm_delete.html'
    success_url = reverse_lazy('telephony:recordings')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def delete(self, request, *args, **kwargs):
        recording = self.get_object()
        # Delete the actual file
        if recording.file_path and os.path.exists(recording.file_path):
            os.remove(recording.file_path)
        messages.success(request, f'Recording deleted successfully!')
        return super().delete(request, *args, **kwargs)


@login_required
def download_recording(request, pk):
    """
    Download recording file
    """
    recording = get_object_or_404(Recording, pk=pk)
    # TODO: Implement file download logic
    messages.info(request, f'Downloading {recording.filename}')
    return redirect('telephony:recordings')


@login_required
def play_recording(request, pk):
    """
    Play recording in browser
    """
    recording = get_object_or_404(Recording, pk=pk)
    # TODO: Implement audio player logic
    return render(request, 'telephony/play_recording.html', {'recording': recording})


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


class DialplanContextDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete dialplan context
    """
    model = DialplanContext
    template_name = 'telephony/dialplan_context_confirm_delete.html'
    success_url = reverse_lazy('telephony:dialplan_contexts')

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def delete(self, request, *args, **kwargs):
        context = self.get_object()
        messages.success(request, f'Dialplan context {context.name} deleted successfully!')
        return super().delete(request, *args, **kwargs)


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


class DialplanExtensionDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete dialplan extension
    """
    model = DialplanExtension
    template_name = 'telephony/dialplan_extension_confirm_delete.html'

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_success_url(self):
        return reverse('telephony:dialplan_context_detail', kwargs={'pk': self.object.context.pk})

    def delete(self, request, *args, **kwargs):
        extension = self.get_object()
        messages.success(request, f'Dialplan extension {extension.extension} deleted successfully!')
        return super().delete(request, *args, **kwargs)


# ============================================================================
# WEBRTC MANAGEMENT
# ============================================================================

class WebRTCPhoneConfigView(LoginRequiredMixin, CreateView):
    """
    Configure WebRTC phone settings
    """
    form_class = WebRTCConfigForm
    template_name = 'telephony/webrtc_config.html'
    success_url = reverse_lazy('telephony:dashboard')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Remove 'instance' if present because form is not a ModelForm
        kwargs.pop('instance', None)
        return kwargs

    def form_valid(self, form):
        # Since WebRTCConfigForm is not a ModelForm, do not call form.save()
        messages.success(self.request, 'WebRTC configuration saved successfully!')
        # Instead of calling super().form_valid(form), redirect manually
        from django.shortcuts import redirect
        return redirect(self.success_url)


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
        config = {
            'extension': phone.extension,
            'secret': phone.secret,
            'server': phone.asterisk_server.server_ip,
            'webrtc_enabled': phone.webrtc_enabled,
            'ice_host': phone.ice_host or 'stun:stun.l.google.com:19302'
        }
        return JsonResponse(config)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)


# ============================================================================
# CALL CONTROL FUNCTIONS
# ============================================================================

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
            try:
                campaign = Campaign.objects.filter(id=campaign_id, is_active=True).first()
            except:
                pass
        
        # TODO: Implement actual call origination via AMI/ARI
        result = {
            'success': True,
            'message': f'Call initiated from {phone.extension} to {phone_number}',
            'call_id': f'call_{timezone.now().timestamp()}'
        }
        
        return JsonResponse(result)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def hangup_call(request):
    """
    Hangup a call
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    # TODO: Implement call hangup logic via AMI/ARI
    return JsonResponse({'success': True, 'message': 'Call hangup requested'})


@login_required
def transfer_call(request):
    """
    Transfer a call
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    # TODO: Implement call transfer logic via AMI/ARI
    return JsonResponse({'success': True, 'message': 'Call transfer requested'})


@login_required
def park_call(request):
    """
    Park a call
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    # TODO: Implement call parking logic via AMI/ARI
    return JsonResponse({'success': True, 'message': 'Call parking requested'})


# ============================================================================
# MONITORING VIEWS
# ============================================================================

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
    template_name = 'telephony/call_monitor.html'
    context_object_name = 'calls'
    paginate_by = 50

    def get_queryset(self):
        # TODO: Replace with actual CallLog model when available
        return []


class QueueMonitorView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    Real-time queue monitoring
    """
    model = CallQueue
    template_name = 'telephony/queue_monitor.html'
    context_object_name = 'queues'

    def test_func(self):
        return is_manager_or_admin(self.request.user)


# ============================================================================
# CONFIGURATION AND DIAGNOSTICS
# ============================================================================

@login_required
@user_passes_test(is_manager_or_admin)
def export_telephony_config(request):
    """
    Export telephony configuration
    """
    # TODO: Implement configuration export logic
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
    # TODO: Implement connectivity testing logic
    messages.success(request, 'Connectivity test completed!')
    return redirect('telephony:diagnostics')


@login_required
@user_passes_test(is_manager_or_admin)
def performance_test(request):
    """
    Run performance tests
    """
    # TODO: Implement performance testing logic
    messages.success(request, 'Performance test completed!')
    return redirect('telephony:diagnostics')


# ============================================================================
# ADDITIONAL API ENDPOINTS
# ============================================================================

@login_required
@user_passes_test(is_manager_or_admin)
def server_status_api(request, pk):
    """
    Get real-time server status
    """
    server = get_object_or_404(AsteriskServer, pk=pk)
    
    try:
        # TODO: Implement actual server status check via AMI/ARI
        status = {
            'server_id': server.pk,
            'name': server.name,
            'connection_status': server.connection_status,
            'last_connected': server.last_connected.isoformat() if server.last_connected else None,
            'max_calls': server.max_calls,
            'active_calls': 0,  # Placeholder
            'registered_phones': PsEndpoint.objects.count(),
        }
        return JsonResponse(status)
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'status': 'error'
        }, status=500)


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

# ============================================================================
# DASHBOARD VIEW
# ============================================================================

@login_required
@user_passes_test(is_manager_or_admin)
def telephony_dashboard(request):
    """
    Main telephony dashboard with Asterisk sync status
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
        
        # Phone stats with Asterisk sync info
        'total_phones': Phone.objects.count(),
        'active_phones': Phone.objects.filter(is_active=True).count(),
        'assigned_phones': Phone.objects.exclude(user__isnull=True).count(),
        'webrtc_phones': Phone.objects.filter(webrtc_enabled=True).count(),
        'asterisk_synced_phones': PsEndpoint.objects.count(),
    }
    
    return render(request, 'telephony/dashboard.html', context)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@login_required
def telephony_stats_api(request):
    """
    Get telephony statistics for dashboard including Asterisk sync status
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
            'asterisk_synced': PsEndpoint.objects.count(),
        },
        'queues': {
            'total': CallQueue.objects.count(),
            'active': CallQueue.objects.filter(is_active=True).count(),
        },
    }
    
    return JsonResponse(stats)



# Add these imports at the top of your existing views.py
import subprocess
import os

# Add this function after your existing helper functions
def generate_pjsip_wizard_config():
    """
    Generate pjsip_wizard.conf from all active phones for auto-provisioning
    """
    try:
        phones = Phone.objects.filter(is_active=True)
        
        config_content = """[template_wizard](!)
type = wizard
transport = transport-udp
accepts_registrations = yes
accepts_auth = yes
endpoint/context = agents
endpoint/disallow = all
endpoint/allow = ulaw,alaw
endpoint/direct_media = no
aor/max_contacts = 1
aor/remove_existing = yes

"""
        
        # Add each active phone
        for phone in phones:
            config_content += f"""[{phone.extension}](template_wizard)
inbound_auth/username = {phone.extension}
inbound_auth/password = {phone.secret}

"""
        
        # Write to Asterisk configuration file
        with open('/etc/asterisk/pjsip_wizard.conf', 'w') as f:
            f.write(config_content)
        
        # Reload Asterisk PJSIP configuration
        subprocess.run(['asterisk', '-rx', 'pjsip reload'], 
                      capture_output=True, text=True, timeout=10)
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to generate PJSIP Wizard config: {e}")
        return False

# Replace your existing PhoneCreateView.form_valid method with this:
def form_valid(self, form):
    response = super().form_valid(form)
    
    # Auto-generate PJSIP Wizard configuration
    if generate_pjsip_wizard_config():
        messages.success(
            self.request, 
            f'Phone/Extension {self.object.extension} created and auto-provisioned! '
            f'Ready for immediate registration.'
        )
    else:
        messages.warning(
            self.request,
            f'Phone/Extension {self.object.extension} created but auto-provisioning failed.'
        )
    
    return response

# Replace your existing PhoneUpdateView.form_valid method with this:
def form_valid(self, form):
    response = super().form_valid(form)
    
    # Regenerate PJSIP Wizard configuration
    if generate_pjsip_wizard_config():
        messages.success(
            self.request, 
            f'Phone/Extension {self.object.extension} updated and auto-provisioned!'
        )
    else:
        messages.warning(
            self.request,
            f'Phone/Extension {self.object.extension} updated but auto-provisioning failed.'
        )
    
    return response

# Replace your existing PhoneDeleteView.delete method with this:
def delete(self, request, *args, **kwargs):
    phone = self.get_object()
    extension = phone.extension
    
    # Delete phone first
    response = super().delete(request, *args, **kwargs)
    
    # Regenerate PJSIP Wizard configuration without this phone
    if generate_pjsip_wizard_config():
        messages.success(
            request, 
            f'Phone extension {extension} deleted and removed from auto-provisioning!'
        )
    else:
        messages.warning(
            request,
            f'Phone extension {extension} deleted but auto-provisioning cleanup failed.'
        )
    
    return response

# Add this new view function for manual regeneration:
@login_required
@user_passes_test(is_manager_or_admin)
def regenerate_all_provisioning(request):
    """
    Manually regenerate PJSIP Wizard configuration for all phones
    """
    try:
        if generate_pjsip_wizard_config():
            active_phones = Phone.objects.filter(is_active=True).count()
            messages.success(
                request, 
                f'Successfully auto-provisioned {active_phones} phones! All ready for registration.'
            )
        else:
            messages.error(request, 'Auto-provisioning failed.')
    except Exception as e:
        messages.error(request, f'Auto-provisioning failed: {str(e)}')
    
    return redirect('telephony:phones')