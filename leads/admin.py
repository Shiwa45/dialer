# leads/admin.py (Fixed to match updated models)

from django.contrib import admin
from django.db.models import Count, Q
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponse
import csv

from .models import (
    Lead, LeadList, DNCEntry, LeadImport, CallbackSchedule,
    LeadNote, LeadRecyclingRule, LeadFilter
)


def export_as_csv(modeladmin, request, queryset):
    """
    Export selected items as CSV
    """
    meta = modeladmin.model._meta
    field_names = [field.name for field in meta.fields]

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename={meta}.csv'
    writer = csv.writer(response)

    writer.writerow(field_names)
    for obj in queryset:
        writer.writerow([getattr(obj, field) for field in field_names])

    return response

export_as_csv.short_description = "Export Selected as CSV"


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = [
        'get_full_name', 'phone_number', 'email', 'company', 
        'status', 'lead_list', 'assigned_user', 'priority',
        'created_at', 'last_contact_date'
    ]
    list_filter = [
        'status', 'priority', 'lead_list', 'assigned_user',
        'created_at', 'last_contact_date', 'state'
    ]
    search_fields = [
        'first_name', 'last_name', 'phone_number', 'email', 
        'company', 'address', 'city'
    ]
    readonly_fields = ['created_at', 'updated_at']  # Removed 'created_by'
    actions = [export_as_csv, 'mark_as_contacted', 'mark_as_dnc', 'reset_to_new']
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name')
        }),
        ('Contact Details', {
            'fields': ('phone_number', 'email', 'company')
        }),
        ('Address Information', {
            'fields': ('address', 'city', 'state', 'zip_code')
        }),
        ('Lead Management', {
            'fields': ('lead_list', 'status', 'priority', 'assigned_user')
        }),
        ('Additional Information', {
            'fields': ('comments', 'source', 'call_count', 'last_contact_date'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = 'Name'
    get_full_name.admin_order_field = 'first_name'
    
    def mark_as_contacted(self, request, queryset):
        count = queryset.update(status='contacted')
        self.message_user(request, f'{count} leads marked as contacted.')
    mark_as_contacted.short_description = "Mark selected leads as contacted"
    
    def mark_as_dnc(self, request, queryset):
        count = queryset.update(status='dnc')
        # Add to DNC list
        for lead in queryset:
            DNCEntry.objects.get_or_create(
                phone_number=lead.phone_number,
                defaults={'reason': 'Admin action', 'added_by': request.user}
            )
        self.message_user(request, f'{count} leads marked as DNC.')
    mark_as_dnc.short_description = "Mark selected leads as DNC"
    
    def reset_to_new(self, request, queryset):
        count = queryset.update(status='new', call_count=0)
        self.message_user(request, f'{count} leads reset to new status.')
    reset_to_new.short_description = "Reset selected leads to new status"


@admin.register(LeadList)
class LeadListAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'get_lead_count', 'get_fresh_leads', 'get_contacted_leads',
        'is_active', 'created_by', 'created_at'
    ]
    list_filter = ['is_active', 'created_at', 'created_by']
    search_fields = ['name', 'description', 'tags']
    readonly_fields = ['created_at', 'updated_at']
    actions = [export_as_csv, 'activate_lists', 'deactivate_lists']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Classification', {
            'fields': ('tags',)
        }),
        ('Management', {
            'fields': ('created_by',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            lead_count=Count('leads'),
            fresh_leads=Count('leads', filter=Q(leads__status='new')),
            contacted_leads=Count('leads', filter=Q(leads__status__in=['contacted', 'callback', 'sale']))
        )
    
    def get_lead_count(self, obj):
        return obj.lead_count
    get_lead_count.short_description = 'Total Leads'
    get_lead_count.admin_order_field = 'lead_count'
    
    def get_fresh_leads(self, obj):
        return obj.fresh_leads
    get_fresh_leads.short_description = 'Fresh Leads'
    get_fresh_leads.admin_order_field = 'fresh_leads'
    
    def get_contacted_leads(self, obj):
        return obj.contacted_leads
    get_contacted_leads.short_description = 'Contacted'
    get_contacted_leads.admin_order_field = 'contacted_leads'
    
    def activate_lists(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} lead lists activated.')
    activate_lists.short_description = "Activate selected lead lists"
    
    def deactivate_lists(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} lead lists deactivated.')
    deactivate_lists.short_description = "Deactivate selected lead lists"


@admin.register(DNCEntry)
class DNCEntryAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'reason', 'added_by', 'created_at']
    list_filter = ['created_at', 'added_by']
    search_fields = ['phone_number', 'reason']
    readonly_fields = ['created_at', 'updated_at']
    actions = [export_as_csv, 'remove_from_dnc']
    
    fieldsets = (
        ('DNC Information', {
            'fields': ('phone_number', 'reason', 'added_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def remove_from_dnc(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f'{count} numbers removed from DNC list.')
    remove_from_dnc.short_description = "Remove selected numbers from DNC"


@admin.register(LeadImport)
class LeadImportAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'user', 'lead_list', 'status', 'get_progress',
        'successful_imports', 'failed_imports', 'created_at'
    ]
    list_filter = ['status', 'created_at', 'user', 'lead_list']
    search_fields = ['name', 'user__username']
    readonly_fields = [
        'created_at', 'updated_at', 'processed_rows', 'total_rows',
        'successful_imports', 'failed_imports', 'duplicate_count'
    ]
    actions = [export_as_csv, 'retry_failed_imports']
    
    fieldsets = (
        ('Import Information', {
            'fields': ('name', 'user', 'lead_list', 'file')
        }),
        ('Status & Progress', {
            'fields': ('status', 'processed_rows', 'total_rows', 'error_message')
        }),
        ('Options', {
            'fields': ('skip_duplicates', 'check_dnc'),
            'classes': ('collapse',)
        }),
        ('Results', {
            'fields': ('successful_imports', 'failed_imports', 'duplicate_count')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_progress(self, obj):
        if obj.total_rows > 0:
            percentage = (obj.processed_rows / obj.total_rows) * 100
            color = 'green' if obj.status == 'completed' else 'blue'
            return format_html(
                '<div style="width: 100px; background-color: #f0f0f0;">'
                '<div style="width: {}%; background-color: {}; height: 20px;"></div>'
                '</div> {}%',
                percentage, color, round(percentage, 1)
            )
        return "0%"
    get_progress.short_description = 'Progress'
    
    def retry_failed_imports(self, request, queryset):
        count = 0
        for import_obj in queryset.filter(status='failed'):
            import_obj.status = 'pending'
            import_obj.error_message = ''
            import_obj.save()
            count += 1
        self.message_user(request, f'{count} imports queued for retry.')
    retry_failed_imports.short_description = "Retry failed imports"


@admin.register(CallbackSchedule)
class CallbackScheduleAdmin(admin.ModelAdmin):
    list_display = [
        'lead', 'agent', 'campaign', 'scheduled_time', 'timezone',
        'is_completed', 'get_status', 'created_at'
    ]
    list_filter = [
        'is_completed', 'scheduled_time', 'timezone', 'agent', 
        'campaign', 'created_at'
    ]
    search_fields = [
        'lead__first_name', 'lead__last_name', 'lead__phone_number',
        'agent__username', 'campaign__name', 'notes'
    ]
    readonly_fields = ['created_at', 'updated_at', 'completed_at']
    actions = [export_as_csv, 'mark_completed']
    date_hierarchy = 'scheduled_time'
    
    fieldsets = (
        ('Callback Information', {
            'fields': ('lead', 'agent', 'campaign', 'scheduled_time', 'timezone')
        }),
        ('Status', {
            'fields': ('is_completed', 'completed_at', 'reminder_sent')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_status(self, obj):
        if obj.is_completed:
            return format_html('<span style="color: green;">✓ Completed</span>')
        elif obj.is_overdue():
            return format_html('<span style="color: red;">⚠ Overdue</span>')
        else:
            return format_html('<span style="color: blue;">⏰ Pending</span>')
    get_status.short_description = 'Status'
    
    def mark_completed(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(is_completed=False).update(
            is_completed=True,
            completed_at=timezone.now()
        )
        self.message_user(request, f'{count} callbacks marked as completed.')
    mark_completed.short_description = "Mark selected callbacks as completed"


@admin.register(LeadNote)
class LeadNoteAdmin(admin.ModelAdmin):
    list_display = ['lead', 'user', 'get_note_preview', 'is_important', 'created_at']
    list_filter = ['is_important', 'created_at', 'user']
    search_fields = ['lead__first_name', 'lead__last_name', 'note', 'user__username']
    readonly_fields = ['created_at', 'updated_at']
    actions = [export_as_csv, 'mark_important', 'mark_not_important']
    
    fieldsets = (
        ('Note Information', {
            'fields': ('lead', 'user', 'note', 'is_important')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_note_preview(self, obj):
        return obj.note[:100] + '...' if len(obj.note) > 100 else obj.note
    get_note_preview.short_description = 'Note Preview'
    
    def mark_important(self, request, queryset):
        count = queryset.update(is_important=True)
        self.message_user(request, f'{count} notes marked as important.')
    mark_important.short_description = "Mark selected notes as important"
    
    def mark_not_important(self, request, queryset):
        count = queryset.update(is_important=False)
        self.message_user(request, f'{count} notes marked as not important.')
    mark_not_important.short_description = "Mark selected notes as not important"


@admin.register(LeadRecyclingRule)
class LeadRecyclingRuleAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'source_status', 'target_status', 'days_since_contact',
        'max_attempts', 'is_active', 'created_at'
    ]
    list_filter = ['is_active', 'source_status', 'target_status', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    actions = [export_as_csv, 'activate_rules', 'deactivate_rules']
    
    fieldsets = (
        ('Rule Information', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Recycling Criteria', {
            'fields': ('source_status', 'target_status', 'days_since_contact', 'max_attempts')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def activate_rules(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} recycling rules activated.')
    activate_rules.short_description = "Activate selected rules"
    
    def deactivate_rules(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} recycling rules deactivated.')
    deactivate_rules.short_description = "Deactivate selected rules"


@admin.register(LeadFilter)
class LeadFilterAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'is_active', 'created_by', 'created_at']
    list_filter = ['is_active', 'created_at', 'created_by']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    actions = [export_as_csv]
    
    fieldsets = (
        ('Filter Information', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Filter Criteria', {
            'fields': ('filter_criteria',)
        }),
        ('Management', {
            'fields': ('created_by',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


# Customize admin site header
admin.site.site_header = "Autodialer Administration"
admin.site.site_title = "Autodialer Admin"
admin.site.index_title = "Lead Management System"