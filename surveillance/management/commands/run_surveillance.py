import time
import cv2
import sys
from django.core.management.base import BaseCommand
from django.conf import settings
from students.embeddings import face_engine
from surveillance.matcher import matcher
from surveillance.models import DetectionLog


class Command(BaseCommand):
    help = "Runs CampusGuard AI real-time face recognition surveillance pipeline on CCTV / webcam feed."

    def add_arguments(self, parser):
        parser.add_argument(
            '--camera',
            type=str,
            default=str(getattr(settings, 'DEFAULT_CAMERA_SOURCE', 0)),
            help='Camera index (e.g. 0), video file path, or RTSP stream URL'
        )
        parser.add_argument(
            '--sample-rate',
            type=int,
            default=getattr(settings, 'FRAME_SAMPLE_RATE', 5),
            help='Process every N-th frame (default: 5)'
        )
        parser.add_argument(
            '--location',
            type=str,
            default=getattr(settings, 'DEFAULT_GATE_LOCATION', 'Main Gate - Gate 1'),
            help='Campus gate or surveillance camera location'
        )
        parser.add_argument(
            '--camera-id',
            type=str,
            default='CAM-01',
            help='Camera identifier code'
        )
        parser.add_argument(
            '--headless',
            action='store_true',
            help='Run in headless mode without desktop GUI preview window'
        )
        parser.add_argument(
            '--max-frames',
            type=int,
            default=0,
            help='Limit execution to N frames (0 for infinite loop until quit)'
        )

    def handle(self, *args, **options):
        camera_source = options['camera']
        sample_rate = options['sample_rate']
        location = options['location']
        camera_id = options['camera_id']
        headless = options['headless']
        max_frames = options['max_frames']

        if camera_source.isdigit():
            camera_source = int(camera_source)

        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("[CAMPUSGUARD AI] REAL-TIME SURVEILLANCE RUNTIME ENGINE"))
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(f"- Camera Source: {camera_source}")
        self.stdout.write(f"- Gate Location: {location} (ID: {camera_id})")
        self.stdout.write(f"- Frame Sampling Rate: Every {sample_rate} frame(s)")
        self.stdout.write(f"- Thresholds: Low={settings.CONFIDENCE_THRESHOLD_LOW*100:.0f}% | High={settings.CONFIDENCE_THRESHOLD_HIGH*100:.0f}%")
        self.stdout.write(f"- Deduplication Window: {settings.DEDUPLICATION_COOLDOWN_SECONDS}s")
        
        indexed_count = matcher.reload_cache()
        self.stdout.write(self.style.WARNING(f"- Indexed Active Suspended Embeddings: {indexed_count} vector(s)"))

        self.stdout.write(self.style.SUCCESS("Initializing camera feed..."))
        cap = cv2.VideoCapture(camera_source)

        if not cap.isOpened():
            self.stderr.write(self.style.ERROR(f"[ERROR] Failed to open video source '{camera_source}'."))
            return

        frame_count = 0
        detected_faces_cache = []
        start_time = time.time()

        self.stdout.write(self.style.SUCCESS(">> Surveillance pipeline is ACTIVE. Press 'q' in preview or Ctrl+C to stop.\n"))

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    self.stdout.write(self.style.WARNING("End of video stream reached."))
                    break

                frame_count += 1
                if max_frames > 0 and frame_count >= max_frames:
                    self.stdout.write(self.style.SUCCESS(f"Reached max frame limit of {max_frames}."))
                    break

                if frame_count % sample_rate == 0:
                    detected_faces_cache = []
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
                        is_logged = match_result['logged']

                        if classification == 'high_confidence':
                            color = (0, 0, 255) # Red
                            label = f"HIGH ALERT: {student.full_name} ({pct}%)"
                            if is_logged:
                                self.stdout.write(self.style.ERROR(
                                    f"[HIGH CONFIDENCE] {student.full_name} ({student.student_id}) detected at {location} - Score: {pct}% -> IMMEDIATE ALERT DISPATCHED (Log #{match_result['log_id']})"
                                ))
                        elif classification == 'low_confidence':
                            color = (0, 165, 255) # Orange
                            label = f"SUSPECT: {student.full_name} ({pct}%)"
                            if is_logged:
                                self.stdout.write(self.style.WARNING(
                                    f"[LOW CONFIDENCE] Potential match: {student.full_name} ({student.student_id}) - Score: {pct}% -> Routed to Low-Confidence Queue (Log #{match_result['log_id']})"
                                ))
                        else:
                            color = (0, 255, 0) # Green
                            label = f"Visitor ({pct}%)"

                        detected_faces_cache.append({
                            'bbox': bbox,
                            'color': color,
                            'label': label,
                            'classification': classification
                        })

                if not headless:
                    display_frame = frame.copy()
                    for d in detected_faces_cache:
                        x, y, w, h = d['bbox']
                        color = d['color']
                        label = d['label']
                        cv2.rectangle(display_frame, (x, y), (x + w, y + h), color, 2)
                        cv2.rectangle(display_frame, (x, max(0, y - 25)), (x + w, y), color, -1)
                        cv2.putText(display_frame, label, (x + 5, max(12, y - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

                    cv2.rectangle(display_frame, (0, 0), (display_frame.shape[1], 35), (20, 20, 20), -1)
                    cv2.putText(
                        display_frame,
                        f"CAMPUSGUARD AI | {location} | {camera_id} | ACTIVE SUSPENSIONS: {len(matcher.student_ids)}",
                        (15, 22),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 255, 255),
                        1,
                        cv2.LINE_AA
                    )

                    cv2.imshow("CampusGuard AI - Live Gate Surveillance", display_frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

        except KeyboardInterrupt:
            self.stdout.write(self.style.NOTICE("\nSurveillance stopped."))
        finally:
            cap.release()
            if not headless:
                cv2.destroyAllWindows()
            elapsed = time.time() - start_time
            fps = frame_count / elapsed if elapsed > 0 else 0
            self.stdout.write(self.style.SUCCESS(f"\nPipeline closed. Processed {frame_count} frames in {elapsed:.1f}s ({fps:.1f} FPS)."))
