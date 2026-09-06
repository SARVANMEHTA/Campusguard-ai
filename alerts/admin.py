from django.contrib import admin
from .models import AlertRecipient


@admin.register(AlertRecipient)
class AlertRecipientAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'role', 'department', 'is_active', 'created_at')
    list_filter = ('role', 'is_active', 'department')
    search_fields = ('name', 'email', 'department')
    list_editable = ('is_active',)
