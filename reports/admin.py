# reports/admin.py
from django.contrib import admin
from .models import Dashboard, Report, ReportSchedule, ReportExecution

@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'is_public', 'is_active', 'created_at']
    list_filter = ['is_public', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['dashboard_id', 'created_at', 'updated_at']


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['name', 'report_type', 'created_by', 'is_public', 'is_active', 'created_at']
    list_filter = ['report_type', 'is_public', 'is_active']
    search_fields = ['name', 'description']
    readonly_fields = ['report_id', 'created_at', 'updated_at']


@admin.register(ReportSchedule)
class ReportScheduleAdmin(admin.ModelAdmin):
    list_display = ['name', 'report', 'frequency', 'next_run', 'status', 'created_by']
    list_filter = ['frequency', 'status']
    search_fields = ['name', 'email_subject']


@admin.register(ReportExecution)
class ReportExecutionAdmin(admin.ModelAdmin):
    list_display = ['report', 'started_at', 'completed_at', 'status', 'total_records']
    list_filter = ['status', 'started_at']
    search_fields = ['error_message', 'file_path']
