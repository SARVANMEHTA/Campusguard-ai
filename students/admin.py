from django.contrib import admin
from django.utils.html import format_html
from .models import SuspendedStudent, FaceEmbedding


class FaceEmbeddingInline(admin.TabularInline):
    model = FaceEmbedding
    extra = 0
    readonly_fields = ('created_at', 'preview_embedding')

    def preview_embedding(self, obj):
        if obj.embedding_vector:
            dim = len(obj.embedding_vector)
            return f"{dim}-dimensional vector ({obj.model_version})"
        return "None"
    preview_embedding.short_description = "Vector Info"


@admin.register(SuspendedStudent)
class SuspendedStudentAdmin(admin.ModelAdmin):
    list_display = (
        'photo_thumbnail',
        'student_id',
        'full_name',
        'department',
        'year',
        'suspension_start_date',
        'suspension_end_date',
        'status_badge',
        'embedding_count',
        'created_at'
    )
    list_filter = ('status', 'department', 'year', 'suspension_start_date', 'suspension_end_date')
    search_fields = ('student_id', 'full_name', 'department', 'suspension_reason')
    readonly_fields = ('created_at', 'photo_preview')
    inlines = [FaceEmbeddingInline]

    def photo_thumbnail(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" width="48" height="48" style="border-radius:50%; object-fit:cover; border:2px solid #dee2e6;" />',
                obj.photo.url
            )
        return "No Photo"
    photo_thumbnail.short_description = "Photo"

    def photo_preview(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" width="160" height="160" style="border-radius:8px; object-fit:cover; border:1px solid #ced4da;" />',
                obj.photo.url
            )
        return "No Photo"
    photo_preview.short_description = "Current Photo"

    def status_badge(self, obj):
        if obj.status == 'active':
            return format_html('<span style="background-color:#dc3545; color:white; padding:4px 8px; border-radius:12px; font-weight:600; font-size:11px;">ACTIVE SUSPENSION</span>')
        return format_html('<span style="background-color:#6c757d; color:white; padding:4px 8px; border-radius:12px; font-weight:600; font-size:11px;">EXPIRED</span>')
    status_badge.short_description = "Status"

    def embedding_count(self, obj):
        count = obj.embeddings.count()
        return format_html('<b>{}</b> vector(s)', count)
    embedding_count.short_description = "Embeddings"


@admin.register(FaceEmbedding)
class FaceEmbeddingAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'model_version', 'created_at')
    list_filter = ('model_version', 'created_at')
    search_fields = ('student__full_name', 'student__student_id')
