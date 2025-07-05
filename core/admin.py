# core/admin.py

from django.contrib import admin
from .models import SystemSettings, UserActivity

@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ['key', 'value', 'is_active', 'updated_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['key', 'value', 'description']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'ip_address', 'timestamp']
    list_filter = ['timestamp', 'action']
    search_fields = ['user__username', 'action', 'ip_address']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'