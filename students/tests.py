import datetime
from django.test import TestCase
from django.utils import timezone
from students.models import SuspendedStudent, FaceEmbedding


class SuspendedStudentModelTest(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.student = SuspendedStudent.objects.create(
            student_id="TEST001",
            full_name="Test Student",
            department="Computer Science",
            year="4th Year",
            suspension_reason="Testing disciplinary system",
            suspension_start_date=today - datetime.timedelta(days=2),
            suspension_end_date=today + datetime.timedelta(days=10),
            status="active"
        )
        self.embedding = FaceEmbedding.objects.create(
            student=self.student,
            embedding_vector=[0.1] * 128,
            model_version="sface-128"
        )

    def test_student_creation_and_suspension_status(self):
        self.assertEqual(self.student.student_id, "TEST001")
        self.assertTrue(self.student.is_currently_suspended)
        self.assertEqual(self.student.embeddings.count(), 1)

    def test_status_auto_expiry(self):
        # Move end date to past
        self.student.suspension_end_date = timezone.now().date() - datetime.timedelta(days=1)
        self.student.save()
        self.student.check_and_update_status()
        self.assertEqual(self.student.status, 'expired')
        self.assertFalse(self.student.is_currently_suspended)
