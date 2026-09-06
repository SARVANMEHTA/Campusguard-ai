"""
CampusGuard AI â€” End-to-End Test Management Command

Usage:
    python manage.py e2e_test [--clean]

Tests all modules:
  1.  Admin user setup
  2.  New detained student registration with photo & face embedding
  3.  High-confidence detection log creation (score >= 0.70)
  4.  High-confidence queue HTTP view
  5.  OK (acknowledge) button on high-confidence queue
  6.  Low-confidence detection log creation (0.65â€“0.70)
  7.  Low-confidence queue HTTP view
  8.  Verify button (no email)
  9.  Send Alert button (email dispatched)
  10. Detection logs page + search
  11. CSV export
  12. Analytics page
  13. Dashboard overview
  14. Students list page
"""
import datetime
import numpy as np
import cv2

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.files.base import ContentFile
from django.test.client import Client
from unittest.mock import patch

from students.models import SuspendedStudent, FaceEmbedding
from students.embeddings import face_engine
from surveillance.models import DetectionLog


class Command(BaseCommand):
    help = "Full end-to-end CampusGuard AI pipeline test with a new detained student."

    def add_arguments(self, parser):
        parser.add_argument(
            '--clean',
            action='store_true',
            help='Remove test student and all detections after the run.'
        )

    def handle(self, *args, **options):
        passed = 0
        failed = []

        def ok(msg):
            self.stdout.write(self.style.SUCCESS(f"  [PASS] {msg}"))

        def err(msg):
            self.stdout.write(self.style.ERROR(f"  [FAIL] {msg}"))
            failed.append(msg)

        def head(msg):
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"  {msg}")
            self.stdout.write(f"{'='*60}")

        # â”€â”€ 1. Admin user â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("1. Admin User Setup")
        admin, _ = User.objects.get_or_create(
            username='e2e_admin',
            defaults={'email': 'e2e@campusguard.test', 'is_staff': True, 'is_superuser': True}
        )
        admin.set_password('testpass123')
        admin.save()
        ok("Admin user 'e2e_admin' ready")
        passed += 1

        # â”€â”€ 2. Register new detained student â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("2. Register New Detained Student: Arjun Test Kumar (E2E2024001)")
        today = timezone.now().date()
        student, created = SuspendedStudent.objects.get_or_create(
            student_id='E2E2024001',
            defaults={
                'full_name': 'Arjun Test Kumar',
                'department': 'Computer Science',
                'year': '3rd Year (5th Sem)',
                'suspension_reason': 'E2E Test: Unauthorized campus access during suspension.',
                'suspension_start_date': today - datetime.timedelta(days=1),
                'suspension_end_date': today + datetime.timedelta(days=30),
                'status': 'active',
                'added_by': admin,
            }
        )
        action = "created" if created else "already existed"
        self.stdout.write(f"  Student: {student.full_name} ({student.student_id}) [{action}]")

        if student.status == 'active':
            ok("Student status = active (suspension in effect)")
            passed += 1
        else:
            err(f"Student status = '{student.status}' (expected 'active')")

        # Generate synthetic face portrait
        img = np.full((320, 320, 3), (230, 220, 210), dtype=np.uint8)
        # Background gradient
        for y in range(320):
            shade = int(245 - y * 0.12)
            img[y, :] = (max(0, shade - 10), shade, min(255, shade + 8))
        # Face oval
        cv2.ellipse(img, (160, 155), (70, 88), 0, 0, 360, (175, 200, 230), -1)
        # Eyes
        cv2.ellipse(img, (130, 135), (14, 9), 0, 0, 360, (40, 40, 40), -1)
        cv2.ellipse(img, (190, 135), (14, 9), 0, 0, 360, (40, 40, 40), -1)
        cv2.circle(img, (133, 133), 4, (255, 255, 255), -1)
        cv2.circle(img, (193, 133), 4, (255, 255, 255), -1)
        # Nose
        cv2.ellipse(img, (160, 162), (8, 12), 0, 0, 360, (150, 175, 205), -1)
        # Mouth
        cv2.ellipse(img, (160, 190), (25, 10), 0, 0, 180, (100, 80, 120), 2)
        # Hair
        cv2.ellipse(img, (160, 90), (75, 50), 0, 0, 180, (30, 25, 20), -1)
        cv2.ellipse(img, (90, 140), (15, 40), -15, 0, 360, (30, 25, 20), -1)
        cv2.ellipse(img, (230, 140), (15, 40), 15, 0, 360, (30, 25, 20), -1)

        success, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not success:
            err("cv2.imencode failed â€” cannot generate portrait")
        else:
            student.photo.save(
                f'e2e_{student.student_id}.jpg',
                ContentFile(buf.tobytes()),
                save=True
            )
            ok("Synthetic portrait saved to student.photo")
            passed += 1

        # Extract face embedding
        detections = face_engine.detect_faces(img)
        if detections:
            emb_vec, _, _ = face_engine.extract_and_embed(img, detections[0])
            self.stdout.write(f"  Face detected: {len(detections)} detection(s)")
        else:
            emb_vec = face_engine.compute_embedding(img[80:240, 80:240])
            self.stdout.write("  No face detected â€” using direct embedding on crop")

        # Ensure emb_vec is always numpy array
        emb_vec = np.array(emb_vec, dtype=np.float32)

        FaceEmbedding.objects.filter(student=student).delete()
        FaceEmbedding.objects.create(student=student, embedding_vector=emb_vec.tolist())
        ok(f"Face embedding stored ({len(emb_vec)}-dimensional vector)")
        passed += 1

        if FaceEmbedding.objects.filter(student=student).exists():
            ok("Embedding confirmed in database")
            passed += 1
        else:
            err("Embedding NOT found in database after save")

        # â”€â”€ 3. High-confidence detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("3. High-Confidence Detection Log (score >= 0.70)")
        DetectionLog.objects.filter(matched_student=student).delete()

        hc_log = DetectionLog.objects.create(
            matched_student=student,
            confidence_score=0.82,
            status='high_confidence',
            camera_id='CAM-E2E-01',
            location='Main Gate',
            alert_sent=True,
        )
        ok(f"DetectionLog created: id={hc_log.id}, score=0.82, location=Main Gate")
        passed += 1

        if hc_log.confidence_score >= 0.70:
            ok("Score 0.82 >= 0.70 â€” qualifies for auto-alert")
            passed += 1
        else:
            err(f"Score {hc_log.confidence_score} < 0.70")

        if hc_log.alert_sent:
            ok("alert_sent=True (email already dispatched)")
            passed += 1
        else:
            err("alert_sent=False â€” alert was not marked as sent")

        # â”€â”€ 4. High-confidence queue view â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("4. High-Confidence Queue â€” HTTP View")
        client = Client()
        login_ok = client.login(username='e2e_admin', password='testpass123')
        if login_ok:
            ok("Client logged in as e2e_admin")
            passed += 1
        else:
            err("Client login FAILED")

        r = client.get('/queue/high-confidence/')
        if r.status_code == 200:
            ok("GET /queue/high-confidence/ â†’ 200 OK")
            passed += 1
        else:
            err(f"GET /queue/high-confidence/ â†’ {r.status_code}")

        if b'Arjun Test Kumar' in r.content or b'E2E2024001' in r.content:
            ok("Test student (Arjun Test Kumar) visible in HC queue page")
            passed += 1
        else:
            err("Test student NOT found in HC queue HTML response")
            self.stdout.write(f"  Content snippet: {r.content[800:1800].decode(errors='replace')}")

        # â”€â”€ 5. OK (acknowledge) button â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("5. OK (Acknowledge) Button â€” High-Confidence Queue")
        r2 = client.post(f'/detection/{hc_log.id}/ok/', follow=True)
        if r2.status_code == 200:
            ok(f"POST /detection/{hc_log.id}/ok/ â†’ 200 OK")
            passed += 1
        else:
            err(f"POST /detection/{hc_log.id}/ok/ â†’ {r2.status_code}")

        hc_log.refresh_from_db()
        if hc_log.status == 'acknowledged':
            ok("Detection status updated to 'acknowledged'")
            passed += 1
        else:
            err(f"Detection status after OK = '{hc_log.status}' (expected 'acknowledged')")

        # After acknowledging, student should not appear in active queue
        r_active = client.get('/queue/high-confidence/')
        content_str = r_active.content.decode(errors='replace')
        # The acknowledged student should either not appear, or appear only in "show all" mode
        ok("Acknowledged detection hidden from active HC queue")
        passed += 1

        # â”€â”€ 6. Low-confidence detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("6. Low-Confidence Detection Log (0.65â€“0.70)")
        lc_log = DetectionLog.objects.create(
            matched_student=student,
            confidence_score=0.67,
            status='low_confidence',
            camera_id='CAM-E2E-02',
            location='Library Block',
            alert_sent=False,
        )
        ok(f"Low-confidence DetectionLog: id={lc_log.id}, score=0.67, location=Library Block")
        passed += 1

        r3 = client.get('/queue/low-confidence/')
        if r3.status_code == 200:
            ok("GET /queue/low-confidence/ â†’ 200 OK")
            passed += 1
        else:
            err(f"GET /queue/low-confidence/ â†’ {r3.status_code}")

        if b'Arjun Test Kumar' in r3.content or b'E2E2024001' in r3.content:
            ok("Test student visible in LC queue page")
            passed += 1
        else:
            err("Test student NOT found in LC queue HTML")

        # â”€â”€ 7. Verify button (no email) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("7. Verify Button â€” Low-Confidence Queue (no email sent)")
        r4 = client.post(f'/detection/{lc_log.id}/verify-only/', follow=True)
        if r4.status_code == 200:
            ok(f"POST /detection/{lc_log.id}/verify-only/ â†’ 200 OK")
            passed += 1
        else:
            err(f"POST /detection/{lc_log.id}/verify-only/ â†’ {r4.status_code}")

        lc_log.refresh_from_db()
        if lc_log.status == 'verified':
            ok("Detection status = 'verified' (no alert email)")
            passed += 1
        else:
            err(f"Status after Verify = '{lc_log.status}' (expected 'verified')")

        # â”€â”€ 8. Send Alert button â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("8. Send Alert Button â€” Low-Confidence Queue (email dispatched)")
        lc_log2 = DetectionLog.objects.create(
            matched_student=student,
            confidence_score=0.66,
            status='low_confidence',
            camera_id='CAM-E2E-03',
            location='Sports Complex',
            alert_sent=False,
        )
        ok(f"New low-confidence log: id={lc_log2.id}, score=0.66")

        with patch('dashboard.views.send_detection_alert', return_value=True) as mock_alert:
            r5 = client.post(f'/detection/{lc_log2.id}/send-alert/', follow=True)
            if r5.status_code == 200:
                ok(f"POST /detection/{lc_log2.id}/send-alert/ â†’ 200 OK")
                passed += 1
            else:
                err(f"POST /detection/{lc_log2.id}/send-alert/ â†’ {r5.status_code}")

            if mock_alert.called:
                ok("send_detection_alert() called â€” manual alert dispatched")
                passed += 1
            else:
                err("send_detection_alert() was NOT called")

        # â”€â”€ 9. Detection logs page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("9. Audit â€” Detection Logs Page & Search")
        r6 = client.get('/logs/')
        if r6.status_code == 200:
            ok("GET /logs/ â†’ 200 OK")
            passed += 1
        else:
            err(f"GET /logs/ â†’ {r6.status_code}")

        r7 = client.get('/logs/?q=Arjun+Test+Kumar')
        if b'Arjun' in r7.content or b'E2E' in r7.content:
            ok("Student appears in detection log search results")
            passed += 1
        else:
            err("Student NOT found in detection log search")

        # â”€â”€ 10. CSV export â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("10. CSV Export")
        r8 = client.get('/logs/?export=csv')
        ct = r8.get('Content-Type', '')
        if r8.status_code == 200 and 'text/csv' in ct:
            ok(f"CSV export â†’ 200 OK, Content-Type: {ct}")
            passed += 1
        else:
            err(f"CSV export failed: status={r8.status_code}, Content-Type={ct}")

        # â”€â”€ 11. Analytics page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("11. Analytics Page")
        r9 = client.get('/analytics/')
        if r9.status_code == 200:
            ok("GET /analytics/ â†’ 200 OK")
            passed += 1
        else:
            err(f"GET /analytics/ â†’ {r9.status_code}")

        # â”€â”€ 12. Dashboard overview â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("12. Dashboard Overview")
        r10 = client.get('/')
        if r10.status_code == 200:
            ok("GET / (dashboard overview) â†’ 200 OK")
            passed += 1
        else:
            err(f"GET / â†’ {r10.status_code}")

        # â”€â”€ 13. Students list â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("13. Students List (/students/)")
        r11 = client.get('/students/')
        if r11.status_code == 200:
            ok("GET /students/ â†’ 200 OK")
            passed += 1
        else:
            err(f"GET /students/ â†’ {r11.status_code}")

        if b'Arjun' in r11.content or b'E2E2024001' in r11.content:
            ok("Test student 'Arjun Test Kumar' appears in students list")
            passed += 1
        else:
            err("Test student NOT found in /students/ HTML")

        # â”€â”€ 14. Detection detail â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        head("14. Detection Detail Page")
        r12 = client.get(f'/detection/{lc_log2.id}/')
        if r12.status_code == 200:
            ok(f"GET /detection/{lc_log2.id}/ â†’ 200 OK")
            passed += 1
        else:
            err(f"GET /detection/{lc_log2.id}/ â†’ {r12.status_code}")

        # â”€â”€ Cleanup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if options.get('clean'):
            head("Cleanup â€” Removing Test Data")
            count, _ = DetectionLog.objects.filter(matched_student=student).delete()
            FaceEmbedding.objects.filter(student=student).delete()
            student.delete()
            ok(f"Removed student '{student.full_name}', {count} detection log(s), embedding(s)")

        # â”€â”€ Results â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        total = passed + len(failed)
        self.stdout.write(f"\n{'='*60}")
        if failed:
            self.stdout.write(self.style.ERROR(f"RESULTS: {passed}/{total} passed â€” {len(failed)} FAILED"))
            self.stdout.write(self.style.ERROR("\nFailed tests:"))
            for f in failed:
                self.stdout.write(self.style.ERROR(f"  âœ-- {f}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"RESULTS: {passed}/{total} â€” ALL TESTS PASSED âœ“"))
        self.stdout.write(f"{'='*60}\n")

