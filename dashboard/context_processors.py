from surveillance.models import DetectionLog
from students.models import SuspendedStudent


def queue_counts(request):
    """Context processor providing real-time badge numbers across all dashboard views."""
    try:
        high_conf_count = (
            DetectionLog.objects.filter(
                confidence_score__gte=0.70,
                matched_student__isnull=False
            ).exclude(status__in=['rejected', 'acknowledged'])
            .values('matched_student')
            .distinct()
            .count()
        )
        low_conf_count = (
            DetectionLog.objects.filter(
                status='low_confidence',
                matched_student__isnull=False
            ).values('matched_student')
            .distinct()
            .count()
        )
        pending_count = DetectionLog.objects.filter(status='pending').count()
        active_students_count = SuspendedStudent.objects.filter(status='active').count()
        total_reviews_pending = high_conf_count + low_conf_count + pending_count
        
        return {
            'nav_high_conf_count': high_conf_count,
            'nav_low_conf_count': low_conf_count,
            'nav_total_pending': total_reviews_pending,
            'nav_active_students': active_students_count,
        }
    except Exception:
        # Fallback before initial migrations
        return {
            'nav_high_conf_count': 0,
            'nav_low_conf_count': 0,
            'nav_total_pending': 0,
            'nav_active_students': 0,
        }
