# 🛡️ CampusGuard AI
### Suspended Student Detection & Alert System Using Deep Face Recognition
*A Complete Final-Year Engineering Project for Campus Perimeter Surveillance*

---

## 📌 Project Overview
**CampusGuard AI** is an intelligent computer-vision and automated alert system engineered for educational institutions. It continuously detects and recognizes faces captured at campus entry gates, matches them against a maintained database of currently suspended students using deep face embeddings and vectorized cosine similarity, applies a tiered confidence-threshold system, and routes matches through a **strict human-in-the-loop verification workflow** before dispatching alerts to campus authorities.

---

## 🏛️ System Architecture & Subsystems

```
+-----------------------------------------------------------------------------------+
| 1. Capture Subsystem (OpenCV Video Streams / Webcam / RTSP Gate Ingestion)        |
+----------------------------------------+------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 2. Recognition Subsystem (YuNet Deep Face Detector -> SFace 128-d Feature Vector) |
+----------------------------------------+------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 3. Vectorized Matcher & Confidence Tier Classifier                                |
|    - < 70%       : Ignored / Discarded (Regular campus visitor)                   |
|    - 70% - 85%   : Low-Confidence Review Queue (Requires detailed inspection)     |
|    - > 85%       : High-Confidence Review Queue (Urgent 1-click sign-off)         |
+----------------------------------------+------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 4. Human Verification Safeguard (Admin verifies match -> Email Alert Dispatched)  |
+-----------------------------------------------------------------------------------+
```

---

## 🚀 Quick Start Guide

### 1. Environment & Setup
```bash
# Clone/Open repository directory
cd "CampusGuard AI"

# Install dependencies
pip install -r requirements.txt
```

### 2. Database Migration & Demo Data Population
```bash
# Run database migrations
python manage.py makemigrations students surveillance
python manage.py migrate

# Populate sample suspended students, embeddings, and detection queues
python manage.py populate_demo_data
```

### 3. Start the Web Dashboard
```bash
python manage.py runserver 8000
```
Open **http://127.0.0.1:8000/** in your web browser.

**Default Admin Credentials:**
- **Username:** `admin`
- **Password:** `admin123`
- **Django Admin Portal:** `http://127.0.0.1:8000/admin/`

---

## 🎥 Running the Surveillance Engine

### Option A: Web-Based Live Gate Monitor
Navigate to **http://127.0.0.1:8000/surveillance/live/** to view the live gate feed in the web dashboard, test image uploads, and view real-time sightings.

### Option B: CLI Surveillance Daemon
To run the computer-vision ingestion pipeline as a standalone background command:
```bash
# Run on default local webcam 0
python manage.py run_surveillance --camera 0 --location "Main Gate - Turnstile 1"

# Run on a video file (e.g. CCTV recorded footage)
python manage.py run_surveillance --camera "path/to/cctv_sample.mp4" --location "North Gate"

# Run in headless mode (for headless Linux/cloud servers)
python manage.py run_surveillance --camera 0 --headless
```

---

## 📡 REST API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/students/` | List all suspended students (filter by `?status=active`) |
| `GET` | `/api/detections/` | Filter detection audit logs by camera, student, date |
| `GET` | `/api/queues/high-confidence/` | Real-time high-confidence items awaiting sign-off |
| `GET` | `/api/queues/low-confidence/` | Low-confidence review items |
| `POST` | `/api/detections/<id>/verify/` | Verify match & dispatch email alert |
| `POST` | `/api/detections/<id>/reject/` | Mark detection as False Positive / Rejected |
| `GET` | `/api/stats/` | System-wide statistics for live widgets & telemetry |

---

## 🧪 Running Automated Tests
```bash
python manage.py test
```
Runs 9 comprehensive unit and integration tests verifying:
- Student models, expiry calculation, and embedding vectors
- Cosine similarity matching, threshold tiers (>85%, 70-85%, <70%), and deduplication cooldowns
- Alert mailer formatting, snapshot attachments, and status updates
- REST API queue actions and statistics calculation
