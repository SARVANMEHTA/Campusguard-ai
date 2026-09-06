from rest_framework import serializers
from students.models import SuspendedStudent, FaceEmbedding
from surveillance.models import DetectionLog


class FaceEmbeddingSerializer(serializers.ModelSerializer):
    class Meta:
        model = FaceEmbedding
        fields = ['id', 'model_version', 'created_at']


class SuspendedStudentSerializer(serializers.ModelSerializer):
    embeddings_count = serializers.IntegerField(source='embeddings.count', read_only=True)
    is_suspended = serializers.BooleanField(source='is_currently_suspended', read_only=True)

    class Meta:
        model = SuspendedStudent
        fields = [
            'id',
            'student_id',
            'full_name',
            'photo',
            'department',
            'year',
            'suspension_reason',
            'suspension_start_date',
            'suspension_end_date',
            'status',
            'is_suspended',
            'embeddings_count',
            'created_at'
        ]


class DetectionLogSerializer(serializers.ModelSerializer):
    matched_student_details = SuspendedStudentSerializer(source='matched_student', read_only=True)
    confidence_percentage = serializers.ReadOnlyField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    reviewer_name = serializers.SerializerMethodField()

    class Meta:
        model = DetectionLog
        fields = [
            'id',
            'matched_student',
            'matched_student_details',
            'camera_id',
            'location',
            'timestamp',
            'confidence_score',
            'confidence_percentage',
            'snapshot_image',
            'status',
            'status_display',
            'admin_reviewed_by',
            'reviewer_name',
            'admin_notes',
            'alert_sent',
            'alert_sent_at'
        ]

    def get_reviewer_name(self, obj):
        if obj.admin_reviewed_by:
            return obj.admin_reviewed_by.get_full_name() or obj.admin_reviewed_by.username
        return None
