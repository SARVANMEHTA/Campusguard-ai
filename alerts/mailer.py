import os
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from .models import AlertRecipient

logger = logging.getLogger(__name__)


def get_active_recipients():
    """Fetches all active recipient emails configured in the system (with send_email=True)."""
    try:
        db_emails = list(AlertRecipient.objects.filter(is_active=True, send_email=True).values_list('email', flat=True))
        if db_emails:
            return db_emails
    except Exception as e:
        logger.warning(f"Could not query AlertRecipient: {e}")
    return getattr(settings, 'ALERT_RECIPIENT_EMAILS', ['security.desk@campus.edu', 'chief.proctor@campus.edu'])


def send_detection_alert(detection_log, admin_user=None, custom_recipients=None, admin_notes=""):
    """
    Dispatches a high-priority security alert email to campus authorities.
    Records success/failure and timestamps directly onto DetectionLog.

    Args:
        detection_log (DetectionLog): The detection record
        admin_user (User): The admin who verified (None if automated dispatch)
        custom_recipients (list): Optional override recipient list
        admin_notes (str): Optional review notes

    Returns:
        bool: True if alert dispatched successfully, False otherwise
    """
    if not detection_log.matched_student:
        err_msg = f"Cannot send alert for DetectionLog #{detection_log.id}: No matched student assigned."
        logger.error(err_msg)
        detection_log.admin_notes = f"{admin_notes} [ALERT_FAILED: No matched student assigned]".strip()
        detection_log.save(update_fields=['admin_notes'])
        return False

    student = detection_log.matched_student
    recipients = custom_recipients or get_active_recipients()

    if not recipients:
        err_msg = f"No recipient emails available for Detection #{detection_log.id}."
        logger.warning(err_msg)
        detection_log.admin_notes = f"{admin_notes} [ALERT_FAILED: No recipient emails configured]".strip()
        detection_log.save(update_fields=['admin_notes'])
        return False

    reviewer_name = admin_user.get_full_name() or admin_user.username if admin_user else "CampusGuard AI (Automated Instant Alert)"

    context = {
        'detection': detection_log,
        'student': student,
        'reviewer_name': reviewer_name,
        'admin_user': admin_user,
        'admin_notes': admin_notes,
        'recipients': recipients,
    }

    subject = f"🚨 URGENT: Suspended Student Detected - {student.full_name} ({student.student_id}) at {detection_log.location}"
    html_content = render_to_string('alerts/email_alert.html', context)
    text_content = strip_tags(html_content)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'CampusGuard AI <alerts@campusguard.edu>')

    try:
        logger.info(f"Attempting SMTP dispatch for Detection #{detection_log.id} to {recipients} (From: {from_email})...")
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=recipients
        )
        email.attach_alternative(html_content, "text/html")

        if detection_log.snapshot_image and os.path.exists(detection_log.snapshot_image.path):
            with open(detection_log.snapshot_image.path, 'rb') as f:
                email.attach(
                    filename=f"detection_snapshot_{detection_log.id}.jpg",
                    content=f.read(),
                    mimetype="image/jpeg"
                )

        if student.photo and os.path.exists(student.photo.path):
            with open(student.photo.path, 'rb') as f:
                email.attach(
                    filename=f"student_reference_{student.student_id}.jpg",
                    content=f.read(),
                    mimetype="image/jpeg"
                )

        email.send(fail_silently=False)

        # Record confirmed success
        detection_log.alert_sent = True
        detection_log.alert_sent_at = timezone.now()
        detection_log.status = 'verified'
        if admin_user:
            detection_log.admin_reviewed_by = admin_user
        if admin_notes:
            detection_log.admin_notes = admin_notes
        detection_log.save()

        logger.info(f"SUCCESS: Security alert email delivered for Detection #{detection_log.id} to {recipients}")

        # Dispatch parallel WhatsApp Alert
        try:
            from .whatsapp import send_whatsapp_alert
            send_whatsapp_alert(detection_log, admin_user=admin_user, admin_notes=admin_notes)
        except Exception as wa_err:
            logger.warning(f"WhatsApp alert dispatch warning for Detection #{detection_log.id}: {wa_err}")

        return True

    except Exception as e:
        logger.error(f"FAILED: SMTP dispatch failed for Detection #{detection_log.id}: {str(e)}", exc_info=True)
        detection_log.alert_sent = False
        detection_log.status = 'verified'
        if admin_user:
            detection_log.admin_reviewed_by = admin_user
        error_note = f"[ALERT_FAILED: {str(e)}]"
        detection_log.admin_notes = f"{admin_notes or ''} {error_note}".strip()
        detection_log.save()

        # Still attempt WhatsApp alert if email failed
        try:
            from .whatsapp import send_whatsapp_alert
            send_whatsapp_alert(detection_log, admin_user=admin_user, admin_notes=admin_notes)
        except Exception as wa_err:
            logger.warning(f"WhatsApp alert dispatch warning for Detection #{detection_log.id}: {wa_err}")

        return False
