import os
import datetime
import numpy as np
import cv2
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.files.base import ContentFile
from django.conf import settings
from students.models import SuspendedStudent, FaceEmbedding
from students.embeddings import face_engine
from surveillance.models import DetectionLog
from surveillance.matcher import matcher


def generate_synthetic_portrait(seed_id, name="Student"):
    """
    Generates a synthetic face portrait containing facial landmarks
    so face detectors and feature extractors produce reliable deep embeddings.
    """
    np.random.seed(seed_id * 37 + 101)
    
    # Base canvas 320x320
    img = np.full((320, 320, 3), (235, 225, 215), dtype=np.uint8)
    
    skin_tones = [
        (185, 205, 235), # Fair BGR
        (160, 185, 215), # Wheatish
        (140, 165, 200), # Medium
        (120, 145, 180), # Dusky
    ]
    skin = skin_tones[seed_id % len(skin_tones)]
    
    hair_colors = [
        (30, 25, 20),
        (20, 20, 20),
        (45, 35, 30),
    ]
    hair = hair_colors[seed_id % len(hair_colors)]

    # Background gradient
    for y in range(320):
        shade = int(240 - y * 0.15)
        img[y, :] = (shade - 10, shade, shade + 10)

    # Torso/Shirt
    shirt_colors = [(180, 80, 50), (60, 120, 180), (80, 140, 80), (120, 60, 120)]
    shirt_color = shirt_colors[seed_id % len(shirt_colors)]
    cv2.ellipse(img, (160, 340), (110, 80), 0, 0, 360, shirt_color, -1)
    cv2.ellipse(img, (160, 270), (45, 30), 0, 0, 360, (int(skin[0]*0.9), int(skin[1]*0.9), int(skin[2]*0.9)), -1)

    # Head / Face Oval
    cv2.ellipse(img, (160, 160), (68, 85), 0, 0, 360, skin, -1)
    cv2.ellipse(img, (160, 160), (68, 85), 0, 0, 360, (int(skin[0]*0.8), int(skin[1]*0.8), int(skin[2]*0.8)), 2)

    # Hair
    cv2.ellipse(img, (160, 105), (72, 45), 0, 0, 180, hair, -1)
    cv2.ellipse(img, (100, 140), (18, 45), -15, 0, 360, hair, -1)
    cv2.ellipse(img, (220, 140), (18, 45), 15, 0, 360, hair, -1)

    # Eyebrows
    cv2.ellipse(img, (132, 132), (18, 4), -8, 0, 360, hair, -1)
    cv2.ellipse(img, (188, 132), (18, 4), 8, 0, 360, hair, -1)

    # Eyes
    cv2.ellipse(img, (132, 148), (14, 8), 0, 0, 360, (250, 250, 250), -1)
    cv2.ellipse(img, (188, 148), (14, 8), 0, 0, 360, (250, 250, 250), -1)
    cv2.circle(img, (132, 148), 6, (40, 60, 30), -1)
    cv2.circle(img, (188, 148), 6, (40, 60, 30), -1)
    cv2.circle(img, (132, 148), 3, (10, 10, 10), -1)
    cv2.circle(img, (188, 148), 3, (10, 10, 10), -1)
    cv2.circle(img, (134, 146), 2, (255, 255, 255), -1)
    cv2.circle(img, (190, 146), 2, (255, 255, 255), -1)

    # Nose
    nose_color = (int(skin[0]*0.75), int(skin[1]*0.75), int(skin[2]*0.75))
    pts_nose = np.array([[160, 145], [153, 178], [167, 178]], np.int32)
    cv2.polylines(img, [pts_nose], False, nose_color, 2)

    # Mouth / Lips
    cv2.ellipse(img, (160, 205), (20, 7), 0, 0, 360, (110, 110, 180), -1)
    cv2.ellipse(img, (160, 204), (16, 2), 0, 0, 360, (80, 80, 140), -1)

    # Encode to JPEG
    _, buffer = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    return buffer.tobytes(), img


class Command(BaseCommand):
    help = "Populates realistic demo data for CampusGuard AI (Admin user, Suspended Students, Face Embeddings, Detection Logs)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("[CAMPUSGUARD AI] POPULATING DEMO DATASET"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        # 1. Create Default Admin User
        admin_user, created = User.objects.get_or_create(username='admin')
        if created:
            admin_user.set_password('admin123')
            admin_user.is_superuser = True
            admin_user.is_staff = True
            admin_user.first_name = "Chief Security"
            admin_user.last_name = "Officer"
            admin_user.email = "security.admin@campus.edu"
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("[OK] Created Superuser: admin (Password: admin123)"))
        else:
            self.stdout.write("[OK] Superuser 'admin' already exists.")

        # 2. Sample Suspended Students
        today = timezone.now().date()
        demo_students_data = [
            {
                'id': 1,
                'student_id': '21BCE1045',
                'full_name': 'Aarav Mehta',
                'department': 'Computer Science & Engineering',
                'year': '4th Year (8th Sem)',
                'reason': 'Found responsible for unauthorized server room intrusion and campus network tampering during mid-term evaluations.',
                'start_offset': -10,
                'end_offset': 50,
                'status': 'active'
            },
            {
                'id': 2,
                'student_id': '22BME1082',
                'full_name': 'Rohan Deshmukh',
                'department': 'Mechanical Engineering',
                'year': '3rd Year (6th Sem)',
                'reason': 'Engaged in severe physical altercation inside hostel block B dining hall resulting in property damage.',
                'start_offset': -5,
                'end_offset': 25,
                'status': 'active'
            },
            {
                'id': 3,
                'student_id': '23BEC2014',
                'full_name': 'Priya Nair',
                'department': 'Electronics & Communication',
                'year': '2nd Year (4th Sem)',
                'reason': 'Repeated violation of campus curfew regulations and unauthorized entry into staff quarters.',
                'start_offset': -2,
                'end_offset': 40,
                'status': 'active'
            },
            {
                'id': 4,
                'student_id': '20BCI1009',
                'full_name': 'Vikramaditya Rao',
                'department': 'Civil Engineering',
                'year': '4th Year (8th Sem)',
                'reason': 'Organized an unsanctioned protest blockade near the University Chancellor Complex.',
                'start_offset': -90,
                'end_offset': -10,
                'status': 'expired'
            },
            {
                'id': 5,
                'student_id': '22BIT3021',
                'full_name': 'Karan Malhotra',
                'department': 'Information Technology',
                'year': '3rd Year (5th Sem)',
                'reason': 'Academic dishonesty during end-semester exams involving electronic communication gear.',
                'start_offset': -15,
                'end_offset': 60,
                'status': 'active'
            }
        ]

        created_students = []
        for sdata in demo_students_data:
            student, s_created = SuspendedStudent.objects.get_or_create(
                student_id=sdata['student_id'],
                defaults={
                    'full_name': sdata['full_name'],
                    'department': sdata['department'],
                    'year': sdata['year'],
                    'suspension_reason': sdata['reason'],
                    'suspension_start_date': today + datetime.timedelta(days=sdata['start_offset']),
                    'suspension_end_date': today + datetime.timedelta(days=sdata['end_offset']),
                    'status': sdata['status'],
                    'added_by': admin_user
                }
            )

            # Generate synthetic portrait & embeddings
            img_bytes, img_bgr = generate_synthetic_portrait(sdata['id'], sdata['full_name'])
            
            filename = f"student_{sdata['student_id']}.jpg"
            student.photo.save(filename, ContentFile(img_bytes), save=True)

            # Extract and store 128-d face embedding
            detections = face_engine.detect_faces(img_bgr)
            if detections:
                embedding_vec, aligned_face, bbox = face_engine.extract_and_embed(img_bgr, detections[0])
            else:
                embedding_vec = face_engine.compute_embedding(img_bgr[80:240, 80:240])
            
            FaceEmbedding.objects.get_or_create(
                student=student,
                defaults={
                    'embedding_vector': embedding_vec,
                    'model_version': 'sface-128',
                }
            )
            created_students.append((student, img_bytes, img_bgr))
            self.stdout.write(f"[OK] Enrolled Student: {student.full_name} ({student.student_id}) - Status: {student.get_status_display()}")

        # 3. Create Sample Detection Logs
        self.stdout.write("\nGenerating sample surveillance detection events across queues...")
        
        # S1 (Aarav Mehta) -> High Confidence Pending
        s1 = created_students[0][0]
        s1_bytes = created_students[0][1]
        DetectionLog.objects.create(
            matched_student=s1,
            camera_id='CAM-01',
            location='Main Gate - Turnstile 2',
            confidence_score=0.934,
            snapshot_image=ContentFile(s1_bytes, name=f"snap_{s1.student_id}_high.jpg"),
            status='high_confidence',
            alert_sent=False
        )
        self.stdout.write("[OK] Created High-Confidence Queue Item: Aarav Mehta (93.4% Match at Main Gate)")

        # S2 (Rohan Deshmukh) -> Low Confidence Pending
        s2 = created_students[1][0]
        s2_bytes = created_students[1][1]
        DetectionLog.objects.create(
            matched_student=s2,
            camera_id='CAM-03',
            location='Hostel Block Gate - North',
            confidence_score=0.782,
            snapshot_image=ContentFile(s2_bytes, name=f"snap_{s2.student_id}_low.jpg"),
            status='low_confidence',
            alert_sent=False
        )
        self.stdout.write("[OK] Created Low-Confidence Queue Item: Rohan Deshmukh (78.2% Match at Hostel Gate)")

        # S3 (Priya Nair) -> Verified Incident (Alert Sent)
        s3 = created_students[2][0]
        s3_bytes = created_students[2][1]
        DetectionLog.objects.create(
            matched_student=s3,
            camera_id='CAM-02',
            location='Library Entrance - East Gate',
            confidence_score=0.915,
            snapshot_image=ContentFile(s3_bytes, name=f"snap_{s3.student_id}_verified.jpg"),
            status='verified',
            admin_reviewed_by=admin_user,
            admin_notes="Student sighted near library turnstiles. Security personnel dispatched immediately.",
            alert_sent=True,
            alert_sent_at=timezone.now() - datetime.timedelta(hours=2)
        )
        self.stdout.write("[OK] Created Verified Incident Log: Priya Nair (Alert Sent)")

        # S5 (Karan Malhotra) -> Rejected False Positive
        s5 = created_students[4][0]
        s5_bytes = created_students[4][1]
        DetectionLog.objects.create(
            matched_student=s5,
            camera_id='CAM-04',
            location='Sports Complex - Gate 3',
            confidence_score=0.735,
            snapshot_image=ContentFile(s5_bytes, name=f"snap_{s5.student_id}_rejected.jpg"),
            status='rejected',
            admin_reviewed_by=admin_user,
            admin_notes="Visual inspection confirmed different individual (fellow student with similar hairstyle).",
            alert_sent=False
        )
        self.stdout.write("[OK] Created Rejected False Positive Log: Karan Malhotra")

        # 4. Seed Alert Recipients
        self.stdout.write("\nEnrolling default Security Alert Email Contacts...")
        from alerts.models import AlertRecipient
        sample_recipients = [
            {'name': 'Campus Main Gate Security Desk', 'email': 'security.desk@campus.edu', 'role': 'security', 'department': 'Main Gate'},
            {'name': 'Prof. M. K. Sharma (Chief Proctor)', 'email': 'chief.proctor@campus.edu', 'role': 'proctor', 'department': 'Proctorial Board'},
            {'name': 'Dr. S. V. Raman (HOD CSE)', 'email': 'hod.cse@campus.edu', 'role': 'hod', 'department': 'Computer Science & Engg'},
            {'name': 'Chief Warden (Hostels)', 'email': 'chief.warden@campus.edu', 'role': 'warden', 'department': 'Hostel Administration'},
        ]
        for r in sample_recipients:
            rec_obj, _ = AlertRecipient.objects.get_or_create(email=r['email'], defaults=r)
            self.stdout.write(f"[OK] Enrolled Alert Recipient: {rec_obj.name} <{rec_obj.email}>")

        # 5. Reload in-memory matcher cache
        count = matcher.reload_cache()
        self.stdout.write(self.style.SUCCESS(f"\n[OK] In-Memory Surveillance Matcher Cache Reloaded: {count} active embeddings indexed."))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("[SUCCESS] DEMO DATA GENERATION COMPLETE!"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

