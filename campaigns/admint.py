# campaigns/admin.py
from django.contrib import admin
from .models import (
    Campaign, CampaignAgent, Disposition, CampaignDisposition,
    Script, CampaignStats, CampaignHours
)

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'campaign_type', 'dial_method', 'status', 'created_by', 'start_date', 'is_active']
    list_filter = ['campaign_type', 'dial_method', 'status', 'is_active', 'created_at']
    search_fields = ['name', 'description', 'campaign_id']
    readonly_fields = ['campaign_id', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'campaign_id', 'created_by')
        }),
        ('Campaign Settings', {
            'fields': ('campaign_type', 'dial_method', 'status', 'is_active')
        }),
        ('Schedule', {
            'fields': ('start_date', 'end_date', 'daily_start_time', 'daily_end_time', 'timezone')
        }),
        ('Call Settings', {
            'fields': ('max_attempts', 'call_timeout', 'retry_delay', 'dial_ratio', 'max_lines', 'abandon_rate')
        }),
        ('Recording & Monitoring', {
            'fields': ('enable_recording', 'recording_delay', 'monitor_agents')
        }),
        ('Compliance', {
            'fields': ('use_internal_dnc', 'use_campaign_dnc', 'amd_enabled')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

@admin.register(CampaignAgent)
class CampaignAgentAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'user', 'assigned_date', 'is_active', 'calls_made', 'sales_made']
    list_filter = ['is_active', 'assigned_date']
    search_fields = ['campaign__name', 'user__username', 'user__first_name', 'user__last_name']

@admin.register(Disposition)
class DispositionAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'category', 'is_sale', 'requires_callback', 'is_active']
    list_filter = ['category', 'is_sale', 'requires_callback', 'is_active']
    search_fields = ['name', 'code', 'description']

@admin.register(CampaignDisposition)
class CampaignDispositionAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'disposition', 'sort_order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['campaign__name', 'disposition__name']

@admin.register(Script)
class ScriptAdmin(admin.ModelAdmin):
    list_display = ['name', 'script_type', 'is_active', 'created_at']
    list_filter = ['script_type', 'is_active', 'created_at']
    search_fields = ['name', 'description']

@admin.register(CampaignStats)
class CampaignStatsAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'date', 'calls_made', 'calls_answered', 'sales_made']
    list_filter = ['date']
    search_fields = ['campaign__name']
    date_hierarchy = 'date'

@admin.register(CampaignHours)
class CampaignHoursAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'get_day_display', 'start_time', 'end_time', 'is_active']
    list_filter = ['day_of_week', 'is_active']
    search_fields = ['campaign__name']
    
    def get_day_display(self, obj):
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return days[obj.day_of_week] if 0 <= obj.day_of_week < 7 else 'Unknown'
    get_day_display.short_description = 'Day'

# =============================================================================

