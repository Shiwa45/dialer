from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, UserSession, AgentStatus


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "employee_id", "phone_number", "department", "is_active_agent")
    search_fields = ("user__username", "user__email", "employee_id", "agent_id")
    list_filter = ("is_active_agent", "can_make_outbound", "can_receive_inbound", "department")
    autocomplete_fields = ("user",)


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "session_key", "ip_address", "login_time", "logout_time", "is_active")
    search_fields = ("user__username", "session_key", "ip_address")
    list_filter = ("is_active", "login_time")
    autocomplete_fields = ("user",)


@admin.register(AgentStatus)
class AgentStatusAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "status_changed_at", "current_campaign")
    list_filter = ("status",)
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user", "current_campaign")


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Profile"
    fk_name = "user"


class CustomUserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "get_role",
        "get_department",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")

    def get_role(self, instance):
        profile = getattr(instance, "profile", None)
        return profile.get_role() if profile else "No Role"

    get_role.short_description = "Role"

    def get_department(self, instance):
        profile = getattr(instance, "profile", None)
        return profile.department if profile else ""

    get_department.short_description = "Department"


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
