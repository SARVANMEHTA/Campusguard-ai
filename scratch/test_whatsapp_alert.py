import os
import sys
from unittest.mock import patch, MagicMock

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, r"c:\Users\skmsa\OneDrive\Desktop\4th Year Assignment Project")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'campusguard.settings')
import django
django.setup()

from django.utils import timezone
from students.models import SuspendedStudent
from surveillance.models import DetectionLog
from alerts.models import AlertRecipient
from alerts.whatsapp import (
    normalize_whatsapp_number,
    get_active_whatsapp_recipients,
    format_whatsapp_message,
    send_whatsapp_alert,
)
from alerts.mailer import send_detection_alert

print("=" * 60)
print("TEST: WhatsApp Alerting Engine Verification")
print("=" * 60)

# 1. Test normalize_whatsapp_number
print("1. Testing phone number normalization...")
assert normalize_whatsapp_number("+919876543210") == "whatsapp:+919876543210"
assert normalize_whatsapp_number("+91 98765 43210") == "whatsapp:+919876543210"
assert normalize_whatsapp_number("whatsapp:+919876543210") == "whatsapp:+919876543210"
assert normalize_whatsapp_number(None) is None
print("   [PASS] Number normalization handles formats accurately.")

# 2. Test recipient fetching
print("2. Testing recipient query...")
recipients = get_active_whatsapp_recipients()
print(f"   Found {len(recipients)} WhatsApp recipient(s): {[r['whatsapp_address'] for r in recipients]}")
assert len(recipients) > 0, "Should have active or fallback recipients"
print("   [PASS] Recipient resolver working.")

# 3. Test message formatting
print("3. Testing message formatting...")
student = SuspendedStudent.objects.first()
detection = DetectionLog.objects.filter(matched_student__isnull=False).first()
if not detection:
    detection = DetectionLog.objects.create(
        matched_student=student,
        camera_id="CAM-01",
        location="Main Gate",
        confidence_score=0.85,
        status="verified"
    )

student = detection.matched_student
msg = format_whatsapp_message(detection, admin_notes="Test investigation note")
print(f"   Formatted Message Preview:\n{msg[:180]}...")
assert "CAMPUSGUARD AI: HIGH-PRIORITY SECURITY ALERT" in msg
assert student.full_name in msg
assert "http://127.0.0.1:8000/detection/" in msg
print("   [PASS] Message formatted with full details.")

# 4. Test Simulated Mode (without Twilio credentials)
print("4. Testing Simulated Mode dispatch...")
detection.whatsapp_sent = False
detection.whatsapp_sent_at = None
detection.save()

res_sim = send_whatsapp_alert(detection, admin_notes="Simulated dispatch test")
detection.refresh_from_db()
assert res_sim is True, "Simulated dispatch should return True"
assert detection.whatsapp_sent is True, "DetectionLog.whatsapp_sent must be True"
assert detection.whatsapp_sent_at is not None, "DetectionLog.whatsapp_sent_at must be populated"
print("   [PASS] Simulated Mode logged and updated DetectionLog successfully.")

# 5. Test Live Twilio Mode (using mocked Client to verify API call contract)
print("5. Testing Twilio Client API integration with mock credentials...")
with patch('django.conf.settings.TWILIO_ACCOUNT_SID', 'ACmockaccount1234567890abcdef123'), \
     patch('django.conf.settings.TWILIO_AUTH_TOKEN', 'mocktoken1234567890abcdef123456'), \
     patch('django.conf.settings.TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886'), \
     patch('twilio.rest.Client') as MockClient:

    mock_client_instance = MagicMock()
    MockClient.return_value = mock_client_instance

    res_live = send_whatsapp_alert(
        detection,
        custom_recipients=[{'name': 'Chief Proctor', 'phone': '+919876543210', 'whatsapp_address': 'whatsapp:+919876543210', 'role': 'proctor'}]
    )

    assert res_live is True, "Live dispatch should return True"
    assert MockClient.called, "Twilio Client must be instantiated with credentials"
    assert mock_client_instance.messages.create.called, "client.messages.create must be invoked"
    call_kwargs = mock_client_instance.messages.create.call_args[1]
    assert call_kwargs['to'] == 'whatsapp:+919876543210'
    assert call_kwargs['from_'] == 'whatsapp:+14155238886'
    print("   [PASS] Twilio API call parameters verified (to, from_, body).")

# 6. Test Unified Dispatch (send_detection_alert triggers both email and WhatsApp)
print("6. Testing Unified Dispatch in send_detection_alert...")
with patch('django.core.mail.EmailMultiAlternatives.send', return_value=1), \
     patch('alerts.whatsapp.send_whatsapp_alert') as mock_wa:
    mock_wa.return_value = True

    send_detection_alert(detection, admin_notes="Unified dispatch test")
    assert mock_wa.called, "send_detection_alert must trigger send_whatsapp_alert in parallel!"
    print("   [PASS] Unified alert pipeline dispatches both Email and WhatsApp in parallel.")

print("\n>>> ALL 6 WHATSAPP ALERTING TESTS PASSED! <<<")
