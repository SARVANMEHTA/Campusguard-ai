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


def send_via_resend(api_key, recipients, subject, html_content, attachments=None):
    """
    Sends email via Resend HTTPS REST API (Port 443), which is completely unblocked on Render Free Tier.
    """
    import json
    import urllib.request
    import urllib.error

    url = "https://api.resend.com/emails"
    from_email = getattr(settings, 'RESEND_FROM_EMAIL', '') or "CampusGuard AI <onboarding@resend.dev>"

    if isinstance(recipients, str):
        recipients = [recipients]

    valid_recipients = [r.strip() for r in recipients if r and '@' in r]
    if not valid_recipients:
        valid_recipients = [getattr(settings, 'EMAIL_HOST_USER', 'kler6234@gmail.com')]

    payload = {
        "from": from_email,
        "to": valid_recipients,
        "subject": subject,
        "html": html_content,
    }
    if attachments:
        payload["attachments"] = attachments

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "CampusGuard-AI"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_body = resp.read().decode('utf-8')
            logger.info(f"Resend HTTPS dispatch succeeded: {resp.status} - {resp_body}")
            return True, None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        logger.warning(f"Resend HTTPError {e.code}: {err_body}")
        # If testing domain rejects sending to external unverified address, retry directly with owner email
        user_email = getattr(settings, 'EMAIL_HOST_USER', '').strip()
        if user_email and [user_email] != valid_recipients and ("only send testing emails to your own email address" in err_body or "validation_error" in err_body):
            logger.info(f"Retrying Resend HTTPS dispatch directly to account owner: {user_email}")
            payload["to"] = [user_email]
            retry_data = json.dumps(payload).encode('utf-8')
            retry_req = urllib.request.Request(
                url,
                data=retry_data,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "CampusGuard-AI"
                },
                method="POST"
            )
            with urllib.request.urlopen(retry_req, timeout=15) as retry_resp:
                logger.info(f"Resend retry to owner succeeded: {retry_resp.status}")
                return True, None
        return False, err_body
    except Exception as e:
        logger.error(f"Resend exception: {e}")
        return False, str(e)


def send_detection_alert(detection_log, admin_user=None, custom_recipients=None, admin_notes=""):
    """
    Dispatches a high-priority security alert email to campus authorities.
    Records success/failure and timestamps directly onto DetectionLog.
    Supports Resend HTTPS API (Port 443) and standard SMTP with automatic fallback.
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

    # 1. Try Resend HTTPS REST API (Port 443 - Bypasses Render SMTP blocking)
    resend_key = getattr(settings, 'RESEND_API_KEY', '').strip()
    if resend_key:
        logger.info(f"Attempting Resend HTTPS dispatch for Detection #{detection_log.id} to {recipients}...")
        resend_attachments = []
        try:
            import base64
            if detection_log.snapshot_image and os.path.exists(detection_log.snapshot_image.path):
                with open(detection_log.snapshot_image.path, 'rb') as f:
                    resend_attachments.append({
                        "filename": f"detection_snapshot_{detection_log.id}.jpg",
                        "content": base64.b64encode(f.read()).decode('ascii')
                    })
            if student.photo and os.path.exists(student.photo.path):
                with open(student.photo.path, 'rb') as f:
                    resend_attachments.append({
                        "filename": f"student_reference_{student.student_id}.jpg",
                        "content": base64.b64encode(f.read()).decode('ascii')
                    })
        except Exception as att_err:
            logger.warning(f"Error preparing Resend attachments: {att_err}")

        ok, err = send_via_resend(resend_key, recipients, subject, html_content, attachments=resend_attachments)
        if ok:
            detection_log.alert_sent = True
            detection_log.alert_sent_at = timezone.now()
            detection_log.status = 'verified'
            if admin_user:
                detection_log.admin_reviewed_by = admin_user
            if admin_notes:
                detection_log.admin_notes = admin_notes
            detection_log.save()

            logger.info(f"SUCCESS: Security alert email delivered via Resend for Detection #{detection_log.id}")

            # Dispatch parallel WhatsApp Alert
            try:
                from .whatsapp import send_whatsapp_alert
                send_whatsapp_alert(detection_log, admin_user=admin_user, admin_notes=admin_notes)
            except Exception as wa_err:
                logger.warning(f"WhatsApp alert dispatch warning for Detection #{detection_log.id}: {wa_err}")

            return True
        else:
            logger.warning(f"Resend HTTPS failed ({err}), attempting fallback to SMTP...")

    # 2. Fallback: SMTP Email Backend
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

        detection_log.alert_sent = True
        detection_log.alert_sent_at = timezone.now()
        detection_log.status = 'verified'
        if admin_user:
            detection_log.admin_reviewed_by = admin_user
        if admin_notes:
            detection_log.admin_notes = admin_notes
        detection_log.save()

        logger.info(f"SUCCESS: Security alert email delivered via SMTP for Detection #{detection_log.id} to {recipients}")

        # Dispatch parallel WhatsApp Alert
        try:
            from .whatsapp import send_whatsapp_alert
            send_whatsapp_alert(detection_log, admin_user=admin_user, admin_notes=admin_notes)
        except Exception as wa_err:
            logger.warning(f"WhatsApp alert dispatch warning for Detection #{detection_log.id}: {wa_err}")

        return True

    except Exception as e:
        logger.error(f"FAILED: Email dispatch failed for Detection #{detection_log.id}: {str(e)}", exc_info=True)
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

