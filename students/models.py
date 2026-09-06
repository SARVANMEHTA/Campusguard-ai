import datetime
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class SuspendedStudent(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active Suspension'),
        ('expired', 'Suspension Expired'),
    ]

    student_id = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Roll Number / Student ID",
        help_text="Unique student registration/roll number."
    )
    full_name = models.CharField(
        max_length=150,
        verbose_name="Full Name"
    )
    photo = models.ImageField(
        upload_to='students/profiles/',
        verbose_name="Reference Photo"
    )
    department = models.CharField(
        max_length=100,
        verbose_name="Department"
    )
    year = models.CharField(
        max_length=20,
        verbose_name="Year / Semester"
    )
    suspension_reason = models.TextField(
        verbose_name="Reason for Suspension"
    )
    suspension_start_date = models.DateField(
        verbose_name="Suspension Start Date"
    )
    suspension_end_date = models.DateField(
        verbose_name="Suspension End Date"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name="Suspension Status"
    )
    added_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="added_students",
        verbose_name="Added By Admin"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Suspended Student"
        verbose_name_plural = "Suspended Students"

    def __str__(self):
        return f"{self.full_name} ({self.student_id}) - {self.department}"

    @property
    def is_currently_suspended(self):
        today = timezone.now().date()
        if self.status == 'active' and self.suspension_start_date <= today <= self.suspension_end_date:
            return True
        return False

    def check_and_update_status(self):
        """Auto-update status if suspension date has elapsed."""
        today = timezone.now().date()
        if self.suspension_end_date < today and self.status == 'active':
            self.status = 'expired'
            self.save(update_fields=['status'])


class FaceEmbedding(models.Model):
    student = models.ForeignKey(
        SuspendedStudent,
        on_delete=models.CASCADE,
        related_name="embeddings",
        verbose_name="Suspended Student"
    )
    embedding_vector = models.JSONField(
        verbose_name="Serialized Embedding Vector (128-d or 512-d list)"
    )
    model_version = models.CharField(
        max_length=50,
        default="sface-128",
        verbose_name="Model Architecture / Version"
    )
    source_image = models.ImageField(
        upload_to='students/embeddings/',
        null=True,
        blank=True,
        verbose_name="Source Cropped Face Image"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Face Embedding"
        verbose_name_plural = "Face Embeddings"

    def __str__(self):
        return f"Embedding for {self.student.full_name} ({self.model_version}) - ID {self.id}"
