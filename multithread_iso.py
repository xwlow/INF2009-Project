import cv2
import time
import csv
import os
import joblib
import numpy as np
from ultralytics import YOLO
import paho.mqtt.client as mqtt
import json
import threading

# --- 1. CONFIGURATION ---
LOG_FILE = 'sentry_behavior_database.csv'
HUMAN_MODEL = 'human_risk_model.joblib'
VEHICLE_MODEL = 'vehicle_risk_model.joblib'
TARGET_CLASSES = [0, 2, 7]  # 0=Person, 2=Car, 7=Truck
ALERT_THRESHOLD = 240       # Seconds
CAMERA_LOCATION = "Front Gate"
LAPTOP_IP = "172.20.10.2"   
SKIP_FRAMES = 1             # Run AI every 2nd frame to double FPS

# --- 2. THREADED CAMERA CLASS (The Performance Secret) ---
class VideoStream:
    def __init__(self, src=0):
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.ret, self.frame = self.cap.read()
        self.stopped = False

    def start(self):
        threading.Thread(target=self.update, args=(), daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            self.ret, self.frame = self.cap.read()

    def read(self):
        return self.frame

    def stop(self):
        self.stopped = True
        self.cap.release()

# --- 3. INITIALIZATION ---
# Load models using OpenVINO for Pi 5 optimization
detector = YOLO('yolo26n_openvino_model/') 
classifier = YOLO('runs/classify/train3/weights/best_openvino_model/') 
vs = VideoStream(0).start()

# MQTT SETUP
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
try:
    mqtt_client.connect(LAPTOP_IP, 1883, 60)
    mqtt_client.loop_start() 
    print(f"📡 MQTT Connected to {LAPTOP_IP}")
except Exception as e:
    print(f"⚠️ MQTT Offline: {e}")

# Load Models & Setup CSV
models = {}
if os.path.exists(HUMAN_MODEL): models[0] = joblib.load(HUMAN_MODEL)
if os.path.exists(VEHICLE_MODEL):
    v_model = joblib.load(VEHICLE_MODEL)
    models[2], models[7] = v_model, v_model

if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['duration', 'cx', 'cy', 'area', 'class_id', 'timestamp'])

# Tracking vars
loitering_times, max_stats = {}, {}
notified_ids = set()
prev_time, frame_count = 0, 0

print("🛡️ SENTRY ACTIVE: Monitoring Multi-Class Risks (Threaded)...")

# --- 4. MAIN PROCESSING LOOP ---
try:
    while True:
        frame = vs.read()
        if frame is None: break
        
        frame_count += 1
        h, w, _ = frame.shape
        
        # Calculate FPS
        curr_time = time.time()
        fps = 1 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 0
        prev_time = curr_time

        # --- PERFORMANCE HACK: SKIP FRAMES ---
        # We only run heavy detection every N frames. The tracker persists between calls.
        if frame_count % SKIP_FRAMES == 0:
            results = detector.track(frame, imgsz=640, persist=True, tracker="bytetrack.yaml", verbose=False)
            active_ids = []

            if results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.int().cpu().tolist()
                class_ids = results[0].boxes.cls.int().cpu().tolist()
                track_ids = results[0].boxes.id.int().cpu().tolist()

                for box, cls_idx, track_id in zip(boxes, class_ids, track_ids):
                    if cls_idx in TARGET_CLASSES:
                        active_ids.append(track_id)
                        
                        if track_id not in loitering_times:
                            loitering_times[track_id] = time.time()
                        
                        # Feature Extraction
                        stay_duration = time.time() - loitering_times[track_id]
                        x1, y1, x2, y2 = box
                        cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
                        area = ((x2 - x1) * (y2 - y1)) / (h * w)
                        max_stats[track_id] = [stay_duration, cx, cy, area, cls_idx]

                        # RISK INFERENCE
                        risk_level, color = "NORMAL", (0, 255, 0)
                        feat_array = np.array([[stay_duration, cx, cy, area]])
                        
                        if cls_idx in models:
                            prediction = models[cls_idx].predict(feat_array)[0]
                            if prediction == -1:
                                risk_level, color = "HIGH RISK", (0, 0, 255)

                        # CLASSIFICATION (Police/Whitelisting)
                        brand = "Person" if cls_idx == 0 else "Unknown"
                        if cls_idx in [2, 7] and (stay_duration >= ALERT_THRESHOLD or risk_level == "HIGH RISK"):
                            car_crop = frame[y1:y2, x1:x2]
                            if car_crop.size > 0:
                                cls_res = classifier(car_crop, verbose=False)
                                brand = cls_res[0].names[cls_res[0].probs.top1]
                                if brand == "police_car":
                                    risk_level, color = "WHITELISTED", (255, 0, 0)

                        # MQTT ALERTING
                        if track_id not in notified_ids and risk_level == "HIGH RISK":
                            payload = {
                                "timestamp": time.strftime("%H:%M:%S"),
                                "track_id": track_id,
                                "type": "HUMAN" if cls_idx == 0 else "VEHICLE",
                                "label": brand,
                                "risk": risk_level,
                                "duration": round(stay_duration, 1),
                                "location": CAMERA_LOCATION
                            }
                            mqtt_client.publish("sentry/alerts", json.dumps(payload))
                            notified_ids.add(track_id)

                        # VISUALIZATION
                        label = f"ID:{track_id} {risk_level} ({brand})"
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # DATA LOGGING CLEANUP (When IDs disappear)
            for tid in list(loitering_times.keys()):
                if tid not in active_ids:
                    with open(LOG_FILE, 'a', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(max_stats[tid] + [time.strftime("%Y-%m-%d %H:%M:%S")])
                    if tid in notified_ids: notified_ids.remove(tid)
                    del loitering_times[tid]
                    del max_stats[tid]

        # UI Overlay
        cv2.putText(frame, f"SENTRY FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imshow('Smart Sentry Pro (Multi-Threaded)', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

except KeyboardInterrupt:
    print("Shutting down Sentry...")

finally:
    vs.stop()
    mqtt_client.loop_stop()
    cv2.destroyAllWindows()