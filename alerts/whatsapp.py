import os
import re
import logging
from django.conf import settings
from django.utils import timezone
from .models import AlertRecipient

logger = logging.getLogger(__name__)


def normalize_whatsapp_number(phone_raw):
    """
    Cleans and formats a phone number for WhatsApp.
    Ensures E.164 international format prefixed with 'whatsapp:'.
    Example: '+91 98765 43210' -> 'whatsapp:+919876543210'
    """
    if not phone_raw:
        return None
    cleaned = re.sub(r'[^\d+]', '', str(phone_raw).strip())
    if not cleaned:
        return None
    if not cleaned.startswith('+'):
        cleaned = '+' + cleaned
    if not cleaned.startswith('whatsapp:'):
        return f"whatsapp:{cleaned}"
    return cleaned


def get_active_whatsapp_recipients():
    """
    Retrieves all active recipients configured to receive WhatsApp notifications.
    Returns list of dicts with recipient name, raw phone, and formatted whatsapp address.
    """
    recipients = []
    try:
        active_objs = AlertRecipient.objects.filter(
            is_active=True,
            send_whatsapp=True
        ).exclude(phone_number__isnull=True).exclude(phone_number__exact='')
        
        for r in active_objs:
            wa_num = normalize_whatsapp_number(r.phone_number)
            if wa_num:
                recipients.append({
                    'name': r.name,
                    'phone': r.phone_number,
                    'whatsapp_address': wa_num,
                    'role': r.role
                })
        if recipients:
            return recipients
    except Exception as e:
        logger.warning(f"Could not query AlertRecipient for WhatsApp: {e}")

    # Fallback to configured settings numbers
    fallback_phones = getattr(settings, 'ALERT_RECIPIENT_PHONES', ['+919876543210'])
    for p in fallback_phones:
        wa_num = normalize_whatsapp_number(p)
        if wa_num:
            recipients.append({
                'name': 'Campus Security Desk',
                'phone': p,
                'whatsapp_address': wa_num,
                'role': 'security'
            })
    return recipients


def format_whatsapp_message(detection_log, admin_user=None, admin_notes=""):
    """
    Generates a concise, high-visibility formatted WhatsApp alert message.
    """
    student = detection_log.matched_student
    time_str = detection_log.timestamp.astimezone().strftime("%d %b %Y, %I:%M:%S %p")
    
    sender_title = admin_user.get_full_name() or admin_user.username if admin_user else "Automated Live Surveillance Match"

    message = (
        f"🚨 *CAMPUSGUARD AI: HIGH-PRIORITY SECURITY ALERT* 🚨\n\n"
        f"A suspended student has been detected on campus premises.\n\n"
        f"👤 *Name:* {student.full_name}\n"
        f"🆔 *Roll No:* {student.student_id}\n"
        f"🏢 *Department:* {student.department} ({student.year})\n"
        f"📍 *Location:* {detection_log.location} ({detection_log.camera_id})\n"
        f"🎯 *Match Confidence:* {detection_log.confidence_percentage}% (High Confidence)\n"
        f"⚠️ *Suspension Reason:* {student.suspension_reason or 'Disciplinary Action'}\n"
        f"🕒 *Detected At:* {time_str}\n"
        f"🛡️ *Dispatched By:* {sender_title}\n"
    )

    if admin_notes:
        message += f"\n📝 *Notes:* {admin_notes}\n"

    message += (
        f"\n🔗 *Incident Case File:*\n"
        f"http://127.0.0.1:8000/detection/{detection_log.id}/\n\n"
        f"⚠️ *Immediate action required by on-duty campus security officers.*"
    )
    return message


def send_twilio_message(account_sid, auth_token, from_wa, to_wa, body, content_sid=None):
    """
    Sends a WhatsApp message via Twilio SDK if available, or direct Twilio REST HTTPS API via requests.
    Guarantees no 'No module named twilio' import errors.
    """
    # 1. Try twilio Python SDK if installed
    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        try:
            msg = client.messages.create(body=body, from_=from_wa, to=to_wa)
            return True, getattr(msg, 'sid', 'ok')
        except Exception as body_err:
            if ("ContentSid Required" in str(body_err) or "63016" in str(body_err)) and content_sid:
                msg = client.messages.create(from_=from_wa, to=to_wa, content_sid=content_sid)
                return True, getattr(msg, 'sid', 'ok')
            raise body_err
    except ImportError:
        pass

    # 2. Direct HTTP REST API via requests (zero external SDK dependency)
    import requests
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = {
        "From": from_wa,
        "To": to_wa,
        "Body": body,
    }
    resp = requests.post(url, data=data, auth=(account_sid, auth_token), timeout=15)
    if resp.status_code in (200, 201):
        try:
            return True, resp.json().get('sid', 'ok')
        except Exception:
            return True, 'ok'

    err_text = resp.text
    if ("ContentSid" in err_text or "template" in err_text.lower() or "63016" in err_text) and content_sid:
        retry_data = {
            "From": from_wa,
            "To": to_wa,
            "ContentSid": content_sid,
        }
        resp2 = requests.post(url, data=retry_data, auth=(account_sid, auth_token), timeout=15)
        if resp2.status_code in (200, 201):
            return True, 'ok'
        err_text = resp2.text

    return False, err_text


def send_whatsapp_alert(detection_log, admin_user=None, custom_recipients=None, admin_notes=""):
    """
    Dispatches WhatsApp security alerts to campus authorities.
    
    If Twilio credentials (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) are provided,
    sends live WhatsApp messages using the official Twilio API (or HTTP REST API).
    
    If credentials are empty, operates in Simulated Development Mode.

    Returns:
        bool: True if alert was dispatched (or simulated successfully), False on error.
    """
    if not detection_log.matched_student:
        logger.error(f"Cannot dispatch WhatsApp alert for DetectionLog #{detection_log.id}: No matched student assigned.")
        return False

    recipients = custom_recipients or get_active_whatsapp_recipients()
    if not recipients:
        logger.warning(f"No WhatsApp recipient phone numbers available for Detection #{detection_log.id}.")
        return False

    message_body = format_whatsapp_message(detection_log, admin_user=admin_user, admin_notes=admin_notes)

    account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '').strip()
    auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '').strip()
    from_whatsapp = getattr(settings, 'TWILIO_WHATSAPP_FROM', 'whatsapp:+17372212163').strip()
    content_sid = getattr(settings, 'TWILIO_WHATSAPP_CONTENT_SID', 'HXfe5ab5f00277942d4d4200328b4d403c').strip()

    is_live_twilio = bool(account_sid and auth_token)

    if is_live_twilio:
        sent_count = 0
        last_err = None

        for recipient in recipients:
            to_addr = recipient['whatsapp_address'] if isinstance(recipient, dict) else normalize_whatsapp_number(recipient)
            if not to_addr:
                continue

            logger.info(f"Dispatching live Twilio WhatsApp alert for Detection #{detection_log.id} to {to_addr}...")
            ok, err = send_twilio_message(account_sid, auth_token, from_whatsapp, to_addr, message_body, content_sid)
            if ok:
                sent_count += 1
            else:
                last_err = err
                logger.warning(f"Twilio WhatsApp dispatch failed for {to_addr}: {err}")

        if sent_count > 0:
            detection_log.whatsapp_sent = True
            detection_log.whatsapp_sent_at = timezone.now()
            detection_log.save(update_fields=['whatsapp_sent', 'whatsapp_sent_at'])
            logger.info(f"SUCCESS: Twilio WhatsApp alert delivered to {sent_count} recipient(s) for Detection #{detection_log.id}.")
            return True
        else:
            logger.error(f"FAILED: Twilio WhatsApp dispatch failed for Detection #{detection_log.id}: {last_err}")
            detection_log.whatsapp_sent = False
            detection_log.save(update_fields=['whatsapp_sent'])
            return False


    else:
        # Simulated Development Mode (No credentials required)
        logger.info("=" * 70)
        logger.info(f"[WHATSAPP ALERT SIMULATION] Twilio credentials not configured.")
        logger.info(f"Target Recipients: {[r['whatsapp_address'] if isinstance(r, dict) else r for r in recipients]}")
        logger.info(f"Message Content:\n{message_body}")
        logger.info("=" * 70)

        # Mark as dispatched in development simulation
        detection_log.whatsapp_sent = True
        detection_log.whatsapp_sent_at = timezone.now()
        detection_log.save(update_fields=['whatsapp_sent', 'whatsapp_sent_at'])
        return True
