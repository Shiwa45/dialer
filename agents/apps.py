# agents/apps.py
from django.apps import AppConfig

class AgentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agents'
    verbose_name = 'Agent Interface'
