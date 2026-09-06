import time
import cv2
import json
import numpy as np
from django.shortcuts import render, get_object_or_404, redirect
from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.conf import settings
from students.embeddings import face_engine
from surveillance.matcher import matcher
from surveillance.models import DetectionLog


import logging

logger = logging.getLogger(__name__)


def gen_frames(camera_source=0, sample_rate=3, location="Main Gate - Gate 1", camera_id="CAM-01"):
    """
    Generator function that captures frames from camera/video,
    runs face detection & matching, draws overlays, and yields multipart JPEG stream.
    """
    if str(camera_source).isdigit():
        camera_source = int(camera_source)

    cap = cv2.VideoCapture(camera_source)
    frame_count = 0
    detected_cache = []
    consecutive_failures = 0

    try:
        while True:
            success, frame = cap.read()
            if not success or frame is None:
                consecutive_failures += 1
                time.sleep(0.05)
                if consecutive_failures > 50:
                    logger.warning("Camera stream source reached end or disconnected.")
                    break
                continue

            consecutive_failures = 0
            frame_count += 1

            if frame_count % sample_rate == 0:
                detected_cache = []
                try:
                    # Sync cache so any newly registered students/embeddings are immediately recognized
                    matcher.check_and_refresh_cache()

                    detections = face_engine.detect_faces(frame)
                    for det in detections:
                        embedding, aligned_face, bbox = face_engine.extract_and_embed(frame, det)
                        if embedding is None:
                            continue

                        match_result = matcher.process_and_log_frame(
                            frame_bgr=frame,
                            bbox=bbox,
                            embedding=embedding,
                            camera_id=camera_id,
                            location=location
                        )

                        student = match_result['student']
                        pct = match_result['confidence_pct']
                        classification = match_result['classification']
                        alert_sent = match_result.get('alert_dispatched', False)

                        if classification == 'high_confidence':
                            color = (0, 0, 255) # Red
                            if alert_sent:
                                label = f"HIGH ALERT: {student.full_name} ({pct}%) [ALERT SENT]"
                                logger.info(f"[HIGH ALERT DISPATCHED] {student.full_name} ({student.student_id}) at {location} - Score: {pct}%")
                            elif match_result.get('in_cooldown', False):
                                label = f"HIGH ALERT: {student.full_name} ({pct}%) [ALERT DISPATCHED]"
                            else:
                                label = f"HIGH ALERT: {student.full_name} ({pct}%)"
                        elif classification == 'low_confidence':
                            color = (0, 165, 255) # Orange
                            label = f"SUSPECT: {student.full_name} ({pct}%)"
                        else:
                            color = (0, 255, 0) # Green
                            label = f"Visitor ({pct}%)"

                        detected_cache.append({'bbox': bbox, 'color': color, 'label': label, 'classification': classification})
                except Exception as frame_err:
                    logger.error(f"Error during live detection/logging: {frame_err}", exc_info=True)

            # Render overlay
            try:
                display_frame = frame.copy()
                for det in detected_cache:
                    x, y, w, h = det['bbox']
                    color = det['color']
                    label = det['label']
                    cv2.rectangle(display_frame, (x, y), (x + w, y + h), color, 2)
                    cv2.rectangle(display_frame, (x, max(0, y - 24)), (x + w, y), color, -1)
                    cv2.putText(display_frame, label, (x + 5, max(12, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

                ret, buffer = cv2.imencode('.jpg', display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            except Exception as render_err:
                logger.error(f"Error rendering live frame: {render_err}")
    finally:
        cap.release()


def live_stream_feed(request):
    """MJPEG live video stream response for browser."""
    camera_source = request.GET.get('source', str(getattr(settings, 'DEFAULT_CAMERA_SOURCE', 0)))
    location = request.GET.get('location', getattr(settings, 'DEFAULT_GATE_LOCATION', 'Main Gate - Gate 1'))
    camera_id = request.GET.get('camera_id', 'CAM-01')
    sample_rate = int(request.GET.get('sample_rate', getattr(settings, 'FRAME_SAMPLE_RATE', 5)))

    return StreamingHttpResponse(
        gen_frames(camera_source=camera_source, sample_rate=sample_rate, location=location, camera_id=camera_id),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


def live_monitor_view(request):
    """Dedicated live surveillance gate console view."""
    matcher.reload_cache()
    recent_logs = DetectionLog.objects.filter(status__in=['high_confidence', 'low_confidence', 'verified']).order_by('-timestamp')[:10]
    
    context = {
        'recent_logs': recent_logs,
        'active_students_count': len(matcher.student_ids),
        'default_location': getattr(settings, 'DEFAULT_GATE_LOCATION', 'Main Gate - Gate 1'),
    }
    return render(request, 'dashboard/live_monitor.html', context)


@csrf_exempt
def process_single_image(request):
    """
    Endpoint allowing admins or test scripts to upload a single test image/frame
    and run full face recognition and logging against the suspended database.
    """
    if request.method == 'POST' and 'image' in request.FILES:
        image_file = request.FILES['image']
        location = request.POST.get('location', 'Gate 1 - Manual Inspection')
        camera_id = request.POST.get('camera_id', 'INSPECTION-01')

        try:
            image_bytes = image_file.read()
            nparr = np.frombuffer(image_bytes, np.uint8)
            frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            detections = face_engine.detect_faces(frame_bgr)
            if not detections:
                return JsonResponse({'success': False, 'message': 'No face detected in submitted image.'})

            results = []
            for det in detections:
                embedding, aligned_face, bbox = face_engine.extract_and_embed(frame_bgr, det)
                if embedding is None:
                    continue

                res = matcher.process_and_log_frame(
                    frame_bgr=frame_bgr,
                    bbox=bbox,
                    embedding=embedding,
                    camera_id=camera_id,
                    location=location,
                    force_log=True
                )
                
                results.append({
                    'matched': res['matched'],
                    'student_name': res['student'].full_name if res['student'] else None,
                    'student_id': res['student'].student_id if res['student'] else None,
                    'confidence_pct': res['confidence_pct'],
                    'classification': res['classification'],
                    'log_id': res['log_id']
                })

            return JsonResponse({'success': True, 'detections': results})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request'})
