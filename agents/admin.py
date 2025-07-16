# agents/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    AgentQueue, AgentScript, AgentHotkey, AgentBreakCode,
    AgentSkill, AgentPerformanceGoal, AgentNote,
    AgentWebRTCSession, AgentCallbackTask
)


@admin.register(AgentQueue)
class AgentQueueAdmin(admin.ModelAdmin):
    list_display = [
        'agent', 'campaign', 'is_active', 'priority', 
        'max_concurrent_calls', 'assigned_date'
    ]
    list_filter = ['is_active', 'campaign', 'assigned_date']
    search_fields = ['agent__username', 'agent__first_name', 'agent__last_name', 'campaign__name']
    ordering = ['priority', 'assigned_date']
    
    fieldsets = (
        ('Assignment', {
            'fields': ('agent', 'campaign', 'is_active', 'priority')
        }),
        ('Call Settings', {
            'fields': ('max_concurrent_calls', 'wrap_up_time', 'auto_answer')
        }),
        ('Permissions', {
            'fields': ('receive_inbound', 'make_outbound')
        }),
        ('Management', {
            'fields': ('assigned_by',),
            'classes': ('collapse',)
        })
    )
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing existing object
            return ['assigned_date', 'assigned_by']
        return ['assigned_by']
    
    def save_model(self, request, obj, form, change):
        if not change:  # New object
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(AgentScript)
class AgentScriptAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'script_type', 'campaign', 'is_global', 
        'is_active', 'display_order', 'created_by'
    ]
    list_filter = ['script_type', 'is_global', 'is_active', 'campaign']
    search_fields = ['name', 'content']
    ordering = ['display_order', 'name']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'script_type', 'content')
        }),
        ('Assignment', {
            'fields': ('campaign', 'is_global')
        }),
        ('Display Settings', {
            'fields': ('is_active', 'display_order', 'auto_display')
        })
    )
    
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ['created_by']
        return []
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(AgentHotkey)
class AgentHotkeyAdmin(admin.ModelAdmin):
    list_display = [
        'agent', 'key_combination', 'action_type', 
        'disposition', 'is_active'
    ]
    list_filter = ['action_type', 'is_active']
    search_fields = ['agent__username', 'key_combination', 'description']
    ordering = ['agent__username', 'key_combination']
    
    fieldsets = (
        ('Hotkey Configuration', {
            'fields': ('agent', 'key_combination', 'action_type', 'description')
        }),
        ('Action Details', {
            'fields': ('disposition', 'transfer_number', 'script')
        }),
        ('Settings', {
            'fields': ('is_active',)
        })
    )


@admin.register(AgentBreakCode)
class AgentBreakCodeAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'name', 'is_paid', 'max_duration', 
        'requires_approval', 'is_active', 'display_order'
    ]
    list_filter = ['is_paid', 'requires_approval', 'is_active']
    search_fields = ['code', 'name', 'description']
    ordering = ['display_order', 'name']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'description')
        }),
        ('Settings', {
            'fields': ('is_paid', 'max_duration', 'requires_approval', 'is_active')
        }),
        ('Display', {
            'fields': ('display_order', 'color_code')
        })
    )


@admin.register(AgentSkill)
class AgentSkillAdmin(admin.ModelAdmin):
    list_display = [
        'agent', 'skill_name', 'proficiency_level', 
        'certified', 'certification_expires', 'can_train_others'
    ]
    list_filter = ['proficiency_level', 'certified', 'can_train_others', 'is_active']
    search_fields = ['agent__username', 'skill_name']
    ordering = ['agent__username', 'skill_name']
    
    fieldsets = (
        ('Skill Information', {
            'fields': ('agent', 'skill_name', 'proficiency_level')
        }),
        ('Certification', {
            'fields': ('certified', 'certification_date', 'certification_expires')
        }),
        ('Status', {
            'fields': ('can_train_others', 'is_active', 'verified_by')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        })
    )


@admin.register(AgentPerformanceGoal)
class AgentPerformanceGoalAdmin(admin.ModelAdmin):
    list_display = [
        'agent', 'goal_type', 'target_value', 'current_value',
        'progress_display', 'period_type', 'achieved', 'is_active'
    ]
    list_filter = ['goal_type', 'period_type', 'achieved', 'is_active']
    search_fields = ['agent__username', 'notes']
    ordering = ['-start_date']
    
    fieldsets = (
        ('Goal Information', {
            'fields': ('agent', 'goal_type', 'period_type')
        }),
        ('Targets', {
            'fields': ('target_value', 'current_value')
        }),
        ('Time Period', {
            'fields': ('start_date', 'end_date')
        }),
        ('Status', {
            'fields': ('is_active', 'achieved', 'achievement_date')
        }),
        ('Management', {
            'fields': ('set_by', 'notes'),
            'classes': ('collapse',)
        })
    )
    
    def progress_display(self, obj):
        progress = obj.progress_percentage()
        color = 'green' if progress >= 100 else 'orange' if progress >= 75 else 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color,
            progress
        )
    progress_display.short_description = 'Progress'
    
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ['set_by']
        return []
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.set_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(AgentNote)
class AgentNoteAdmin(admin.ModelAdmin):
    list_display = [
        'agent', 'note_type', 'subject', 'is_private', 
        'is_important', 'created_by', 'created_at'
    ]
    list_filter = ['note_type', 'is_private', 'is_important', 'created_at']
    search_fields = ['agent__username', 'subject', 'content']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Note Information', {
            'fields': ('agent', 'note_type', 'subject', 'content')
        }),
        ('Settings', {
            'fields': ('is_private', 'is_important')
        })
    )
    
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ['created_by']
        return []
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(AgentWebRTCSession)
class AgentWebRTCSessionAdmin(admin.ModelAdmin):
    list_display = [
        'agent', 'status', 'sip_extension', 'connect_time',
        'connection_duration_display', 'quality_display'
    ]
    list_filter = ['status', 'asterisk_server', 'connect_time']
    search_fields = ['agent__username', 'sip_extension', 'session_id']
    ordering = ['-created_at']
    readonly_fields = ['session_id', 'connection_duration_display']
    
    fieldsets = (
        ('Session Information', {
            'fields': ('agent', 'session_id', 'status', 'sip_extension', 'asterisk_server')
        }),
        ('Connection Details', {
            'fields': ('connect_time', 'disconnect_time', 'last_ping'),
            'classes': ('collapse',)
        }),
        ('Quality Metrics', {
            'fields': ('packet_loss', 'jitter', 'latency'),
            'classes': ('collapse',)
        }),
        ('Network Information', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        })
    )
    
    def connection_duration_display(self, obj):
        if obj.is_active():
            duration = obj.connection_duration()
            hours = int(duration // 3600)
            minutes = int((duration % 3600) // 60)
            return f"{hours:02d}:{minutes:02d}"
        return "N/A"
    connection_duration_display.short_description = 'Duration'
    
    def quality_display(self, obj):
        if obj.status == 'connected':
            quality = "Good"
            if obj.packet_loss > 5 or obj.jitter > 50 or obj.latency > 200:
                quality = "Poor"
            elif obj.packet_loss > 2 or obj.jitter > 30 or obj.latency > 150:
                quality = "Fair"
            
            color = 'green' if quality == 'Good' else 'orange' if quality == 'Fair' else 'red'
            return format_html('<span style="color: {};">{}</span>', color, quality)
        return "N/A"
    quality_display.short_description = 'Quality'


@admin.register(AgentCallbackTask)
class AgentCallbackTaskAdmin(admin.ModelAdmin):
    list_display = [
        'agent', 'lead_display', 'scheduled_time', 'priority_display',
        'status', 'is_overdue_display', 'created_by'
    ]
    list_filter = ['status', 'priority', 'scheduled_time', 'campaign']
    search_fields = [
        'agent__username', 'lead__first_name', 'lead__last_name', 
        'lead__phone_number', 'notes'
    ]
    ordering = ['scheduled_time', '-priority']
    
    fieldsets = (
        ('Task Information', {
            'fields': ('agent', 'lead', 'campaign', 'scheduled_time', 'priority')
        }),
        ('Details', {
            'fields': ('notes', 'status')
        }),
        ('Completion', {
            'fields': ('completed_time', 'completion_notes', 'call_log'),
            'classes': ('collapse',)
        })
    )
    
    def lead_display(self, obj):
        return f"{obj.lead.first_name} {obj.lead.last_name}"
    lead_display.short_description = 'Lead'
    
    def priority_display(self, obj):
        colors = {1: 'blue', 2: 'green', 3: 'orange', 4: 'red'}
        color = colors.get(obj.priority, 'black')
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_priority_display()
        )
    priority_display.short_description = 'Priority'
    
    def is_overdue_display(self, obj):
        if obj.is_overdue():
            return format_html('<span style="color: red;">Yes</span>')
        return format_html('<span style="color: green;">No</span>')
    is_overdue_display.short_description = 'Overdue'
    
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ['created_by']
        return []
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# Custom admin site configuration
admin.site.site_header = "AutoDialer Agent Management"
admin.site.site_title = "Agent Admin"
admin.site.index_title = "Agent Interface Administration"