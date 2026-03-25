import cv2
import time
import os
import joblib
import numpy as np
import base64
import json
import threading
from ultralytics import YOLO
import paho.mqtt.client as mqtt

# --- 1. CONFIGURATION ---
HUMAN_MODEL = 'human_risk_model.joblib'
VEHICLE_MODEL = 'vehicle_risk_model.joblib'
TARGET_CLASSES = [0, 2, 7] 
LAPTOP_IP = "172.20.10.2"   # Replace with your current Laptop/Broker IP
SEND_INTERVAL = 10.0        # ⏱️ Send image/metadata every 10 seconds
FORGET_THRESHOLD = 60.0     # 🧠 Remember vehicles for 60 seconds after they leave

RED, GREEN, YELLOW, RESET = "\033[91m", "\033[92m", "\033[93m", "\033[0m"

# --- 2. THREADED CAMERA ---
class VideoStream:
    def __init__(self, src=0):
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
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
print("⚙️ Initializing YOLO & Brand Classifier (OpenVINO)...")
detector = YOLO('yolo26n_openvino_model/') 
classifier = YOLO('runs/classify/train3/weights/best_openvino_model/') 
vs = VideoStream(0).start()

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
try:
    mqtt_client.connect(LAPTOP_IP, 1883, 60)
    mqtt_client.loop_start() 
    print(f"📡 MQTT Connected to {LAPTOP_IP}")
except Exception as e:
    print(f"⚠️ MQTT Offline: {e}")

models = {}
if os.path.exists(HUMAN_MODEL): models[0] = joblib.load(HUMAN_MODEL)
if os.path.exists(VEHICLE_MODEL):
    v_model = joblib.load(VEHICLE_MODEL)
    models[2], models[7] = v_model, v_model

# State Management Vars
loitering_times = {}
last_seen_times = {}
notified_ids = set()
last_send_time = 0
prev_frame_time = 0
actual_scene_risk = 0.0

print(f"🛡️ SENTRY ACTIVE: Image Interval = {SEND_INTERVAL}s | Memory = {FORGET_THRESHOLD}s")

# --- 4. MAIN LOOP ---
try:
    while True:
        frame = vs.read()
        if frame is None: continue
        
        current_time = time.time()
        delta_time = current_time - prev_frame_time if prev_frame_time > 0 else 0.0
        fps = 1.0 / delta_time if delta_time > 0 else 0.0
        prev_frame_time = current_time
        h, w, _ = frame.shape
        
        results = detector.track(frame, imgsz=640, persist=True, tracker="bytetrack.yaml", verbose=False)
        active_ids, active_objects_data = [], []
        high_risk_count, target_risk = 0, 0.0

        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.int().cpu().tolist()
            class_ids = results[0].boxes.cls.int().cpu().tolist()
            track_ids = results[0].boxes.id.int().cpu().tolist()

            for box, cls_idx, track_id in zip(boxes, class_ids, track_ids):
                if cls_idx in TARGET_CLASSES:
                    active_ids.append(track_id)
                    
                    # 🧠 PERSISTENCE LOGIC: Start or Resume Timer
                    if track_id not in loitering_times:
                        loitering_times[track_id] = time.time()
                    
                    # Update Last Seen Time
                    last_seen_times[track_id] = time.time()
                    
                    stay_duration = time.time() - loitering_times[track_id]
                    x1, y1, x2, y2 = box
                    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
                    area = ((x2 - x1) * (y2 - y1)) / (h * w)

                    # 1. INDIVIDUAL RISK (Behavioral)
                    risk_level, color = "NORMAL", (0, 255, 0)
                    if cls_idx in models:
                        if models[cls_idx].predict([[stay_duration, cx, cy, area]])[0] == -1:
                            risk_level, color = "HIGH RISK", (0, 0, 255)

                    # 2. BRAND CLASSIFICATION & WHITELISTING
                    current_brand = "Human" if cls_idx == 0 else "Vehicle"
                    if cls_idx in [2, 7]: 
                        car_crop = frame[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]
                        if car_crop.size > 0:
                            cls_res = classifier(car_crop, verbose=False)
                            current_brand = cls_res[0].names[cls_res[0].probs.top1]
                            if current_brand == "police_car":
                                risk_level, color = "WHITELISTED", (255, 191, 0)

                    if risk_level == "HIGH RISK": 
                        high_risk_count += 1

                    # 3. CONSOLIDATE OBJECT DATA
                    active_objects_data.append({
                        "track_id": track_id,
                        "type": "HUMAN" if cls_idx == 0 else "VEHICLE",
                        "brand": current_brand, 
                        "individual_risk": risk_level,
                        "duration": round(stay_duration, 1)
                    })
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            target_risk = min(100.0, (high_risk_count * 35.0) + (len(active_ids) * 5.0))

        # Risk Smoothing
        if target_risk > actual_scene_risk: actual_scene_risk = target_risk
        else: actual_scene_risk = max(target_risk, actual_scene_risk - (10.0 * delta_time))

        # --- 5. SMART CLEANUP (Temporal Memory) ---
        for tid in list(loitering_times.keys()):
            if tid not in active_ids:
                # Car is gone. Check if we should forget it yet.
                time_since_seen = current_time - last_seen_times.get(tid, 0)
                if time_since_seen > FORGET_THRESHOLD:
                    del loitering_times[tid]
                    if tid in last_seen_times: del last_seen_times[tid]
                    if tid in notified_ids: notified_ids.remove(tid)

        # --- 6. MQTT UPLOAD (10s Interval OR New Threat) ---
        new_threat = False
        for obj in active_objects_data:
            if obj["individual_risk"] == "HIGH RISK" and obj["track_id"] not in notified_ids:
                new_threat = True
                notified_ids.add(obj["track_id"])

        if (current_time - last_send_time) >= SEND_INTERVAL or new_threat:
            _, buffer = cv2.imencode('.jpg', frame)
            img_str = base64.b64encode(buffer).decode('utf-8')
            payload = {
                "timestamp": time.strftime("%H:%M:%S"),
                "scene_risk_score": round(actual_scene_risk, 1), 
                "active_threats": high_risk_count,              
                "objects": active_objects_data,
                "image": img_str
            }
            mqtt_client.publish("sentry/alerts", json.dumps(payload))
            last_send_time = current_time

        if actual_scene_risk >= 80 or high_risk_count >= 3:
            scene_color, risk_status = RED, "CRITICAL THREAT"
        elif actual_scene_risk >= 40 or high_risk_count >= 1:
            scene_color, risk_status = YELLOW, "ELEVATED WARNING"
        else:
            scene_color, risk_status = GREEN, "SECURE"
        cv2.putText(frame, f"RISK: {actual_scene_risk:.1f} FPS: {int(fps)} AREA RISK LEVEL: {risk_status}", (10, 20), 1, 1, (255, 255, 255), 2)
        cv2.imshow('Pi Sentry', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
finally:
    vs.stop()
    cv2.destroyAllWindows()