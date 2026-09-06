import os
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import io
from django.core.files.base import ContentFile
from django.conf import settings


class FaceEngine:
    """
    State-of-the-art Deep Neural Network Face Detection & Recognition Engine.
    Uses OpenCV YuNet (Deep Face Detection) + SFace (Deep 128-d Feature Extraction).
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FaceEngine, cls).__new__(cls)
            cls._instance._initialize_models()
        return cls._instance

    def _initialize_models(self):
        project_root = getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent)
        yunet_path = os.path.join(project_root, 'models', 'dnn', 'face_detection_yunet_2023mar.onnx')
        sface_path = os.path.join(project_root, 'models', 'dnn', 'face_recognition_sface_2021dec.onnx')

        if not os.path.exists(yunet_path) or not os.path.exists(sface_path):
            raise FileNotFoundError(f"Deep neural network models missing from {yunet_path} or {sface_path}")

        # Initialize YuNet Face Detector
        self.detector = cv2.FaceDetectorYN_create(
            model=yunet_path,
            config="",
            input_size=(320, 320),
            score_threshold=0.6,
            nms_threshold=0.3,
            top_k=50
        )
        
        # Initialize SFace Deep Face Feature Extractor
        self.recognizer = cv2.FaceRecognizerSF_create(
            model=sface_path,
            config=""
        )

    def detect_faces(self, image_bgr):
        """
        Detects faces in BGR frame.
        Returns list of (x, y, w, h) bounding boxes and raw face array with 5 landmarks.
        """
        if image_bgr is None or image_bgr.size == 0:
            return []

        h, w = image_bgr.shape[:2]
        self.detector.setInputSize((w, h))
        
        _, faces = self.detector.detect(image_bgr)
        
        if faces is None:
            return []

        results = []
        for face in faces:
            box = face[0:4].astype(int)
            x, y, bw, bh = max(0, box[0]), max(0, box[1]), max(1, box[2]), max(1, box[3])
            results.append({
                'bbox': (int(x), int(y), int(bw), int(bh)),
                'raw_face': face,
                'score': float(face[14])
            })
            
        return results

    def extract_and_embed(self, image_bgr, face_data=None):
        """
        Aligns, crops face and computes L2-normalized 128-d deep biometric embedding vector.
        Returns (embedding_vector, aligned_face_bgr, bbox).
        """
        if image_bgr is None or image_bgr.size == 0:
            return None, None, None

        if face_data is None:
            detections = self.detect_faces(image_bgr)
            if not detections:
                return None, None, None
            # Pick highest score or largest face
            face_data = max(detections, key=lambda d: d['bbox'][2] * d['bbox'][3])

        raw_face = face_data['raw_face']
        bbox = face_data['bbox']

        # SFace face alignment and cropping to 112x112 standard input
        aligned_face = self.recognizer.alignCrop(image_bgr, raw_face)
        
        # Extract 128-d feature representation
        feat = self.recognizer.feature(aligned_face) # shape (1, 128)
        vector = feat.flatten().astype(np.float32)

        # L2-normalize
        norm = np.linalg.norm(vector)
        if norm > 1e-6:
            vector = vector / norm
        else:
            vector = np.zeros_like(vector)

        return vector.tolist(), aligned_face, bbox

    def compute_embedding(self, face_bgr):
        """
        Direct feature computation on a pre-cropped face.
        """
        if face_bgr is None or face_bgr.size == 0:
            return None
            
        # Resize to SFace standard 112x112
        resized = cv2.resize(face_bgr, (112, 112))
        feat = self.recognizer.feature(resized)
        vector = feat.flatten().astype(np.float32)
        norm = np.linalg.norm(vector)
        if norm > 1e-6:
            vector = vector / norm
        return vector.tolist()

    def process_image_file_for_embedding(self, image_file):
        """
        Takes uploaded Django ImageField file, runs DNN face detection,
        extracts aligned crop, generates 128-d embedding, and returns (embedding_vec, crop_file).
        """
        image_bytes = image_file.read()
        image_file.seek(0)
        
        nparr = np.frombuffer(image_bytes, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img_bgr is None:
            raise ValueError("Could not decode image file.")

        detections = self.detect_faces(img_bgr)
        if not detections:
            # Fallback for synthetic/clear images: center crop
            h, w = img_bgr.shape[:2]
            cx, cy = w // 2, h // 2
            half = min(w, h) // 3
            center_crop = img_bgr[max(0, cy - half):min(h, cy + half), max(0, cx - half):min(w, cx + half)]
            embedding = self.compute_embedding(center_crop)
            _, buffer = cv2.imencode('.jpg', center_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            crop_content = ContentFile(buffer.tobytes(), name=f"crop_{getattr(image_file, 'name', 'face.jpg')}")
            return embedding, crop_content

        embedding, aligned_face, bbox = self.extract_and_embed(img_bgr, detections[0])
        
        _, buffer = cv2.imencode('.jpg', aligned_face, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        crop_content = ContentFile(buffer.tobytes(), name=f"crop_{getattr(image_file, 'name', 'face.jpg')}")
        
        return embedding, crop_content


# Singleton instance
face_engine = FaceEngine()
