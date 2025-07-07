# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, UserSession, AgentStatus

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'

class CustomUserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_role', 'get_department')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    
    def get_role(self, instance):
        if hasattr(instance, 'profile') and instance.profile:
            return instance.profile.get_role()
        return "No Role"
    get_role.short_description = 'Role'
    
    def get_department(self, instance):
        if hasattr(instance, 'profile') and instance.profile:
            return instance.profile.department
        return ""
    get_department.short_description = 'Department'

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'department', 'is_active']
    list_filter = ['role', 'department', 'is_active']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']

@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'ip_address', 'login_time', 'logout_time', 'is_active']
    list_filter = ['is_active', 'login_time']
    search_fields = ['user__username', 'ip_address']
    readonly_fields = ['session_key', 'login_time', 'logout_time']
    date_hierarchy = 'login_time'

@admin.register(AgentStatus)
class AgentStatusAdmin(admin.ModelAdmin):
    list_display = ['user', 'status', 'status_changed_at', 'current_campaign']
    list_filter = ['status', 'status_changed_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']
    readonly_fields = ['status_changed_at']

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

# =============================================================================

