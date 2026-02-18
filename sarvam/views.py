"""
sarvam/views.py  –  Phase 7: Sarvam AI TTS Admin UI
======================================================

Endpoints:
    GET/POST  /sarvam/tts/              – generate new TTS file
    GET       /sarvam/tts/library/      – list cached files
    GET       /sarvam/tts/play/<name>/  – stream audio to browser
    POST      /sarvam/tts/delete/       – delete a cached file
    POST      /sarvam/tts/assign/       – assign TTS file to IVR/campaign
"""

import os
import logging
from pathlib import Path

from django.shortcuts import render, redirect
from django.http import JsonResponse, FileResponse, Http404, StreamingHttpResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages

from sarvam.tts_service import (
    SarvamTTS, LANGUAGE_CHOICES, VOICE_OPTIONS, TTS_AUDIO_DIR, get_tts
)

logger = logging.getLogger(__name__)


def _is_manager(user):
    try:
        return user.is_staff or user.profile.is_manager()
    except Exception:
        return user.is_staff


# ────────────────────────────────────────────────────────────────────
# Generate TTS
# ────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(_is_manager)
@require_http_methods(['GET', 'POST'])
def generate_tts(request):
    """UI to generate a new TTS audio file via Sarvam AI."""
    result = None

    if request.method == 'POST':
        text     = request.POST.get('text', '').strip()
        language = request.POST.get('language', 'hi-IN')
        voice    = request.POST.get('voice', 'aditya')
        name     = request.POST.get('output_name', 'tts_audio').strip()
        force    = request.POST.get('force_regen') == '1'

        if not text:
            messages.error(request, 'Please enter some text to convert.')
        else:
            tts  = get_tts()
            path = tts.generate(text, language, voice, name, force=force)

            if path:
                filename = Path(path).name
                result   = {'success': True, 'filename': filename, 'path': path}
                messages.success(request, f'Audio generated: {filename}')
            else:
                result = {'success': False}
                messages.error(request, 'TTS generation failed. Check SARVAM_API_KEY in settings.')

    # Voice options for the selected language (sent to template as JSON)
    import json
    voice_options_json = json.dumps(VOICE_OPTIONS)

    return render(request, 'sarvam/generate_tts.html', {
        'language_choices': LANGUAGE_CHOICES,
        'voice_options_json': voice_options_json,
        'result': result,
        'tts_configured': bool(get_tts().api_key),
    })


# ────────────────────────────────────────────────────────────────────
# Library
# ────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(_is_manager)
def tts_library(request):
    """List all generated TTS audio files."""
    tts   = get_tts()
    files = tts.list_cached_files()

    # Enrich with readable size
    for f in files:
        kb = f['size'] / 1024
        f['size_fmt'] = f'{kb:.1f} KB' if kb < 1024 else f'{kb/1024:.1f} MB'

    return render(request, 'sarvam/tts_library.html', {
        'files':      files,
        'audio_dir':  TTS_AUDIO_DIR,
        'count':      len(files),
    })


# ────────────────────────────────────────────────────────────────────
# Play / stream
# ────────────────────────────────────────────────────────────────────

@login_required
def tts_play(request, filename):
    """Stream a TTS audio file to the browser."""
    safe_name = Path(filename).name   # strip any path traversal
    filepath  = Path(TTS_AUDIO_DIR) / safe_name

    if not filepath.exists():
        raise Http404('Audio file not found')

    return FileResponse(
        open(filepath, 'rb'),
        content_type='audio/wav',
        as_attachment=False,
    )


# ────────────────────────────────────────────────────────────────────
# Delete
# ────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(_is_manager)
@require_POST
def tts_delete(request):
    """Delete a cached TTS file."""
    filename = request.POST.get('filename', '').strip()
    if not filename:
        return JsonResponse({'success': False, 'error': 'No filename provided'}, status=400)

    tts = get_tts()
    ok  = tts.delete_cached(filename)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': ok})

    if ok:
        messages.success(request, f'Deleted: {filename}')
    else:
        messages.error(request, f'File not found: {filename}')
    return redirect('sarvam:tts_library')


# ────────────────────────────────────────────────────────────────────
# Assign to IVR or campaign
# ────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(_is_manager)
@require_POST
def tts_assign(request):
    """
    Copy a TTS file to Asterisk sounds and optionally update
    a campaign voicemail_file or IVR audio_file reference.
    """
    filename    = request.POST.get('filename', '').strip()
    assign_type = request.POST.get('assign_type')  # 'campaign' | 'ivr'
    target_id   = request.POST.get('target_id')

    if not filename:
        return JsonResponse({'success': False, 'error': 'No filename'}, status=400)

    src = Path(TTS_AUDIO_DIR) / Path(filename).name
    if not src.exists():
        return JsonResponse({'success': False, 'error': 'Source file not found'}, status=404)

    try:
        if assign_type == 'campaign' and target_id:
            from campaigns.models import Campaign
            campaign = Campaign.objects.get(id=target_id)
            # Save as media file reference
            from django.core.files import File
            with open(src, 'rb') as f:
                campaign.voicemail_file.save(filename, File(f), save=True)
            return JsonResponse({'success': True, 'message': f'Assigned to campaign: {campaign.name}'})

        elif assign_type == 'ivr' and target_id:
            from telephony.models import IVR
            ivr = IVR.objects.get(id=target_id)
            from django.core.files import File
            with open(src, 'rb') as f:
                ivr.audio_file.save(filename, File(f), save=True)
            return JsonResponse({'success': True, 'message': f'Assigned to IVR: {ivr.name}'})

        else:
            return JsonResponse({'success': False, 'error': 'Invalid assign_type or target_id'}, status=400)

    except Exception as e:
        logger.error(f'tts_assign error: {e}', exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ────────────────────────────────────────────────────────────────────
# AJAX: generate from quick-dialog
# ────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(_is_manager)
@require_POST
def tts_generate_ajax(request):
    """AJAX endpoint for inline TTS generation in IVR / campaign forms."""
    import json as _json
    try:
        body = _json.loads(request.body)
    except Exception:
        body = request.POST

    text     = (body.get('text') or '').strip()
    language = body.get('language', 'hi-IN')
    voice    = body.get('voice', 'aditya')
    name     = (body.get('output_name') or 'tts').strip()

    if not text:
        return JsonResponse({'success': False, 'error': 'Empty text'}, status=400)

    tts  = get_tts()
    path = tts.generate(text, language, voice, name)

    if path:
        fname = Path(path).name
        return JsonResponse({
            'success':  True,
            'filename': fname,
            'play_url': f'/sarvam/tts/play/{fname}/',
        })

    return JsonResponse({'success': False, 'error': 'Generation failed — check API key'}, status=500)
