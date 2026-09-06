from django.db import models


class AlertRecipient(models.Model):
    ROLE_CHOICES = [
        ('security', 'Campus Security Office'),
        ('hod', 'Department Head (HOD)'),
        ('proctor', 'Chief Proctor / Disciplinary Committee'),
        ('warden', 'Hostel Chief Warden'),
        ('dean', 'Dean of Student Affairs'),
        ('other', 'Other Authority'),
    ]

    name = models.CharField(
        max_length=150,
        verbose_name="Contact / Authority Name",
        help_text="e.g. Chief Security Officer, Dr. Rajesh Sharma (HOD CSE)"
    )
    email = models.EmailField(
        unique=True,
        verbose_name="Email Address",
        help_text="Official email to receive automated security alerts."
    )
    phone_number = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        verbose_name="WhatsApp / Phone Number",
        help_text="Include country code (e.g. +919876543210 or +14155552671)"
    )
    send_email = models.BooleanField(
        default=True,
        verbose_name="Receive Email Alerts"
    )
    send_whatsapp = models.BooleanField(
        default=True,
        verbose_name="Receive WhatsApp Alerts"
    )
    role = models.CharField(
        max_length=50,
        choices=ROLE_CHOICES,
        default='security',
        verbose_name="Authority Role"
    )
    department = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Associated Department / Gate (Optional)"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active (Receive Alerts)",
        help_text="Uncheck to temporarily pause notifications without deleting the contact."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Added On"
    )

    class Meta:
        ordering = ['role', 'name']
        verbose_name = "Alert Recipient Contact"
        verbose_name_plural = "Alert Recipient Contacts"

    def __str__(self):
        return f"{self.name} <{self.email}> ({self.get_role_display()})"
