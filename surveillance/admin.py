from django.contrib import admin
from django.utils.html import format_html
from .models import DetectionLog


@admin.register(DetectionLog)
class DetectionLogAdmin(admin.ModelAdmin):
    list_display = (
        'snapshot_thumbnail',
        'matched_student',
        'confidence_badge',
        'status_badge',
        'camera_id',
        'location',
        'alert_sent_status',
        'admin_reviewed_by',
        'timestamp'
    )
    list_filter = ('status', 'alert_sent', 'camera_id', 'timestamp')
    search_fields = ('matched_student__full_name', 'matched_student__student_id', 'camera_id', 'location', 'admin_notes')
    readonly_fields = ('timestamp', 'snapshot_preview', 'alert_sent_at')

    def snapshot_thumbnail(self, obj):
        if obj.snapshot_image:
            return format_html(
                '<img src="{}" width="60" height="60" style="border-radius:6px; object-fit:cover; border:1px solid #ced4da;" />',
                obj.snapshot_image.url
            )
        return "No Snapshot"
    snapshot_thumbnail.short_description = "Capture"

    def snapshot_preview(self, obj):
        if obj.snapshot_image:
            return format_html(
                '<img src="{}" style="max-width:320px; max-height:240px; border-radius:8px; border:2px solid #343a40;" />',
                obj.snapshot_image.url
            )
        return "No Snapshot"
    snapshot_preview.short_description = "Capture Preview"

    def confidence_badge(self, obj):
        pct = obj.confidence_score * 100
        if pct >= 70:
            color = "#dc3545" # Red
        elif pct >= 65:
            color = "#ffc107; color:#212529;" # Yellow
        else:
            color = "#6c757d" # Grey
        return format_html(
            f'<span style="background-color:{color}; color:white; padding:4px 8px; border-radius:12px; font-weight:bold; font-size:12px;">{pct:.1f}%</span>'
        )
    confidence_badge.short_description = "Confidence"

    def status_badge(self, obj):
        badge_colors = {
            'high_confidence': 'background-color:#dc3545; color:#fff;',
            'low_confidence': 'background-color:#fd7e14; color:#fff;',
            'verified': 'background-color:#198754; color:#fff;',
            'rejected': 'background-color:#6c757d; color:#fff;',
            'pending': 'background-color:#0dcaf0; color:#000;',
            'unmatched': 'background-color:#adb5bd; color:#000;',
        }
        style = badge_colors.get(obj.status, 'background-color:#6c757d; color:#fff;')
        return format_html(f'<span style="{style} padding:4px 8px; border-radius:10px; font-weight:600; font-size:11px;">{obj.get_status_display()}</span>')
    status_badge.short_description = "Status"

    def alert_sent_status(self, obj):
        if obj.alert_sent:
            return format_html('<span style="color:#198754; font-weight:bold;">✔ Sent ({})</span>', obj.alert_sent_at.strftime('%H:%M:%S') if obj.alert_sent_at else 'Yes')
        return format_html('<span style="color:#6c757d;">Not Sent</span>')
    alert_sent_status.short_description = "Alert Sent"
