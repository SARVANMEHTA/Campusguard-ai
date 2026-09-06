import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from students.models import SuspendedStudent
from surveillance.models import DetectionLog


class DashboardAndApiWorkflowTest(TestCase):
    def setUp(self):
        self.client = Client()
        today = timezone.now().date()
        
        self.student = SuspendedStudent.objects.create(
            student_id="21BCE9999",
            full_name="Workflow Demo Student",
            department="CSE",
            year="4th Year",
            suspension_reason="Demo testing",
            suspension_start_date=today,
            suspension_end_date=today + datetime.timedelta(days=30),
            status="active"
        )
        
        self.detection = DetectionLog.objects.create(
            matched_student=self.student,
            camera_id="CAM-01",
            location="Main Gate",
            confidence_score=0.92,
            status="high_confidence"
        )

    def test_dashboard_views(self):
        response = self.client.get(reverse('dashboard:overview'))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('dashboard:high_confidence_queue'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Workflow Demo Student")

        response = self.client.get(reverse('dashboard:low_confidence_queue'))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('dashboard:detection_logs'))
        self.assertEqual(response.status_code, 200)

    def test_verify_detection_workflow(self):
        # Admin verifies match
        response = self.client.post(
            reverse('dashboard:verify_detection', kwargs={'pk': self.detection.id}),
            {'admin_notes': 'Confirmed on CCTV'}
        )
        self.assertEqual(response.status_code, 302)
        
        self.detection.refresh_from_db()
        self.assertEqual(self.detection.status, 'verified')
        self.assertTrue(self.detection.alert_sent)
        self.assertIsNotNone(self.detection.alert_sent_at)

    def test_reject_detection_workflow(self):
        det2 = DetectionLog.objects.create(
            matched_student=self.student,
            camera_id="CAM-02",
            location="Hostel Gate",
            confidence_score=0.74,
            status="low_confidence"
        )
        
        response = self.client.post(
            reverse('dashboard:reject_detection', kwargs={'pk': det2.id}),
            {'admin_notes': 'False positive verification'}
        )
        self.assertEqual(response.status_code, 302)
        
        det2.refresh_from_db()
        self.assertEqual(det2.status, 'rejected')
        self.assertFalse(det2.alert_sent)

    def test_rest_api_stats_and_queues(self):
        response = self.client.get(reverse('api:system_stats_api'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('active_suspended_students', data)
        self.assertIn('total_pending_review', data)
