import csv
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Count, Q, Max
from students.models import SuspendedStudent
from surveillance.models import DetectionLog
from alerts.mailer import send_detection_alert


def dashboard_overview(request):
    """Main CampusGuard AI Command Center overview."""
    today = timezone.now().date()
    
    # Counts - show each detected student only once in high-conf queue
    latest_high_ids = (
        DetectionLog.objects.filter(
            confidence_score__gte=0.70,
            matched_student__isnull=False
        ).exclude(status__in=['rejected', 'acknowledged'])
        .values('matched_student')
        .annotate(latest_id=Max('id'))
        .values_list('latest_id', flat=True)
    )
    high_conf_queue = DetectionLog.objects.filter(id__in=latest_high_ids).select_related('matched_student').order_by('-timestamp')[:5]
    low_conf_queue = DetectionLog.objects.filter(status='low_confidence').select_related('matched_student').order_by('-timestamp')[:5]
    
    today_detections_count = DetectionLog.objects.filter(timestamp__date=today).count()
    verified_today_count = DetectionLog.objects.filter(timestamp__date=today, status='verified').count()
    rejected_today_count = DetectionLog.objects.filter(timestamp__date=today, status='rejected').count()
    active_suspended_count = SuspendedStudent.objects.filter(status='active').count()
    
    recent_logs = DetectionLog.objects.all().select_related('matched_student', 'admin_reviewed_by')[:10]
    
    context = {
        'high_conf_queue': high_conf_queue,
        'low_conf_queue': low_conf_queue,
        'today_detections_count': today_detections_count,
        'verified_today_count': verified_today_count,
        'rejected_today_count': rejected_today_count,
        'active_suspended_count': active_suspended_count,
        'recent_logs': recent_logs,
    }
    return render(request, 'dashboard/index.html', context)


def high_confidence_queue(request):
    """
    High-Confidence detected persons list (>70% match).
    Shows each detected person only once (latest incident per student).
    Displays the person name and Alert Dispatched Automatically status in Content View.
    Supports active queue filtering and 'OK' acknowledgment.
    """
    show_all = request.GET.get('show') == 'all'
    
    base_query = DetectionLog.objects.filter(
        confidence_score__gte=0.70,
        matched_student__isnull=False
    ).exclude(status='rejected')
    
    if not show_all:
        base_query = base_query.exclude(status='acknowledged')
        
    latest_ids = (
        base_query.values('matched_student')
        .annotate(latest_id=Max('id'))
        .values_list('latest_id', flat=True)
    )
    detections = DetectionLog.objects.filter(id__in=latest_ids).select_related('matched_student').order_by('-timestamp')
    
    active_count = (
        DetectionLog.objects.filter(
            confidence_score__gte=0.70,
            matched_student__isnull=False
        ).exclude(status__in=['rejected', 'acknowledged'])
        .values('matched_student')
        .distinct()
        .count()
    )
    
    return render(request, 'dashboard/high_confidence_queue.html', {
        'detections': detections,
        'show_all': show_all,
        'active_count': active_count,
    })


def low_confidence_queue(request):
    """
    Low-Confidence review queue (65%-70% match).
    Content View layout matching high-confidence queue.
    Shows each detected person once (latest incident per student) with Active vs All History filtering.
    """
    show_all = request.GET.get('show') == 'all'
    
    if not show_all:
        latest_ids = (
            DetectionLog.objects.filter(
                status='low_confidence',
                matched_student__isnull=False
            ).values('matched_student')
            .annotate(latest_id=Max('id'))
            .values_list('latest_id', flat=True)
        )
        detections = DetectionLog.objects.filter(id__in=latest_ids).select_related('matched_student').order_by('-timestamp')
    else:
        all_low_ids = (
            DetectionLog.objects.filter(
                confidence_score__gte=0.65,
                confidence_score__lt=0.70,
                matched_student__isnull=False
            ).values('matched_student')
            .annotate(latest_id=Max('id'))
            .values_list('latest_id', flat=True)
        )
        detections = DetectionLog.objects.filter(id__in=all_low_ids).select_related('matched_student').order_by('-timestamp')

    active_count = (
        DetectionLog.objects.filter(
            status='low_confidence',
            matched_student__isnull=False
        ).values('matched_student')
        .distinct()
        .count()
    )
    
    return render(request, 'dashboard/low_confidence_queue.html', {
        'detections': detections,
        'show_all': show_all,
        'active_count': active_count,
    })


def verify_only_detection(request, pk):
    """
    'Verify' action: Marks detection as Verified by security officer
    without dispatching an email alert.
    """
    detection = get_object_or_404(DetectionLog, pk=pk)
    user = request.user if request.user.is_authenticated else None
    note = request.POST.get('admin_notes') or request.GET.get('admin_notes') or 'Verified by security officer.'

    detection.status = 'verified'
    detection.admin_reviewed_by = user
    if detection.admin_notes:
        detection.admin_notes = f"{detection.admin_notes} | {note}"
    else:
        detection.admin_notes = note
    detection.save(update_fields=['status', 'admin_reviewed_by', 'admin_notes'])

    student_name = detection.matched_student.full_name if detection.matched_student else f"Detection #{detection.id}"
    messages.success(request, f"Detection for {student_name} confirmed as Verified.")
    next_url = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER') or 'dashboard:low_confidence_queue'
    return redirect(next_url)


def send_alert_detection(request, pk):
    """
    'Send Alert' action: Sends official security email alert and marks detection as verified.
    """
    detection = get_object_or_404(DetectionLog, pk=pk)
    user = request.user if request.user.is_authenticated else None
    notes = request.POST.get('admin_notes') or request.GET.get('admin_notes') or 'Verified and alert dispatched by security officer.'
    recipient_input = request.POST.get('recipient_email', '').strip() or request.GET.get('recipient_email', '').strip()

    custom_recipients = [e.strip() for e in recipient_input.replace(';', ',').split(',') if e.strip()] if recipient_input else None

    success = send_detection_alert(
        detection_log=detection,
        admin_user=user,
        custom_recipients=custom_recipients,
        admin_notes=notes
    )

    student_name = detection.matched_student.full_name if detection.matched_student else f"Detection #{detection.id}"
    target_display = f"to {', '.join(custom_recipients)}" if custom_recipients else "to campus authorities"
    if success:
        messages.success(request, f"🚨 Security alert email dispatched {target_display} for {student_name}!")
    else:
        messages.warning(request, f"Detection verified for {student_name}. (Email alert logged {target_display}).")

    next_url = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER') or 'dashboard:low_confidence_queue'
    return redirect(next_url)


def verify_detection(request, pk):
    """Backwards-compatible alias to send_alert_detection."""
    return send_alert_detection(request, pk)


def reject_detection(request, pk):
    """Action to mark detection as False Positive / Rejected."""
    detection = get_object_or_404(DetectionLog, pk=pk)
    notes = request.POST.get('admin_notes') or request.GET.get('admin_notes') or 'Rejected by admin as false positive.'
    
    user = request.user if request.user.is_authenticated else None
    detection.status = 'rejected'
    detection.admin_reviewed_by = user
    detection.admin_notes = notes
    detection.save(update_fields=['status', 'admin_reviewed_by', 'admin_notes'])
    
    messages.info(request, f"Detection #{detection.id} marked as Rejected / False Positive.")
    next_url = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER') or 'dashboard:overview'
    return redirect(next_url)


def acknowledge_detection(request, pk):
    """
    Action to acknowledge / mark detection as OK.
    Sets status to 'acknowledged' and records officer timestamp.
    Supports both POST and GET.
    """
    detection = get_object_or_404(DetectionLog, pk=pk)
    notes = request.POST.get('admin_notes') or request.GET.get('admin_notes') or 'Acknowledged by security officer (OK).'
    user = request.user if request.user.is_authenticated else None

    detection.status = 'acknowledged'
    detection.admin_reviewed_by = user
    if detection.admin_notes:
        detection.admin_notes = f"{detection.admin_notes} | {notes}"
    else:
        detection.admin_notes = notes
    detection.save(update_fields=['status', 'admin_reviewed_by', 'admin_notes'])

    student_name = detection.matched_student.full_name if detection.matched_student else f"Detection #{detection.id}"
    messages.success(request, f"Detection for {student_name} acknowledged (OK).")
    next_url = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER') or 'dashboard:high_confidence_queue'
    return redirect(next_url)



def detection_logs(request):
    """Searchable, filterable audit log of all historical detections."""
    status_filter = request.GET.get('status', 'all')
    camera_filter = request.GET.get('camera', 'all')
    query = request.GET.get('q', '').strip()

    logs = DetectionLog.objects.all().select_related('matched_student', 'admin_reviewed_by')

    if status_filter and status_filter != 'all':
        logs = logs.filter(status=status_filter)

    if camera_filter and camera_filter != 'all':
        logs = logs.filter(camera_id=camera_filter)

    if query:
        logs = logs.filter(
            Q(matched_student__full_name__icontains=query) |
            Q(matched_student__student_id__icontains=query) |
            Q(location__icontains=query) |
            Q(camera_id__icontains=query) |
            Q(admin_notes__icontains=query)
        )

    # Export to CSV if requested
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="campusguard_detection_logs_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Log ID', 'Timestamp', 'Student Name', 'Student ID', 'Confidence Score', 'Status', 'Location', 'Camera ID', 'Alert Sent', 'Reviewed By', 'Notes'])
        for log in logs:
            writer.writerow([
                log.id,
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.matched_student.full_name if log.matched_student else 'Unknown',
                log.matched_student.student_id if log.matched_student else 'N/A',
                f"{log.confidence_percentage}%",
                log.get_status_display(),
                log.location,
                log.camera_id,
                'Yes' if log.alert_sent else 'No',
                log.admin_reviewed_by.username if log.admin_reviewed_by else 'N/A',
                log.admin_notes or ''
            ])
        return response

    cameras = DetectionLog.objects.values_list('camera_id', flat=True).distinct()

    context = {
        'logs': logs,
        'status_filter': status_filter,
        'camera_filter': camera_filter,
        'query': query,
        'cameras': cameras,
    }
    return render(request, 'dashboard/detection_logs.html', context)


def detection_detail(request, pk):
    """Detailed case investigation modal or standalone view."""
    detection = get_object_or_404(DetectionLog.objects.select_related('matched_student', 'admin_reviewed_by'), pk=pk)
    return render(request, 'dashboard/detection_detail.html', {'detection': detection})


def analytics_view(request):
    """Visual analytics dashboard with detection metrics and distributions."""
    total_detections = DetectionLog.objects.count()
    verified_count = DetectionLog.objects.filter(status='verified').count()
    rejected_count = DetectionLog.objects.filter(status='rejected').count()
    high_conf_count = DetectionLog.objects.filter(status='high_confidence').count()
    low_conf_count = DetectionLog.objects.filter(status='low_confidence').count()

    gate_stats = list(
        DetectionLog.objects.values('location')
        .annotate(count=Count('id'))
        .order_by('-count')[:6]
    )

    context = {
        'total_detections': total_detections,
        'verified_count': verified_count,
        'rejected_count': rejected_count,
        'high_conf_count': high_conf_count,
        'low_conf_count': low_conf_count,
        'gate_stats': gate_stats,
    }
    return render(request, 'dashboard/analytics.html', context)
