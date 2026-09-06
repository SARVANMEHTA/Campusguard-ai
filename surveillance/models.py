from django.db import models
from django.contrib.auth.models import User
from students.models import SuspendedStudent


class DetectionLog(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('low_confidence', 'Low Confidence Queue (65%-70%)'),
        ('high_confidence', 'High Confidence Queue (>70%)'),
        ('verified', 'Verified Match (Alert Sent)'),
        ('acknowledged', 'Acknowledged / OK'),
        ('rejected', 'Rejected (False Positive)'),
        ('unmatched', 'Unmatched / Discarded (<65%)'),
    ]

    matched_student = models.ForeignKey(
        SuspendedStudent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detections",
        verbose_name="Matched Suspended Student"
    )
    camera_id = models.CharField(
        max_length=50,
        default="CAM-01",
        verbose_name="Camera ID / Stream Source"
    )
    location = models.CharField(
        max_length=150,
        default="Main Gate - Entry Point",
        verbose_name="Gate / Camera Location"
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Detection Timestamp"
    )
    confidence_score = models.FloatField(
        verbose_name="Match Confidence Score (0.0 - 1.0)"
    )
    snapshot_image = models.ImageField(
        upload_to='snapshots/%Y/%m/%d/',
        verbose_name="Surveillance Frame Snapshot / Cropped Face"
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Review Status"
    )
    admin_reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_detections",
        verbose_name="Reviewed By Admin"
    )
    admin_notes = models.TextField(
        null=True,
        blank=True,
        verbose_name="Admin Review Notes"
    )
    alert_sent = models.BooleanField(
        default=False,
        verbose_name="Email Alert Dispatched"
    )
    alert_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Email Alert Sent Timestamp"
    )
    whatsapp_sent = models.BooleanField(
        default=False,
        verbose_name="WhatsApp Alert Dispatched"
    )
    whatsapp_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="WhatsApp Alert Sent Timestamp"
    )

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Detection Log"
        verbose_name_plural = "Detection Logs"

    def __str__(self):
        student_name = self.matched_student.full_name if self.matched_student else "Unknown"
        return f"[{self.get_status_display()}] {student_name} ({self.confidence_score * 100:.1f}%) at {self.location} - {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"

    @property
    def confidence_percentage(self):
        return round(self.confidence_score * 100, 1)

    @property
    def is_actionable(self):
        return self.status in ['low_confidence', 'high_confidence', 'pending']

    @property
    def alert_status_info(self):
        """
        Returns structured info describing actual delivery state:
        'dispatched' | 'failed' | 'in_review' | 'pending'
        """
        if self.alert_sent:
            time_str = self.alert_sent_at.strftime('%I:%M:%S %p, %d %b') if self.alert_sent_at else ''
            return {
                'state': 'dispatched',
                'title': 'Alert Dispatched Automatically',
                'description': f'Delivered to security authority emails at {time_str}' if time_str else 'Delivered to security authority emails',
                'badge_class': 'alert-success',
                'icon': 'fa-circle-check text-success',
                'can_dispatch': False,
            }
        elif self.admin_notes and '[ALERT_FAILED:' in self.admin_notes:
            err = self.admin_notes.split('[ALERT_FAILED:')[-1].rstrip(']').strip()
            return {
                'state': 'failed',
                'title': 'Alert Delivery Failed — Action Required',
                'description': f'Failed sending email: {err}',
                'badge_class': 'alert-danger',
                'icon': 'fa-circle-xmark text-danger',
                'can_dispatch': True,
            }
        elif self.status == 'low_confidence':
            return {
                'state': 'in_review',
                'title': 'Awaiting Manual Verification',
                'description': 'Confidence score is between 65% – 70%. Human sign-off required.',
                'badge_class': 'alert-warning',
                'icon': 'fa-triangle-exclamation text-warning',
                'can_dispatch': True,
            }
        else:
            return {
                'state': 'pending',
                'title': 'Alert Pending / Unsent',
                'description': 'Detection recorded prior to auto-alert activation or queued for dispatch.',
                'badge_class': 'alert-warning',
                'icon': 'fa-clock text-warning',
                'can_dispatch': True,
            }
