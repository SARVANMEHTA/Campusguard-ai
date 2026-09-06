import datetime
import numpy as np
from django.test import TestCase
from django.utils import timezone
from students.models import SuspendedStudent, FaceEmbedding
from surveillance.models import DetectionLog
from surveillance.matcher import SurveillanceMatcher


class SurveillanceMatcherTest(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.student = SuspendedStudent.objects.create(
            student_id="ROLL-999",
            full_name="Matching Test Candidate",
            department="ECE",
            year="3rd Year",
            suspension_reason="Testing matching logic",
            suspension_start_date=today - datetime.timedelta(days=1),
            suspension_end_date=today + datetime.timedelta(days=20),
            status="active"
        )
        
        # Create a unit normalized vector
        vec = np.zeros(128, dtype=np.float32)
        vec[0] = 1.0 # unit vector on dimension 0
        
        FaceEmbedding.objects.create(
            student=self.student,
            embedding_vector=vec.tolist(),
            model_version="sface-128"
        )

        self.matcher = SurveillanceMatcher()
        self.matcher.reload_cache()

    def test_high_confidence_match(self):
        # Exact vector matching (similarity = 1.0 -> High confidence > 0.70)
        query_vec = np.zeros(128, dtype=np.float32)
        query_vec[0] = 1.0
        
        matched_student, score, classification = self.matcher.match_embedding(query_vec)
        self.assertIsNotNone(matched_student)
        self.assertEqual(matched_student.id, self.student.id)
        self.assertAlmostEqual(score, 1.0, places=2)
        self.assertEqual(classification, 'high_confidence')

    def test_low_confidence_match(self):
        # Angle offset vector to generate ~67% cosine similarity (low confidence 65-70%)
        query_vec = np.zeros(128, dtype=np.float32)
        query_vec[0] = 0.67
        query_vec[1] = np.sqrt(1.0 - 0.67**2)
        
        matched_student, score, classification = self.matcher.match_embedding(query_vec)
        self.assertIsNotNone(matched_student)
        self.assertGreaterEqual(score, 0.65)
        self.assertLess(score, 0.70)
        self.assertEqual(classification, 'low_confidence')

    def test_unmatched_low_similarity(self):
        # Orthogonal vector (similarity = 0.0 -> < 0.65 -> unmatched)
        query_vec = np.zeros(128, dtype=np.float32)
        query_vec[1] = 1.0
        
        matched_student, score, classification = self.matcher.match_embedding(query_vec)
        self.assertLess(score, 0.65)
        self.assertEqual(classification, 'unmatched')

    def test_high_confidence_auto_alert(self):
        # Dummy frame and bbox
        dummy_frame = np.zeros((200, 200, 3), dtype=np.uint8)
        bbox = (20, 20, 100, 100)
        query_vec = np.zeros(128, dtype=np.float32)
        query_vec[0] = 1.0  # Exact match (1.0 > 0.70)

        res = self.matcher.process_and_log_frame(
            frame_bgr=dummy_frame,
            bbox=bbox,
            embedding=query_vec,
            camera_id="TEST-CAM",
            location="Test Gate",
            force_log=True
        )

        self.assertTrue(res['logged'])
        log_obj = DetectionLog.objects.get(id=res['log_id'])
        # High-confidence must be marked verified and alert_sent=True immediately
        self.assertEqual(log_obj.status, 'verified')
        self.assertTrue(log_obj.alert_sent)
        self.assertIsNotNone(log_obj.alert_sent_at)

    def test_low_confidence_queue_entry(self):
        dummy_frame = np.zeros((200, 200, 3), dtype=np.uint8)
        bbox = (20, 20, 100, 100)
        query_vec = np.zeros(128, dtype=np.float32)
        query_vec[0] = 0.67
        query_vec[1] = np.sqrt(1.0 - 0.67**2)

        res = self.matcher.process_and_log_frame(
            frame_bgr=dummy_frame,
            bbox=bbox,
            embedding=query_vec,
            camera_id="TEST-CAM",
            location="Test Gate",
            force_log=True
        )

        self.assertTrue(res['logged'])
        log_obj = DetectionLog.objects.get(id=res['log_id'])
        # Low-confidence must be in queue with status='low_confidence' and alert_sent=False
        self.assertEqual(log_obj.status, 'low_confidence')
        self.assertFalse(log_obj.alert_sent)
