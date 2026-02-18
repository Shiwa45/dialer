"""
settings/views_timezone.py  –  Phase 4 Timezone Settings Views
================================================================

Endpoints:
    GET/POST  /settings/timezone/          – admin: system-wide timezone
    POST      /settings/timezone/user/     – any user: update own tz preference
    GET       /settings/timezone/api/list/ – JSON list of all timezones
"""

import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test

from core.timezone_utils import (
    ALL_TIMEZONES,
    get_system_timezone,
    set_system_timezone,
    get_timezone_offset_string,
    now_in_tz,
)

logger = logging.getLogger(__name__)


def _is_manager(user):
    try:
        return user.is_staff or user.profile.is_manager()
    except Exception:
        return user.is_staff


# ──────────────────────────────────────────────────────────────────────────
# System-wide timezone (managers / admins only)
# ──────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(_is_manager)
@require_http_methods(['GET', 'POST'])
def system_timezone_view(request):
    """
    Display and update the system-wide default timezone.
    """
    current_tz   = get_system_timezone()
    current_time = now_in_tz(current_tz).strftime('%d %b %Y  %I:%M:%S %p %Z')

    if request.method == 'POST':
        new_tz = request.POST.get('timezone', '').strip()
        if not new_tz:
            messages.error(request, 'Please select a timezone.')
        else:
            ok = set_system_timezone(new_tz)
            if ok:
                messages.success(
                    request,
                    f'System timezone updated to {new_tz}'
                )
                return redirect('settings:system_timezone')
            else:
                messages.error(request, f'Invalid timezone: {new_tz}')

    # Enrich timezone list with current offset strings
    tz_choices = [
        {
            'value':   tz[0],
            'label':   tz[1],
            'offset':  get_timezone_offset_string(tz[0]),
            'current': tz[0] == current_tz,
        }
        for tz in ALL_TIMEZONES
    ]

    return render(request, 'settings/system_timezone.html', {
        'current_tz':   current_tz,
        'current_time': current_time,
        'tz_choices':   tz_choices,
    })


# ──────────────────────────────────────────────────────────────────────────
# Per-user timezone preference
# ──────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def update_user_timezone(request):
    """
    Update the authenticated user's personal timezone preference.
    Called via AJAX from the profile page or a dropdown in the navbar.
    """
    new_tz = request.POST.get('timezone', '').strip()

    if not new_tz:
        return JsonResponse({'success': False, 'error': 'No timezone provided'}, status=400)

    try:
        import pytz
        pytz.timezone(new_tz)   # validate
    except Exception:
        return JsonResponse({'success': False, 'error': f'Unknown timezone: {new_tz}'}, status=400)

    try:
        profile = request.user.profile
        profile.timezone = new_tz
        profile.save(update_fields=['timezone'])

        logger.info(f"User {request.user.username} set timezone to {new_tz}")
        return JsonResponse({
            'success': True,
            'message': f'Timezone updated to {new_tz}',
            'offset': get_timezone_offset_string(new_tz),
        })
    except Exception as e:
        logger.error(f"Error updating user timezone: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ──────────────────────────────────────────────────────────────────────────
# JSON API – list available timezones
# ──────────────────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['GET'])
def timezone_list_api(request):
    """
    Return JSON array of all available timezones with their UTC offsets.
    Used by dropdowns on front-end.
    """
    data = [
        {
            'value':  tz[0],
            'label':  tz[1],
            'offset': get_timezone_offset_string(tz[0]),
        }
        for tz in ALL_TIMEZONES
    ]
    return JsonResponse({'timezones': data})
