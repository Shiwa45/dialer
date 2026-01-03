from django.contrib import admin
from django.utils.html import format_html
from .models import Campaign, CampaignAgent, Disposition, CampaignDisposition, Script, CampaignStats, CampaignHours, OutboundQueue, CampaignCarrier, DialerHopper


class CampaignAgentInline(admin.TabularInline):
    model = CampaignAgent
    extra = 0


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'campaign_type', 'dial_method', 'status', 'dial_speed', 'custom_dials_per_agent',
        'created_at'
    )
    list_filter = ('campaign_type', 'dial_method', 'status', 'dial_speed', 'is_active')
    search_fields = ('name', 'description')
    # Allow simple multi-select for carriers; assigned_users uses through so excluded
    fieldsets = (
        ('Basic', {
            'fields': ('name', 'description', 'campaign_type', 'dial_method', 'status', 'is_active')
        }),
        ('Schedule', {
            'fields': ('start_date', 'end_date', 'daily_start_time', 'daily_end_time', 'timezone')
        }),
        ('Dialing', {
            'fields': (
                'max_attempts', 'call_timeout', 'retry_delay', 'dial_ratio', 'dial_level', 'max_lines', 'abandon_rate',
                'dial_speed', 'custom_dials_per_agent', 'hopper_size', 'hopper_level', 'dial_timeout', 'local_call_time',
            )
        }),
        ('Routing', {
            'fields': ('dial_prefix', )
        }),
        ('Compliance', {
            'fields': ('use_internal_dnc', 'use_campaign_dnc', 'amd_enabled')
        }),
        ('Assignment', {
            'fields': ('created_by',)
        }),
        ('Stats (read-only)', {
            'fields': ('total_leads', 'leads_called', 'leads_remaining', 'calls_today')
        }),
    )
    readonly_fields = ('total_leads', 'leads_called', 'leads_remaining', 'calls_today')
    inlines = [CampaignAgentInline]


@admin.register(Disposition)
class DispositionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'category', 'is_sale', 'requires_callback', 'sort_order', 'is_active')
    list_filter = ('category', 'is_sale', 'requires_callback', 'is_active')
    search_fields = ('name', 'code')


@admin.register(CampaignDisposition)
class CampaignDispositionAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'disposition', 'is_active', 'sort_order')
    list_filter = ('campaign', 'is_active')


@admin.register(Script)
class ScriptAdmin(admin.ModelAdmin):
    list_display = ('name', 'script_type', 'is_active')
    list_filter = ('script_type', 'is_active')
    search_fields = ('name',)
    filter_horizontal = ('campaigns',)


@admin.register(CampaignStats)
class CampaignStatsAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'date', 'calls_made', 'calls_answered', 'calls_dropped')
    list_filter = ('campaign', 'date')


@admin.register(CampaignHours)
class CampaignHoursAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'day_of_week', 'start_time', 'end_time', 'is_active')
    list_filter = ('campaign', 'day_of_week', 'is_active')


@admin.register(OutboundQueue)
class OutboundQueueAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'phone_number', 'status', 'attempts', 'last_tried_at', 'created_at')
    list_filter = ('campaign', 'status')
    search_fields = ('phone_number',)


@admin.register(DialerHopper)
class DialerHopperAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'phone_number', 'priority', 'status_badge', 'hopper_entry_time', 'dialed_at')
    list_filter = ('campaign', 'status', 'priority')
    search_fields = ('phone_number', 'lead__first_name', 'lead__last_name')
    readonly_fields = ('hopper_entry_time', 'locked_at', 'dialed_at', 'completed_at', 'channel_id')
    actions = ['reset_to_new', 'mark_as_failed', 'clear_selected']
    
    def status_badge(self, obj):
        colors = {
            'new': 'green',
            'locked': 'orange',
            'dialing': 'blue',
            'completed': 'gray',
            'dropped': 'red',
            'failed': 'darkred'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color, obj.status.upper()
        )
    status_badge.short_description = 'Status'
    
    def reset_to_new(self, request, queryset):
        count = queryset.update(status='new', locked_by=None, locked_at=None)
        self.message_user(request, f'{count} entries reset to NEW status')
    reset_to_new.short_description = 'Reset selected to NEW'
    
    def mark_as_failed(self, request, queryset):
        count = queryset.update(status='failed')
        self.message_user(request, f'{count} entries marked as FAILED')
    mark_as_failed.short_description = 'Mark selected as FAILED'
    
    def clear_selected(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f'{count} hopper entries deleted')
    clear_selected.short_description = 'Delete selected entries'
