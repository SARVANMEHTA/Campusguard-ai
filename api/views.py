from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Count, Q
from students.models import SuspendedStudent
from surveillance.models import DetectionLog
from alerts.mailer import send_detection_alert
from .serializers import SuspendedStudentSerializer, DetectionLogSerializer


class SuspendedStudentListAPI(generics.ListCreateAPIView):
    queryset = SuspendedStudent.objects.all().prefetch_related('embeddings')
    serializer_class = SuspendedStudentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        if status_param in ['active', 'expired']:
            qs = qs.filter(status=status_param)
        return qs


class SuspendedStudentDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    queryset = SuspendedStudent.objects.all().prefetch_related('embeddings')
    serializer_class = SuspendedStudentSerializer


class DetectionLogListAPI(generics.ListAPIView):
    queryset = DetectionLog.objects.all().select_related('matched_student', 'admin_reviewed_by')
    serializer_class = DetectionLogSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        camera_id = self.request.query_params.get('camera_id')
        student_id = self.request.query_params.get('student_id')

        if status_param:
            qs = qs.filter(status=status_param)
        if camera_id:
            qs = qs.filter(camera_id=camera_id)
        if student_id:
            qs = qs.filter(matched_student__student_id__icontains=student_id)

        return qs


class HighConfidenceQueueAPI(generics.ListAPIView):
    queryset = DetectionLog.objects.filter(status='high_confidence').select_related('matched_student')
    serializer_class = DetectionLogSerializer


class LowConfidenceQueueAPI(generics.ListAPIView):
    queryset = DetectionLog.objects.filter(status='low_confidence').select_related('matched_student')
    serializer_class = DetectionLogSerializer


@api_view(['POST'])
def verify_detection_api(request, pk):
    """
    Action to verify detection match and trigger email alert to specific or default recipients.
    Requires explicit admin confirmation.
    """
    try:
        detection = DetectionLog.objects.get(pk=pk)
    except DetectionLog.DoesNotExist:
        return Response({'error': 'Detection log not found'}, status=status.HTTP_404_NOT_FOUND)

    admin_notes = request.data.get('notes', '')
    recipient_input = request.data.get('recipient_email', '')
    
    custom_recipients = None
    if recipient_input:
        if isinstance(recipient_input, list):
            custom_recipients = recipient_input
        elif isinstance(recipient_input, str):
            custom_recipients = [e.strip() for e in recipient_input.replace(';', ',').split(',') if e.strip()]

    user = request.user if request.user.is_authenticated else None
    
    # Send email alert & update detection status to verified
    alert_success = send_detection_alert(
        detection_log=detection,
        admin_user=user,
        custom_recipients=custom_recipients,
        admin_notes=admin_notes
    )

    return Response({
        'success': True,
        'message': f"Detection #{detection.id} verified. Alert dispatched to security authority.",
        'recipients': custom_recipients or getattr(settings, 'ALERT_RECIPIENT_EMAILS', []),
        'alert_sent': alert_success,
        'status': detection.status,
        'alert_sent_at': detection.alert_sent_at
    })



@api_view(['POST'])
def reject_detection_api(request, pk):
    """
    Action to mark detection as False Positive / Rejected.
    """
    try:
        detection = DetectionLog.objects.get(pk=pk)
    except DetectionLog.DoesNotExist:
        return Response({'error': 'Detection log not found'}, status=status.HTTP_404_NOT_FOUND)

    admin_notes = request.data.get('notes', 'Marked as false positive.')
    user = request.user if request.user.is_authenticated else None

    detection.status = 'rejected'
    detection.admin_reviewed_by = user
    detection.admin_notes = admin_notes
    detection.save(update_fields=['status', 'admin_reviewed_by', 'admin_notes'])

    return Response({
        'success': True,
        'message': f"Detection #{detection.id} marked as rejected (False Positive).",
        'status': detection.status
    })


@api_view(['GET'])
def system_stats_api(request):
    """System-wide summary metrics for dashboard widgets & telemetry."""
    today = timezone.now().date()
    
    total_detections_today = DetectionLog.objects.filter(timestamp__date=today).count()
    high_conf_pending = DetectionLog.objects.filter(status='high_confidence').count()
    low_conf_pending = DetectionLog.objects.filter(status='low_confidence').count()
    total_verified = DetectionLog.objects.filter(status='verified').count()
    total_rejected = DetectionLog.objects.filter(status='rejected').count()
    active_suspended_students = SuspendedStudent.objects.filter(status='active').count()

    gate_breakdown = list(
        DetectionLog.objects.values('location')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )

    return Response({
        'total_detections_today': total_detections_today,
        'high_confidence_pending': high_conf_pending,
        'low_confidence_pending': low_conf_pending,
        'total_pending_review': high_conf_pending + low_conf_pending,
        'total_verified_alerts': total_verified,
        'total_rejected_false_positives': total_rejected,
        'active_suspended_students': active_suspended_students,
        'gate_breakdown': gate_breakdown
    })
