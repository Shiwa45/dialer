# core/context_processors.py

from django.conf import settings
from .utils import SettingsManager

def global_settings(request):
    """
    Add global settings to template context
    """
    return {
        'SITE_NAME': SettingsManager.get_setting('SITE_NAME', 'Autodialer System'),
        'COMPANY_NAME': SettingsManager.get_setting('COMPANY_NAME', 'Your Company'),
        'VERSION': SettingsManager.get_setting('VERSION', '1.0.0'),
        'DEBUG': settings.DEBUG,
    }

