"""
CampusGuard AI - Authorized Gate 1 Camera Node
Streams live video from your laptop camera to the CampusGuard AI Cloud Command Center.

Usage:
    python gate_camera_node.py
    python gate_camera_node.py --local        (streams to http://127.0.0.1:8000)
    python gate_camera_node.py --fps 5        (adjust streaming framerate)
"""

import os
import sys
import time
import argparse
from datetime import datetime
import cv2
import requests

def main():
    parser = argparse.ArgumentParser(description='CampusGuard AI - Authorized Gate Camera Node')
    parser.add_argument('--camera', default='0', help='Camera hardware index (default: 0)')
    parser.add_argument('--target', default='https://campusguard-ai.onrender.com/surveillance/node/push/',
                        help='Target server endpoint')
    parser.add_argument('--local', action='store_true', help='Push to local dev server (http://127.0.0.1:8000)')
    parser.add_argument('--fps', type=float, default=4.0, help='Stream frame rate (default: 4.0 FPS)')
    parser.add_argument('--location', default='Main Gate - Gate 1', help='Gate location name')
    parser.add_argument('--camera-id', default='CAM-01', help='Camera ID code')
    parser.add_argument('--no-preview', action='store_true', help='Disable local preview window')
    args = parser.parse_args()

    target_url = 'http://127.0.0.1:8000/surveillance/node/push/' if args.local else args.target
    cam_index = int(args.camera) if args.camera.isdigit() else args.camera

    print('=' * 68)
    print('  CAMPUSGUARD AI // AUTHORIZED GATE 1 CAMERA NODE')
    print('=' * 68)
    print(f'  Hardware Camera:  {cam_index}')
    print(f'  Gate Channel:     {args.location} ({args.camera_id})')
    print(f'  Target Endpoint:  {target_url}')
    print(f'  Stream Rate:      {args.fps} FPS')
    print('=' * 68)

    cap = cv2.VideoCapture(cam_index)
    if not cap.isOpened():
        print(f'[ERROR] Could not open camera {cam_index}. Check if another app is using your webcam.')
        return

    # Warm up camera
    for _ in range(5):
        cap.read()

    print('[INFO] Camera initialized successfully.')
    print(f'[INFO] Streaming live to: {target_url}')
    print("[INFO] Press 'q' on the preview window (or Ctrl+C in terminal) to stop.\n")

    frame_interval = 1.0 / max(1.0, args.fps)
    last_sent_time = 0.0
    frames_sent = 0

    session = requests.Session()

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            # Resize frame for optimal streaming balance (720x480)
            h, w = frame.shape[:2]
            target_w = 720
            target_h = int(h * (target_w / w))
            resized = cv2.resize(frame, (target_w, target_h))

            # HUD Overlay
            now_str = datetime.now().strftime('%Y-%m-%d  %H:%M:%S')
            cv2.rectangle(resized, (0, 0), (target_w, 28), (15, 23, 42), -1)
            cv2.circle(resized, (14, 14), 5, (0, 255, 0), -1)  # Green live dot
            cv2.putText(resized, f'GATE 1 CCTV // {args.camera_id} - {args.location}', (26, 19),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(resized, now_str, (target_w - 180, 19),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (148, 163, 184), 1, cv2.LINE_AA)

            # Local preview
            if not args.no_preview:
                cv2.imshow('CampusGuard AI - Gate 1 Camera Node (Laptop)', resized)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print('\n[INFO] User requested stop. Exiting...')
                    break

            # Send frame at requested interval
            current_time = time.time()
            if current_time - last_sent_time >= frame_interval:
                last_sent_time = current_time
                ret_enc, buffer = cv2.imencode('.jpg', resized, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                if ret_enc:
                    try:
                        resp = session.post(
                            target_url,
                            data=buffer.tobytes(),
                            headers={'Content-Type': 'image/jpeg'},
                            timeout=2.0
                        )
                        if resp.status_code == 200:
                            frames_sent += 1
                            if frames_sent % 20 == 0 or frames_sent == 1:
                                print(f'[LIVE] Streamed {frames_sent} frames to cloud | Server status: OK')
                        else:
                            print(f'[WARN] Server returned status: {resp.status_code}')
                    except requests.RequestException as e:
                        print(f'[WARN] Network push error: {e}')

    except KeyboardInterrupt:
        print('\n[INFO] Stopped by user.')
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(f'[INFO] Node shutdown. Total frames sent: {frames_sent}')

if __name__ == '__main__':
    main()
