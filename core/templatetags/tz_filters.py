"""
core/templatetags/tz_filters.py  –  Phase 4 Timezone Template Filters
=======================================================================

Usage in any template:
    {% load tz_filters %}

    {{ call.start_time | tz_display }}
    {{ call.start_time | tz_display:request.user }}
    {{ call.start_time | as_ist }}
    {{ call.start_time | local_date }}
    {{ call.start_time | local_time }}
    {{ call.start_time | local_datetime }}
    {{ call.start_time | tz_ago }}
    {{ campaign.timezone | tz_offset }}
"""

import logging
from datetime import datetime, timedelta

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _import_utils():
    from core.timezone_utils import (
        to_local, to_ist, format_datetime,
        get_timezone_offset_string, get_system_timezone,
    )
    return to_local, to_ist, format_datetime, get_timezone_offset_string, get_system_timezone


# ──────────────────────────────────────────────
# Filters
# ──────────────────────────────────────────────

@register.filter(name='tz_display')
def tz_display(dt, user=None):
    """
    Convert UTC datetime → system (or user) timezone.
    Returns formatted string like  "11 Feb 2026 02:30 PM IST"

    Usage:
        {{ call.start_time | tz_display }}
        {{ call.start_time | tz_display:request.user }}
    """
    if dt is None:
        return '—'
    try:
        _, _, fmt_dt, _, _ = _import_utils()
        return fmt_dt(dt, user=user, include_tz=True)
    except Exception as e:
        logger.debug(f"tz_display error: {e}")
        return str(dt)


@register.filter(name='as_ist')
def as_ist(dt):
    """
    Convert UTC datetime → IST (Asia/Kolkata).
    Returns: "11 Feb 2026 02:30 PM IST"
    """
    if dt is None:
        return '—'
    try:
        _, to_ist_fn, _, _, _ = _import_utils()
        local = to_ist_fn(dt)
        return local.strftime('%d %b %Y %I:%M %p IST')
    except Exception as e:
        logger.debug(f"as_ist error: {e}")
        return str(dt)


@register.filter(name='local_date')
def local_date(dt, user=None):
    """
    Return date only in system/user timezone.
    Returns: "11 Feb 2026"
    """
    if dt is None:
        return '—'
    try:
        to_local_fn, _, _, _, _ = _import_utils()
        local = to_local_fn(dt, user=user)
        return local.strftime('%d %b %Y')
    except Exception as e:
        logger.debug(f"local_date error: {e}")
        return str(dt)


@register.filter(name='local_time')
def local_time(dt, user=None):
    """
    Return time only in system/user timezone.
    Returns: "02:30 PM IST"
    """
    if dt is None:
        return '—'
    try:
        to_local_fn, _, _, _, _ = _import_utils()
        local = to_local_fn(dt, user=user)
        return local.strftime('%I:%M %p %Z')
    except Exception as e:
        logger.debug(f"local_time error: {e}")
        return str(dt)


@register.filter(name='local_datetime')
def local_datetime(dt, user=None):
    """
    Return full datetime in system/user timezone without timezone label.
    Returns: "11 Feb 2026 02:30 PM"
    """
    if dt is None:
        return '—'
    try:
        to_local_fn, _, _, _, _ = _import_utils()
        local = to_local_fn(dt, user=user)
        return local.strftime('%d %b %Y %I:%M %p')
    except Exception as e:
        logger.debug(f"local_datetime error: {e}")
        return str(dt)


@register.filter(name='tz_ago')
def tz_ago(dt):
    """
    Human-readable relative time, e.g. "3 minutes ago", "2 hours ago".
    Falls back to absolute date if > 7 days.
    """
    if dt is None:
        return '—'
    try:
        import pytz
        from django.utils import timezone as dtz

        now = dtz.now()
        if dtz.is_naive(dt):
            dt = pytz.utc.localize(dt)

        delta = now - dt
        seconds = int(delta.total_seconds())

        if seconds < 0:
            return 'just now'
        if seconds < 60:
            return f'{seconds}s ago'
        minutes = seconds // 60
        if minutes < 60:
            return f'{minutes}m ago'
        hours = minutes // 60
        if hours < 24:
            return f'{hours}h ago'
        days = hours // 24
        if days < 7:
            return f'{days}d ago'

        _, _, fmt_dt, _, _ = _import_utils()
        return fmt_dt(dt, fmt='%d %b %Y', include_tz=False)
    except Exception as e:
        logger.debug(f"tz_ago error: {e}")
        return str(dt)


@register.filter(name='tz_offset')
def tz_offset(tz_name):
    """
    Return UTC offset string for a timezone name.
    e.g.  "Asia/Kolkata" → "UTC+05:30"
    """
    if not tz_name:
        return 'UTC+00:00'
    try:
        _, _, _, get_offset, _ = _import_utils()
        return get_offset(tz_name)
    except Exception as e:
        logger.debug(f"tz_offset error: {e}")
        return 'UTC+00:00'


@register.filter(name='campaign_time')
def campaign_time(campaign):
    """
    Return the *current* local time for a campaign's timezone.
    Useful on dashboards: "Current time in campaign: 02:30 PM IST"
    """
    if campaign is None:
        return '—'
    try:
        from core.timezone_utils import get_campaign_current_time
        current = get_campaign_current_time(campaign)
        return current.strftime('%I:%M %p %Z')
    except Exception as e:
        logger.debug(f"campaign_time error: {e}")
        return '—'


# ──────────────────────────────────────────────
# Simple Tags
# ──────────────────────────────────────────────

@register.simple_tag
def system_timezone():
    """
    Return the current system timezone name.
    Usage:  {% system_timezone %}  → "Asia/Kolkata"
    """
    try:
        from core.timezone_utils import get_system_timezone
        return get_system_timezone()
    except Exception:
        return 'Asia/Kolkata'


@register.simple_tag
def system_time_now(fmt='%d %b %Y %I:%M %p %Z'):
    """
    Current server time in system timezone.
    Usage:  {% system_time_now %}
            {% system_time_now '%H:%M' %}
    """
    try:
        from core.timezone_utils import now_in_tz
        return now_in_tz().strftime(fmt)
    except Exception:
        return ''


@register.inclusion_tag('core/tz_badge.html')
def tz_badge(dt, user=None, label=''):
    """
    Render a compact datetime badge with tooltip showing UTC value.

    Usage:
        {% load tz_filters %}
        {% tz_badge call.start_time request.user %}
        {% tz_badge call.start_time label="Started" %}
    """
    try:
        to_local_fn, _, _, _, _ = _import_utils()
        local_dt = to_local_fn(dt, user=user)
        return {
            'label':       label,
            'display':     local_dt.strftime('%d %b %Y %I:%M %p') if local_dt else '—',
            'tz_abbr':     local_dt.strftime('%Z') if local_dt else '',
            'utc_value':   dt.strftime('%Y-%m-%d %H:%M UTC') if dt else '',
        }
    except Exception:
        return {'label': label, 'display': str(dt), 'tz_abbr': '', 'utc_value': ''}
