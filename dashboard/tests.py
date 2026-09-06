from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from students.models import SuspendedStudent
from surveillance.models import DetectionLog


class HighConfidenceQueueTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.student = SuspendedStudent.objects.create(
            student_id="TEST001",
            full_name="Test Student",
            department="Computer Science",
            year="4th Year",
            suspension_reason="Disciplinary violation",
            suspension_start_date=timezone.now().date(),
            suspension_end_date=timezone.now().date() + timezone.timedelta(days=30),
            status="active"
        )
        self.detection = DetectionLog.objects.create(
            matched_student=self.student,
            camera_id="CAM-01",
            location="Main Gate",
            confidence_score=0.75,
            status="verified",
            alert_sent=True,
            alert_sent_at=timezone.now()
        )

    def test_high_confidence_queue_content_view(self):
        response = self.client.get(reverse('dashboard:high_confidence_queue'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Student")
        self.assertContains(response, "75.0% Match")
        self.assertContains(response, "Alert Dispatched Automatically")
        self.assertContains(response, "OK")

    def test_acknowledge_detection(self):
        response = self.client.post(reverse('dashboard:acknowledge_detection', args=[self.detection.id]))
        self.assertEqual(response.status_code, 302)
        self.detection.refresh_from_db()
        self.assertEqual(self.detection.status, 'acknowledged')

        # Active queue context should now exclude this acknowledged detection
        active_resp = self.client.get(reverse('dashboard:high_confidence_queue'))
        active_students = [d.matched_student for d in active_resp.context['detections']]
        self.assertNotIn(self.student, active_students)

        # All history view should still include it
        all_resp = self.client.get(reverse('dashboard:high_confidence_queue') + '?show=all')
        all_students = [d.matched_student for d in all_resp.context['detections']]
        self.assertIn(self.student, all_students)
        self.assertContains(all_resp, "Acknowledged")


class LowConfidenceQueueTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.student = SuspendedStudent.objects.create(
            student_id="TEST002",
            full_name="Low Conf Student",
            department="Electrical",
            year="3rd Year",
            suspension_reason="Attendance shortage",
            suspension_start_date=timezone.now().date(),
            suspension_end_date=timezone.now().date() + timezone.timedelta(days=30),
            status="active"
        )
        self.detection = DetectionLog.objects.create(
            matched_student=self.student,
            camera_id="CAM-02",
            location="East Gate",
            confidence_score=0.68,
            status="low_confidence",
            alert_sent=False
        )

    def test_low_confidence_queue_content_view(self):
        response = self.client.get(reverse('dashboard:low_confidence_queue'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Low Conf Student")
        self.assertContains(response, "68.0% Match")
        self.assertContains(response, "Awaiting Human Verification")
        self.assertContains(response, "Verify")
        self.assertContains(response, "Send Alert")

    def test_verify_only_detection(self):
        response = self.client.post(reverse('dashboard:verify_only_detection', args=[self.detection.id]))
        self.assertEqual(response.status_code, 302)
        self.detection.refresh_from_db()
        self.assertEqual(self.detection.status, 'verified')
        self.assertFalse(self.detection.alert_sent)

        # Active low-conf queue should now exclude this detection
        active_resp = self.client.get(reverse('dashboard:low_confidence_queue'))
        active_students = [d.matched_student for d in active_resp.context['detections']]
        self.assertNotIn(self.student, active_students)

    def test_send_alert_detection(self):
        response = self.client.post(reverse('dashboard:send_alert_detection', args=[self.detection.id]))
        self.assertEqual(response.status_code, 302)
        self.detection.refresh_from_db()
        self.assertEqual(self.detection.status, 'verified')
        self.assertTrue(self.detection.alert_sent)

        # Active low-conf queue should now exclude this detection
        active_resp = self.client.get(reverse('dashboard:low_confidence_queue'))
        active_students = [d.matched_student for d in active_resp.context['detections']]
        self.assertNotIn(self.student, active_students)

