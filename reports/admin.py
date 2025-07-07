# reports/admin.py
from django.contrib import admin
from .models import Dashboard
# Add other report models when ready

@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'is_public', 'is_active', 'created_at']
    list_filter = ['is_public', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['dashboard_id', 'created_at', 'updated_at']