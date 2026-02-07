"""
Recording Views - Phase 2.5

Views for:
1. Recording playback (streaming)
2. Recording download
3. Recording management

Add these to telephony/views.py
"""

import os
import logging
import mimetypes
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from wsgiref.util import FileWrapper

from core.decorators import agent_required, supervisor_required

logger = logging.getLogger(__name__)


@login_required
@agent_required
def stream_recording(request, call_id):
    """
    Stream recording audio for playback
    
    Supports range requests for seeking in audio players.
    """
    from telephony.models import Recording
    from telephony.recording_service import RecordingService
    from calls.models import CallLog
    
    try:
        # Get recording
        service = RecordingService()
        recording = service.get_recording_for_call(call_id)
        
        if not recording:
            # Try to find by call log
            call_log = get_object_or_404(CallLog, id=call_id)
            
            # Check if user has access
            if not _user_can_access_recording(request.user, call_log):
                return HttpResponse('Access denied', status=403)
            
            if call_log.recording_file:
                file_path = service._find_recording_file(
                    call_log.recording_file, 
                    call_log
                )
                if file_path:
                    return _stream_file(request, file_path)
            
            raise Http404('Recording not found')
        
        # Check if file exists
        if not recording.file_path or not os.path.exists(recording.file_path):
            # Try to sync
            call_log = CallLog.objects.filter(id=call_id).first()
            if call_log:
                service.sync_recordings(call_log)
                recording.refresh_from_db()
        
        if not recording.file_path or not os.path.exists(recording.file_path):
            raise Http404('Recording file not found')
        
        # Check access
        call_log = CallLog.objects.filter(id=call_id).first()
        if call_log and not _user_can_access_recording(request.user, call_log):
            return HttpResponse('Access denied', status=403)
        
        return _stream_file(request, recording.file_path)
        
    except Http404:
        raise
    except Exception as e:
        logger.error(f"Error streaming recording {call_id}: {e}")
        raise Http404('Recording not available')


@login_required
@agent_required
def download_recording(request, call_id):
    """
    Download recording file
    """
    from telephony.models import Recording
    from telephony.recording_service import RecordingService
    from calls.models import CallLog
    
    try:
        service = RecordingService()
        recording = service.get_recording_for_call(call_id)
        
        if not recording or not recording.file_path:
            call_log = get_object_or_404(CallLog, id=call_id)
            
            if call_log.recording_file:
                file_path = service._find_recording_file(
                    call_log.recording_file,
                    call_log
                )
                if file_path and os.path.exists(file_path):
                    filename = os.path.basename(file_path)
                    return _download_file(file_path, filename)
            
            raise Http404('Recording not found')
        
        if not os.path.exists(recording.file_path):
            raise Http404('Recording file not found')
        
        # Check access
        call_log = CallLog.objects.filter(id=call_id).first()
        if call_log and not _user_can_access_recording(request.user, call_log):
            return HttpResponse('Access denied', status=403)
        
        filename = recording.filename or f"recording_{call_id}.wav"
        return _download_file(recording.file_path, filename)
        
    except Http404:
        raise
    except Exception as e:
        logger.error(f"Error downloading recording {call_id}: {e}")
        raise Http404('Recording not available')


@login_required
@supervisor_required
def recording_list(request):
    """
    List all recordings (supervisor/manager view)
    """
    from telephony.models import Recording
    from django.core.paginator import Paginator
    
    recordings = Recording.objects.select_related().order_by('-created_at')
    
    # Filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    campaign_id = request.GET.get('campaign')
    agent_id = request.GET.get('agent')
    
    if date_from:
        recordings = recordings.filter(created_at__date__gte=date_from)
    if date_to:
        recordings = recordings.filter(created_at__date__lte=date_to)
    if campaign_id:
        recordings = recordings.filter(call__campaign_id=campaign_id)
    if agent_id:
        recordings = recordings.filter(call__agent_id=agent_id)
    
    paginator = Paginator(recordings, 50)
    page = request.GET.get('page', 1)
    recordings_page = paginator.get_page(page)
    
    return JsonResponse({
        'success': True,
        'recordings': [
            {
                'id': r.id,
                'call_id': r.call_id,
                'filename': r.filename,
                'duration': r.duration,
                'file_size': r.file_size,
                'is_available': r.is_available,
                'created_at': r.created_at.isoformat() if r.created_at else None
            }
            for r in recordings_page
        ],
        'pagination': {
            'page': recordings_page.number,
            'pages': paginator.num_pages,
            'total': paginator.count
        }
    })


@login_required
@supervisor_required
def recording_stats(request):
    """
    Get recording statistics
    """
    from telephony.models import Recording
    from django.db.models import Sum, Count, Avg
    from django.utils import timezone
    from datetime import timedelta
    
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    
    total_recordings = Recording.objects.count()
    available_recordings = Recording.objects.filter(is_available=True).count()
    
    # Today's recordings
    today_count = Recording.objects.filter(created_at__date=today).count()
    
    # This week's recordings
    week_count = Recording.objects.filter(created_at__date__gte=week_ago).count()
    
    # Storage stats
    storage = Recording.objects.filter(is_available=True).aggregate(
        total_size=Sum('file_size'),
        total_duration=Sum('duration'),
        avg_duration=Avg('duration')
    )
    
    return JsonResponse({
        'success': True,
        'stats': {
            'total_recordings': total_recordings,
            'available_recordings': available_recordings,
            'today_count': today_count,
            'week_count': week_count,
            'total_storage_bytes': storage['total_size'] or 0,
            'total_storage_mb': round((storage['total_size'] or 0) / (1024 * 1024), 2),
            'total_duration_seconds': storage['total_duration'] or 0,
            'avg_duration_seconds': round(storage['avg_duration'] or 0, 1)
        }
    })


def _stream_file(request, file_path):
    """
    Stream a file with range request support
    """
    file_size = os.path.getsize(file_path)
    content_type, _ = mimetypes.guess_type(file_path)
    content_type = content_type or 'audio/wav'
    
    # Handle range requests
    range_header = request.META.get('HTTP_RANGE', '').strip()
    
    if range_header:
        # Parse range header
        range_match = range_header.replace('bytes=', '').split('-')
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if range_match[1] else file_size - 1
        
        if start >= file_size:
            return HttpResponse(status=416)  # Range not satisfiable
        
        end = min(end, file_size - 1)
        length = end - start + 1
        
        with open(file_path, 'rb') as f:
            f.seek(start)
            data = f.read(length)
        
        response = HttpResponse(data, content_type=content_type, status=206)
        response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        response['Content-Length'] = length
        response['Accept-Ranges'] = 'bytes'
        
    else:
        # Full file
        response = FileResponse(
            open(file_path, 'rb'),
            content_type=content_type
        )
        response['Content-Length'] = file_size
        response['Accept-Ranges'] = 'bytes'
    
    return response


def _download_file(file_path, filename):
    """
    Return file for download
    """
    content_type, _ = mimetypes.guess_type(file_path)
    content_type = content_type or 'application/octet-stream'
    
    response = FileResponse(
        open(file_path, 'rb'),
        content_type=content_type
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Content-Length'] = os.path.getsize(file_path)
    
    return response


def _user_can_access_recording(user, call_log):
    """
    Check if user can access a recording
    
    Rules:
    - Superusers and staff can access all
    - Supervisors/managers can access their campaign recordings
    - Agents can only access their own recordings
    """
    if user.is_superuser or user.is_staff:
        return True
    
    # Check if supervisor/manager
    if user.groups.filter(name__in=['Supervisor', 'Manager']).exists():
        # Can access recordings from their campaigns
        if call_log.campaign:
            return call_log.campaign.agents.filter(id=user.id).exists() or \
                   call_log.campaign.supervisors.filter(id=user.id).exists()
        return True
    
    # Agents can only access their own recordings
    return call_log.agent_id == user.id


# ============================================================================
# URL Patterns to Add
# ============================================================================
"""
Add these URL patterns to telephony/urls.py:

# Phase 2.5: Recordings
path('recordings/<int:call_id>/stream/', views.stream_recording, name='stream_recording'),
path('recordings/<int:call_id>/download/', views.download_recording, name='download_recording'),
path('api/recordings/', views.recording_list, name='recording_list'),
path('api/recordings/stats/', views.recording_stats, name='recording_stats'),
"""
