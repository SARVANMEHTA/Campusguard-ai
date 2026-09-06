import time
import cv2
import numpy as np
from django.conf import settings
from django.utils import timezone
from django.core.files.base import ContentFile
from students.models import SuspendedStudent, FaceEmbedding
from surveillance.models import DetectionLog


class SurveillanceMatcher:
    """
    In-memory vectorized cosine similarity matcher for live surveillance feeds.
    Maintains cached embeddings for active suspended students and handles
    deduplication cooldowns and tiered confidence classification.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SurveillanceMatcher, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, 'initialized', False):
            return
        self.student_ids = []
        self.embedding_matrix = None # numpy array of shape (N, 128)
        self.student_lookup = {}     # student_db_id -> SuspendedStudent instance
        self.recent_detections = {}  # student_id -> last_detected_timestamp
        self.recent_alerts = {}      # student_id -> last_successful_alert_timestamp
        self.recent_low_conf = {}    # student_id -> last_low_conf_timestamp
        self._last_cache_check = 0
        self._cached_counts = None
        self.reload_cache()
        self.initialized = True

    def reload_cache(self):
        """Loads all active suspended students and their embeddings into in-memory matrix."""
        students = SuspendedStudent.objects.filter(status='active').prefetch_related('embeddings')
        
        vectors = []
        student_id_map = []
        lookup = {}
        
        for student in students:
            lookup[student.id] = student
            for emb in student.embeddings.all():
                if emb.embedding_vector and len(emb.embedding_vector) == 128:
                    vec = np.array(emb.embedding_vector, dtype=np.float32)
                    norm = np.linalg.norm(vec)
                    if norm > 1e-6:
                        vec = vec / norm
                        vectors.append(vec)
                        student_id_map.append(student.id)
                        
        if vectors:
            self.embedding_matrix = np.vstack(vectors) # shape (N, 128)
            self.student_ids = student_id_map
        else:
            self.embedding_matrix = None
            self.student_ids = []
            
        self.student_lookup = lookup
        self._cached_counts = (len(lookup), len(vectors))
        return len(self.student_ids)

    def check_and_refresh_cache(self):
        """
        Periodically verifies if active students or embeddings in the DB changed.
        If changed, automatically reloads the vectorized matrix so newly registered
        persons are immediately recognized in ongoing live video feeds.
        """
        now = time.time()
        if hasattr(self, '_last_cache_check') and (now - self._last_cache_check) < 2.0:
            return
        self._last_cache_check = now
        try:
            total_active = SuspendedStudent.objects.filter(status='active').count()
            total_embs = FaceEmbedding.objects.filter(student__status='active').count()
            current_counts = (total_active, total_embs)
            if getattr(self, '_cached_counts', None) != current_counts:
                self.reload_cache()
        except Exception:
            pass

    def match_embedding(self, query_vector):
        """
        Computes cosine similarity against all indexed suspended students.
        Returns (best_student, best_score, classification).
        """
        if self.embedding_matrix is None or len(self.student_ids) == 0:
            return None, 0.0, 'no_active_database'
            
        q_vec = np.array(query_vector, dtype=np.float32)
        norm = np.linalg.norm(q_vec)
        if norm > 1e-6:
            q_vec = q_vec / norm
        else:
            return None, 0.0, 'invalid_vector'
            
        # Vectorized dot product (Cosine Similarity because vectors are L2-normalized)
        similarities = np.dot(self.embedding_matrix, q_vec)
        
        best_idx = int(np.argmax(similarities))
        best_score = float(similarities[best_idx])
        matched_student_id = self.student_ids[best_idx]
        matched_student = self.student_lookup.get(matched_student_id)
        
        # If student not in lookup, fetch from DB
        if matched_student is None:
            try:
                matched_student = SuspendedStudent.objects.get(id=matched_student_id)
                self.student_lookup[matched_student_id] = matched_student
            except SuspendedStudent.DoesNotExist:
                return None, 0.0, 'unmatched'

        # Tiered classification according to Section 4.1
        low_th = getattr(settings, 'CONFIDENCE_THRESHOLD_LOW', 0.65)
        high_th = getattr(settings, 'CONFIDENCE_THRESHOLD_HIGH', 0.70)

        if best_score >= high_th:
            classification = 'high_confidence'
        elif best_score >= low_th:
            classification = 'low_confidence'
        else:
            classification = 'unmatched'
            
        return matched_student, best_score, classification

    def is_in_cooldown(self, student_id, classification='low_confidence', cooldown_seconds=None):
        """
        Checks whether this detection is in cooldown.
        High-confidence (>70%) alerts are ONLY in cooldown if an alert was ALREADY
        successfully dispatched for this student within ALERT_COOLDOWN_SECONDS (default 60s).
        A previous low-confidence detection NEVER blocks a high-confidence alert!
        """
        now = time.time()
        if classification == 'high_confidence':
            if cooldown_seconds is None:
                cooldown_seconds = getattr(settings, 'ALERT_COOLDOWN_SECONDS', 60)
            last_alert_time = self.recent_alerts.get(student_id, 0)
            return (now - last_alert_time) < cooldown_seconds
        else:
            if cooldown_seconds is None:
                cooldown_seconds = getattr(settings, 'LOW_CONF_COOLDOWN_SECONDS', 60)
            # If student was recently alerted at high confidence, suppress low confidence duplicates
            if (now - self.recent_alerts.get(student_id, 0)) < 60:
                return True
            last_time = self.recent_low_conf.get(student_id, 0)
            return (now - last_time) < cooldown_seconds

    def record_detection(self, student_id, classification='low_confidence'):
        """Updates last detection timestamp for deduplication."""
        now = time.time()
        self.recent_detections[student_id] = now
        if classification == 'high_confidence':
            self.recent_alerts[student_id] = now
        else:
            self.recent_low_conf[student_id] = now

    def process_and_log_frame(self, frame_bgr, bbox, embedding, camera_id="CAM-01", location="Main Gate - Gate 1", force_log=False):
        """
        Executes full matching logic for a detected face in a frame.
        If confidence >= threshold and not in cooldown, saves DetectionLog to DB.
        Automatically syncs cache for newly registered persons and triggers instant email alerts on >70% match.
        Returns dict with match details.
        """
        # Automatically refresh cache if new students/embeddings were added
        self.check_and_refresh_cache()

        matched_student, score, classification = self.match_embedding(embedding)
        
        result = {
            'matched': False,
            'student': matched_student,
            'confidence': score,
            'confidence_pct': round(score * 100, 1),
            'classification': classification,
            'logged': False,
            'log_id': None,
            'in_cooldown': False,
            'alert_dispatched': False,
        }
        
        if classification in ['high_confidence', 'low_confidence']:
            result['matched'] = True
            
            # Check cooldown specific to the classification level
            if not force_log and self.is_in_cooldown(matched_student.id, classification=classification):
                result['in_cooldown'] = True
                return result
                
            # Crop snapshot face + context
            x, y, w, h = bbox
            h_img, w_img = frame_bgr.shape[:2]
            # Include 25% surrounding context in snapshot
            ctx_x1 = max(0, int(x - 0.25 * w))
            ctx_y1 = max(0, int(y - 0.25 * h))
            ctx_x2 = min(w_img, int(x + 1.25 * w))
            ctx_y2 = min(h_img, int(y + 1.25 * h))
            
            snapshot_crop = frame_bgr[ctx_y1:ctx_y2, ctx_x1:ctx_x2]
            
            # Draw bounding box and confidence tag on snapshot for evidence audit
            overlay_snap = snapshot_crop.copy()
            
            # Encode snapshot to JPEG
            _, buffer = cv2.imencode('.jpg', overlay_snap, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            filename = f"detect_{matched_student.student_id}_{int(time.time())}.jpg"
            image_content = ContentFile(buffer.tobytes(), name=filename)
            
            if classification == 'high_confidence':
                # ── HIGH CONFIDENCE (>70%) ──
                # Immediate synchronous email alert dispatch with zero human approval gate
                log_entry = DetectionLog.objects.create(
                    matched_student=matched_student,
                    camera_id=camera_id,
                    location=location,
                    confidence_score=score,
                    snapshot_image=image_content,
                    status='verified',
                    alert_sent=False,
                    admin_notes='Automatic instant alert: high-confidence match exceeded 70% threshold.'
                )

                from alerts.mailer import send_detection_alert
                alert_ok = False
                try:
                    alert_ok = send_detection_alert(
                        detection_log=log_entry,
                        admin_user=None,
                        admin_notes="Automatic instant alert: high-confidence match (>70%)."
                    )
                except Exception as mail_err:
                    import logging
                    logging.getLogger(__name__).error(f"Error dispatching instant alert for log #{log_entry.id}: {mail_err}")

                if alert_ok:
                    # Successfully dispatched alert: record alert cooldown
                    self.record_detection(matched_student.id, classification='high_confidence')
                    result['alert_dispatched'] = True
                    
                    # Resolve any pending unverified low-confidence logs for this student
                    try:
                        recent_unverified = DetectionLog.objects.filter(
                            matched_student=matched_student,
                            status='low_confidence'
                        )
                        recent_unverified.update(
                            status='verified',
                            admin_notes='Superseded by automatic high-confidence CCTV detection.'
                        )
                    except Exception:
                        pass
                else:
                    # If alert dispatch failed, do NOT lock out cooldown so subsequent frames can retry immediately
                    pass
            else:
                # ── LOW CONFIDENCE (65% - 70%) ──
                # Preserved for manual human review queue
                log_entry = DetectionLog.objects.create(
                    matched_student=matched_student,
                    camera_id=camera_id,
                    location=location,
                    confidence_score=score,
                    snapshot_image=image_content,
                    status='low_confidence'
                )
                self.record_detection(matched_student.id, classification='low_confidence')
            
            result['logged'] = True
            result['log_id'] = log_entry.id
            result['log_obj'] = log_entry
            
        return result


# Singleton matcher instance
matcher = SurveillanceMatcher()
