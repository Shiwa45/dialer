# settings/urls_timezone.py  –  Phase 4
# Add these to your settings/urls.py or main urls.py

from django.urls import path
from settings.views_timezone import (
    system_timezone_view,
    update_user_timezone,
    timezone_list_api,
)

app_name = 'settings'

urlpatterns = [
    # System-wide timezone (managers only)
    path(
        'timezone/',
        system_timezone_view,
        name='system_timezone',
    ),

    # Per-user timezone preference (any authenticated user, AJAX POST)
    path(
        'timezone/user/',
        update_user_timezone,
        name='update_user_timezone',
    ),

    # JSON API – list all timezones
    path(
        'timezone/api/list/',
        timezone_list_api,
        name='timezone_list_api',
    ),
]
