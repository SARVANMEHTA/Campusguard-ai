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


import threading
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class RemoteCameraBuffer:
    """In-memory thread-safe buffer for incoming frames from authorized laptop camera node."""
    latest_frame = None
    last_seen = 0.0
    location = "Main Gate - Gate 1"
    camera_id = "CAM-01"
    lock = threading.Lock()

    @classmethod
    def update(cls, frame_bytes, location="Main Gate - Gate 1", camera_id="CAM-01"):
        with cls.lock:
            cls.latest_frame = frame_bytes
            cls.last_seen = time.time()
            cls.location = location
            cls.camera_id = camera_id

    @classmethod
    def get_frame(cls):
        with cls.lock:
            if cls.latest_frame and (time.time() - cls.last_seen < 6.0):
                return cls.latest_frame
            return None

    @classmethod
    def is_online(cls):
        with cls.lock:
            return bool(cls.latest_frame and (time.time() - cls.last_seen < 6.0))


def generate_standby_frame(location="Main Gate - Gate 1", camera_id="CAM-01"):
    """
    Generates an authenticated, sleek cyber HUD standby frame
    when the authorized laptop camera node is not currently pushing frames.
    """
    img = np.zeros((400, 720, 3), dtype=np.uint8)
    # Deep cyber dark background
    img[:] = (25, 15, 11)

    # Cyan border and tactical corner ticks
    cv2.rectangle(img, (10, 10), (709, 389), (248, 189, 56), 1)
    c_len = 20
    for x, y in [(10, 10), (709, 10), (10, 389), (709, 389)]:
        dx = 1 if x == 10 else -1
        dy = 1 if y == 10 else -1
        cv2.line(img, (x, y), (x + dx * c_len, y), (56, 189, 248), 2)
        cv2.line(img, (x, y), (x, y + dy * c_len), (56, 189, 248), 2)

    # Top header bar
    now_str = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    cv2.putText(img, "CAMPUSGUARD AI // AUTHORIZED GATE CCTV CONSOLE", (24, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (203, 213, 225), 1, cv2.LINE_AA)
    cv2.putText(img, now_str, (510, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (148, 163, 184), 1, cv2.LINE_AA)

    # Center card
    cv2.rectangle(img, (60, 95), (660, 290), (35, 23, 16), -1)
    cv2.rectangle(img, (60, 95), (660, 290), (70, 50, 30), 1)

    # Pulsing amber standby indicator
    cv2.circle(img, (100, 142), 8, (0, 165, 255), -1)
    cv2.putText(img, "GATE 1 CAMERA NODE: STANDBY", (125, 148), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (255, 255, 255), 2, cv2.LINE_AA)

    cv2.putText(img, f"Designated Channel: {location} ({camera_id})", (100, 188), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (203, 213, 225), 1, cv2.LINE_AA)
    cv2.putText(img, "Awaiting live camera video from your authorized laptop.", (100, 216), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (148, 163, 184), 1, cv2.LINE_AA)
    
    cv2.rectangle(img, (95, 240), (625, 275), (50, 35, 20), -1)
    cv2.putText(img, "Run on laptop:  python gate_camera_node.py", (110, 263), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (56, 189, 248), 1, cv2.LINE_AA)

    # Footer
    cv2.putText(img, "AI Biometric Engine: ONLINE  |  Deep Models: YuNet + SFace (ONNX)  |  Node Ingest: READY", (24, 370), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (148, 163, 184), 1, cv2.LINE_AA)

    ret, buffer = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return buffer.tobytes() if ret else b''


def gen_frames(camera_source=0, sample_rate=3, location="Main Gate - Gate 1", camera_id="CAM-01"):
    """
    Dynamic video generator:
    1. If an authorized laptop camera node is streaming to /surveillance/node/push/, streams it.
    2. Else if local hardware camera is available (running on local dev laptop), captures local hardware.
    3. Else renders an authenticated cyber standby screen with live timestamp.
    """
    cap = None
    has_local_camera = False

    # Check if local hardware camera is physically present
    try:
        test_source = int(camera_source) if str(camera_source).isdigit() else camera_source
        test_cap = cv2.VideoCapture(test_source)
        if test_cap.isOpened():
            ret, test_frame = test_cap.read()
            if ret and test_frame is not None:
                cap = test_cap
                has_local_camera = True
            else:
                test_cap.release()
        else:
            test_cap.release()
    except Exception:
        pass

    frame_count = 0
    detected_cache = []

    try:
        while True:
            # 1. Prioritize authorized laptop camera node stream
            remote_frame = RemoteCameraBuffer.get_frame()
            if remote_frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + remote_frame + b'\r\n')
                time.sleep(0.08)
                continue

            # 2. If running locally with local hardware camera attached
            if has_local_camera and cap and cap.isOpened():
                success, frame = cap.read()
                if success and frame is not None:
                    frame_count += 1
                    if frame_count % sample_rate == 0:
                        detected_cache = []
                        try:
                            matcher.check_and_refresh_cache()
                            detections = face_engine.detect_faces(frame)
                            for det in detections:
                                embedding, aligned_face, bbox = face_engine.extract_and_embed(frame, det)
                                if embedding is None:
                                    continue

                                match_result = matcher.process_and_log_frame(
                                    frame_bgr=frame, bbox=bbox, embedding=embedding,
                                    camera_id=camera_id, location=location
                                )
                                student = match_result['student']
                                pct = match_result['confidence_pct']
                                classification = match_result['classification']
                                if classification == 'high_confidence':
                                    color = (0, 0, 255)
                                    label = f"HIGH ALERT: {student.full_name} ({pct}%)"
                                elif classification == 'low_confidence':
                                    color = (0, 165, 255)
                                    label = f"SUSPECT: {student.full_name} ({pct}%)"
                                else:
                                    color = (0, 255, 0)
                                    label = f"Safe ({pct}%)"

                                detected_cache.append({'bbox': bbox, 'color': color, 'label': label})
                        except Exception as det_err:
                            logger.error(f"Detection error in local loop: {det_err}")

                    display_frame = frame.copy()
                    for det in detected_cache:
                        x, y, w, h = det['bbox']
                        cv2.rectangle(display_frame, (x, y), (x + w, y + h), det['color'], 2)
                        cv2.rectangle(display_frame, (x, max(0, y - 24)), (x + w, y), det['color'], -1)
                        cv2.putText(display_frame, det['label'], (x + 5, max(12, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

                    ret, buffer = cv2.imencode('.jpg', display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    if ret:
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                    time.sleep(0.04)
                    continue

            # 3. Render authenticated cyber standby frame when laptop node is offline
            standby_bytes = generate_standby_frame(location=location, camera_id=camera_id)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + standby_bytes + b'\r\n')
            time.sleep(1.0)
    finally:
        if cap and cap.isOpened():
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


@csrf_exempt
def ingest_node_frame(request):
    """
    Receives live video frame from the authorized laptop camera node.
    Stores frame in memory buffer to broadcast live to all dashboard viewers.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    location = request.POST.get('location', 'Main Gate - Gate 1')
    camera_id = request.POST.get('camera_id', 'CAM-01')

    frame_bytes = None
    if 'frame' in request.FILES:
        frame_bytes = request.FILES['frame'].read()
    elif request.body and len(request.body) > 100:
        frame_bytes = request.body

    if not frame_bytes:
        return JsonResponse({'error': 'No frame payload received'}, status=400)

    RemoteCameraBuffer.update(frame_bytes, location=location, camera_id=camera_id)
    return JsonResponse({'status': 'ok', 'bytes_received': len(frame_bytes)})


def node_status_view(request):
    """Returns JSON status of the authorized laptop camera node."""
    online = RemoteCameraBuffer.is_online()
    last_seen = round(time.time() - RemoteCameraBuffer.last_seen, 1) if RemoteCameraBuffer.last_seen > 0 else None
    return JsonResponse({
        'online': online,
        'location': RemoteCameraBuffer.location,
        'camera_id': RemoteCameraBuffer.camera_id,
        'last_seen_seconds_ago': last_seen,
    })


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
