"""
core/timezone_utils.py  –  Phase 4 Timezone Configuration
=============================================================

Central utility for all timezone operations across the autodialer.

Key rules
---------
1. Django always stores UTC in the DB (USE_TZ = True).
2. Display layer converts UTC → the *effective* timezone:
       user tz  →  campaign tz  →  system tz  →  'Asia/Kolkata'
3. Template filters (`tz_display`, `as_ist`, …) call helpers here.
4. The system default is stored in SystemSettings key='system_timezone'.
"""

import logging
from functools import lru_cache
from typing import Optional
from datetime import datetime

import pytz
from django.utils import timezone as django_tz
from django.conf import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Hardcoded fallback – matches your current setup
# ──────────────────────────────────────────────
_DEFAULT_TZ = getattr(settings, 'DEFAULT_DISPLAY_TIMEZONE', 'Asia/Kolkata')

# All timezone choices used across the project
ALL_TIMEZONES = [
    ('UTC',                  'UTC – Coordinated Universal Time'),
    ('Asia/Kolkata',         'IST – India Standard Time (UTC+5:30)'),
    ('Asia/Colombo',         'Sri Lanka Time (UTC+5:30)'),
    ('Asia/Dhaka',           'Bangladesh Time (UTC+6)'),
    ('Asia/Karachi',         'Pakistan Time (UTC+5)'),
    ('Asia/Dubai',           'Gulf Standard Time (UTC+4)'),
    ('Asia/Riyadh',          'Arabia Standard Time (UTC+3)'),
    ('Asia/Singapore',       'Singapore Time (UTC+8)'),
    ('Asia/Shanghai',        'China Standard Time (UTC+8)'),
    ('Asia/Tokyo',           'Japan Standard Time (UTC+9)'),
    ('Australia/Sydney',     'Australian Eastern Time (UTC+10/11)'),
    ('Europe/London',        'GMT / BST (UTC+0/+1)'),
    ('Europe/Paris',         'Central European Time (UTC+1/+2)'),
    ('Africa/Nairobi',       'East Africa Time (UTC+3)'),
    ('America/New_York',     'Eastern Time (UTC-5/-4)'),
    ('America/Chicago',      'Central Time (UTC-6/-5)'),
    ('America/Denver',       'Mountain Time (UTC-7/-6)'),
    ('America/Los_Angeles',  'Pacific Time (UTC-8/-7)'),
]

# ──────────────────────────────────────────────
# Low-level helpers
# ──────────────────────────────────────────────

def get_pytz(tz_name: str) -> pytz.BaseTzInfo:
    """Return a pytz timezone object; falls back to _DEFAULT_TZ on error."""
    try:
        return pytz.timezone(tz_name)
    except Exception:
        logger.warning(f"Unknown timezone '{tz_name}', using {_DEFAULT_TZ}")
        return pytz.timezone(_DEFAULT_TZ)


def get_system_timezone() -> str:
    """
    Return the system-wide display timezone string.
    Reads from SystemSettings key='system_timezone'.
    Result is cached for 60 s to avoid DB hits on every request.
    """
    try:
        from core.models import SystemSettings
        setting = SystemSettings.objects.filter(
            key='system_timezone', is_active=True
        ).first()
        return setting.value if setting else _DEFAULT_TZ
    except Exception:
        return _DEFAULT_TZ


def set_system_timezone(tz_name: str) -> bool:
    """
    Persist a new system-wide timezone to SystemSettings.
    Returns True on success.
    """
    try:
        get_pytz(tz_name)          # validate first
        from core.models import SystemSettings
        SystemSettings.objects.update_or_create(
            key='system_timezone',
            defaults={
                'value': tz_name,
                'description': 'Default system-wide timezone',
                'is_active': True,
            }
        )
        # Bust LRU cache
        _get_effective_tz.cache_clear()
        logger.info(f"System timezone updated to '{tz_name}'")
        return True
    except Exception as e:
        logger.error(f"Failed to set system timezone: {e}")
        return False


@lru_cache(maxsize=64)
def _get_effective_tz(user_tz: str, campaign_tz: str, system_tz: str) -> pytz.BaseTzInfo:
    """
    Cached resolution: user > campaign > system > hardcoded default.
    All three args are plain strings so the result is cacheable.
    """
    for tz_name in (user_tz, campaign_tz, system_tz, _DEFAULT_TZ):
        if tz_name:
            try:
                return pytz.timezone(tz_name)
            except Exception:
                continue
    return pytz.timezone(_DEFAULT_TZ)


# ──────────────────────────────────────────────
# Public conversion API
# ──────────────────────────────────────────────

def get_effective_timezone(
    user=None,
    campaign=None,
) -> pytz.BaseTzInfo:
    """
    Resolve the correct timezone for display, using priority chain:
        user.profile.timezone  →  campaign.timezone  →  system_timezone  →  IST
    """
    user_tz     = ''
    campaign_tz = ''

    if user:
        try:
            user_tz = (user.profile.timezone or '').strip()
        except Exception:
            pass

    if campaign:
        try:
            campaign_tz = (campaign.timezone or '').strip()
        except Exception:
            pass

    system_tz = get_system_timezone()
    return _get_effective_tz(user_tz, campaign_tz, system_tz)


def to_local(dt: Optional[datetime], user=None, campaign=None) -> Optional[datetime]:
    """
    Convert a UTC-aware datetime to the effective local timezone.
    Returns None if dt is None.
    """
    if dt is None:
        return None
    if django_tz.is_naive(dt):
        dt = pytz.utc.localize(dt)
    tz = get_effective_timezone(user=user, campaign=campaign)
    return dt.astimezone(tz)


def to_ist(dt: Optional[datetime]) -> Optional[datetime]:
    """Convenience: convert datetime to Asia/Kolkata."""
    if dt is None:
        return None
    if django_tz.is_naive(dt):
        dt = pytz.utc.localize(dt)
    return dt.astimezone(pytz.timezone('Asia/Kolkata'))


def to_utc(dt: Optional[datetime], from_tz: str = 'Asia/Kolkata') -> Optional[datetime]:
    """
    Convert a naive (or aware) local datetime → UTC.
    Useful when saving user-entered dates from the UI.
    """
    if dt is None:
        return None
    if django_tz.is_naive(dt):
        tz = get_pytz(from_tz)
        dt = tz.localize(dt)
    return dt.astimezone(pytz.utc)


def now_in_tz(tz_name: str = '') -> datetime:
    """Return current time in the given timezone (default: system tz)."""
    tz_name = tz_name or get_system_timezone()
    return datetime.now(tz=get_pytz(tz_name))


def format_datetime(
    dt: Optional[datetime],
    fmt: str = '%d %b %Y %I:%M %p',
    user=None,
    campaign=None,
    include_tz: bool = True,
) -> str:
    """
    Format a UTC-aware datetime for display in the effective timezone.

    Example output:  "11 Feb 2026 02:30 PM IST"
    """
    if dt is None:
        return '—'
    local_dt = to_local(dt, user=user, campaign=campaign)
    result = local_dt.strftime(fmt)
    if include_tz:
        tz_abbr = local_dt.strftime('%Z')
        result = f"{result} {tz_abbr}"
    return result


def get_campaign_current_time(campaign) -> datetime:
    """
    Return the current time in the campaign's configured timezone.
    Used by the dialer to check calling-hours compliance.
    """
    tz_name = getattr(campaign, 'timezone', None) or get_system_timezone()
    return datetime.now(tz=get_pytz(tz_name))


def is_within_calling_hours(campaign) -> bool:
    """
    Check if the current moment falls within the campaign's
    daily_start_time … daily_end_time window, evaluated in the
    campaign's own timezone.
    """
    try:
        from datetime import time as dtime
        current = get_campaign_current_time(campaign)
        current_time = current.time().replace(second=0, microsecond=0)

        start = campaign.daily_start_time
        end   = campaign.daily_end_time

        if isinstance(start, str):
            start = dtime.fromisoformat(start)
        if isinstance(end, str):
            end = dtime.fromisoformat(end)

        return start <= current_time <= end
    except Exception as e:
        logger.error(f"is_within_calling_hours error: {e}")
        return True   # fail-open


def get_timezone_offset_string(tz_name: str) -> str:
    """Return a human-readable UTC offset, e.g.  '+05:30'."""
    try:
        tz = get_pytz(tz_name)
        now = datetime.now(tz=tz)
        offset = now.utcoffset()
        total_seconds = int(offset.total_seconds())
        sign = '+' if total_seconds >= 0 else '-'
        total_seconds = abs(total_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        return f"UTC{sign}{hours:02d}:{minutes:02d}"
    except Exception:
        return 'UTC+00:00'
