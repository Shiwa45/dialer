from django.contrib import admin
from .models import (
    AsteriskServer,
    Carrier,
    DID,
    Phone,
    DialplanContext,
    DialplanExtension,
    PsEndpoint,
    PsAuth,
    PsAor,
    PsRegistration,
    ExtensionsTable,
)


@admin.register(AsteriskServer)
class AsteriskServerAdmin(admin.ModelAdmin):
    list_display = ("name", "server_ip", "server_type", "connection_status", "max_calls", "is_active")
    list_filter = ("server_type", "connection_status", "is_active")
    search_fields = ("name", "server_ip", "server_id")
    readonly_fields = ("last_connected",)


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    list_display = ("name", "protocol", "server_ip", "registration_type", "priority", "is_active")
    list_filter = ("protocol", "registration_type", "is_active")
    search_fields = ("name", "server_ip", "username", "auth_username")
    autocomplete_fields = ("asterisk_server",)


@admin.register(DID)
class DIDAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "name", "did_type", "is_active", "asterisk_server", "carrier")
    list_filter = ("did_type", "is_active", "asterisk_server")
    search_fields = ("phone_number", "name")
    autocomplete_fields = ("asterisk_server", "carrier", "assigned_campaign")


@admin.register(Phone)
class PhoneAdmin(admin.ModelAdmin):
    list_display = ("extension", "name", "context", "asterisk_server", "user", "is_active")
    list_filter = ("context", "is_active", "asterisk_server")
    search_fields = ("extension", "name", "user__username")
    autocomplete_fields = ("asterisk_server", "user")


@admin.register(DialplanContext)
class DialplanContextAdmin(admin.ModelAdmin):
    list_display = ("name", "asterisk_server", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active", "asterisk_server")
    autocomplete_fields = ("asterisk_server",)


@admin.register(DialplanExtension)
class DialplanExtensionAdmin(admin.ModelAdmin):
    list_display = ("context", "extension", "priority", "application", "is_active")
    list_filter = ("context", "is_active")
    search_fields = ("extension", "application", "arguments")
    autocomplete_fields = ("context",)


@admin.register(PsEndpoint)
class PsEndpointAdmin(admin.ModelAdmin):
    list_display = ("id", "context", "aors", "auth")
    search_fields = ("id", "context", "aors", "auth")


@admin.register(PsAuth)
class PsAuthAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "auth_type")
    search_fields = ("id", "username")


@admin.register(PsAor)
class PsAorAdmin(admin.ModelAdmin):
    list_display = ("id", "max_contacts", "qualify_frequency", "contact")
    search_fields = ("id", "contact")


@admin.register(PsRegistration)
class PsRegistrationAdmin(admin.ModelAdmin):
    list_display = ("id", "server_uri", "client_uri", "transport")
    search_fields = ("id", "server_uri", "client_uri")


@admin.register(ExtensionsTable)
class ExtensionsTableAdmin(admin.ModelAdmin):
    list_display = ("context", "exten", "priority", "app")
    list_filter = ("context",)
    search_fields = ("context", "exten", "app", "appdata")
