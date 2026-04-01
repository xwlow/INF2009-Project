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
from pathlib import Path
import csv

# --- 1. CONFIGURATION ---
HUMAN_MODEL = 'human_risk_model.joblib'
VEHICLE_MODEL = 'vehicle_risk_model.joblib'
TARGET_CLASSES = [0, 2, 7] 
LAPTOP_IP = "192.168.10.1" 
SEND_INTERVAL = 0.30        
FORGET_THRESHOLD = 60.0     
SUSPICIOUS_THRESHOLD = 5.0  
WATCHDOG_TIMEOUT = 60.0  # ⏱️ Silence duration before takeover

# --- 2. FAILOVER WATCHDOG LOGIC ---
failover_active = False
last_heartbeat = time.time()

def on_heartbeat(client, userdata, msg):
    global last_heartbeat, failover_active
    # Reset timer whenever we hear the Main Pi talking
    last_heartbeat = time.time()
    
    # If Backup was active, STEP DOWN immediately when Main Pi returns
    if failover_active:
        print("\n👑 Main Pi detected! Backup Pi returning to Standby...")
        failover_active = False

def check_failover():
    global failover_active
    print("🕵️ WATCHDOG ACTIVE: Monitoring Main Pi heartbeat...")
    while True:
        elapsed = time.time() - last_heartbeat
        
        # Trigger Takeover
        if not failover_active and elapsed > WATCHDOG_TIMEOUT:
            print("\n🚨 SILENCE DETECTED. Backup Pi taking over NOW.")
            failover_active = True
        
        # UI Status for Terminal
        if not failover_active:
            print(f"💤 Standby... {max(0, WATCHDOG_TIMEOUT - elapsed):.1f}s until failover", end='\r')
        else:
            print(f"🚀 ACTIVE MODE | Monitoring for Main Pi return...        ", end='\r')
            
        time.sleep(1)

# --- 3. THREADED CAMERA ---
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

# --- 4. INITIALIZATION ---
print("⚙️ Initializing YOLO & Escalated Brand Classifier...")
BASE_DIR = Path(__file__).resolve().parent
detector = YOLO('yolo26n_openvino_model/', task="detect") 
classifier = YOLO('runs/classify/train4/weights/best_openvino_model/', task="classify")
vs = VideoStream(0).start()

cv2.namedWindow("Pi Sentry", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Pi Sentry", 640, 480)

# Main MQTT Client (For Sending)
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

# Watchdog MQTT Client (For Listening to Main Pi)
heartbeat_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
heartbeat_client.on_message = on_heartbeat

try:
    mqtt_client.connect(LAPTOP_IP, 1883, 60)
    mqtt_client.loop_start()
    
    heartbeat_client.connect(LAPTOP_IP, 1883, 60)
    heartbeat_client.subscribe("sentry/alerts") 
    heartbeat_client.loop_start()
    
    print(f"📡 MQTT Connected to {LAPTOP_IP}")
except Exception as e:
    print(f"⚠️ MQTT Connection Error: {e}")

# Start the Failover monitoring thread
threading.Thread(target=check_failover, daemon=True).start()

models = {}
if os.path.exists(HUMAN_MODEL): models[0] = joblib.load(HUMAN_MODEL)
if os.path.exists(VEHICLE_MODEL):
    v_model = joblib.load(VEHICLE_MODEL)
    models[2], models[7] = v_model, v_model

loitering_times, last_seen_times, track_brands = {}, {}, {} 
notified_ids = set()
last_send_time, prev_frame_time, actual_scene_risk = 0, 0, 0.0

# CSV Setup
CSV_FILE = 'sentry_behavior_database.csv'
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        csv.writer(f).writerow(['duration', 'cx', 'cy', 'area', 'class_id', 'timestamp'])

frame_count = 0

# --- 5. MAIN LOOP ---
try:
    while True:
        # --- FAILOVER GATEKEEPER ---
        if not failover_active:
            # If the window is open, show a "Standby" message or just wait
            time.sleep(0.5) 
            continue
        
        frame = vs.read()
        if frame is None: continue
        
        current_time = time.time()
        delta_time = current_time - prev_frame_time if prev_frame_time > 0 else 0.0
        fps = 1.0 / delta_time if delta_time > 0 else 0.0
        prev_frame_time = current_time
        h, w, _ = frame.shape
        
        # Inference (imgsz 320 for performance)
        results = detector.track(frame, imgsz=320, persist=True, tracker="bytetrack.yaml", verbose=False)
        active_ids, active_objects_data = [], []
        high_risk_count, target_risk = 0, 0.0

        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.int().cpu().tolist()
            class_ids = results[0].boxes.cls.int().cpu().tolist()
            track_ids = results[0].boxes.id.int().cpu().tolist()

            for box, cls_idx, track_id in zip(boxes, class_ids, track_ids):
                if cls_idx in TARGET_CLASSES:
                    active_ids.append(track_id)
                    
                    if track_id not in loitering_times: loitering_times[track_id] = time.time()
                    last_seen_times[track_id] = time.time()
                    
                    stay_duration = time.time() - loitering_times[track_id]
                    x1, y1, x2, y2 = box
                    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
                    area = ((x2 - x1) * (y2 - y1)) / (h * w)

                    # Behavioral Risk logic
                    risk_level, color = "NORMAL", (0, 255, 0)
                    if cls_idx in models:
                        if models[cls_idx].predict([[stay_duration, cx, cy, area]])[0] == -1:
                            risk_level, color = "HIGH RISK", (0, 0, 255)

                    # Brand Classification Escalation
                    current_brand = "Human" if cls_idx == 0 else "Vehicle"
                    if cls_idx in [2, 7]:
                        if stay_duration > SUSPICIOUS_THRESHOLD or track_id in track_brands:
                            if track_id not in track_brands:
                                car_crop = frame[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]
                                if car_crop.size > 0:
                                    cls_res = classifier(car_crop, verbose=False)
                                    track_brands[track_id] = cls_res[0].names[cls_res[0].probs.top1]
                            current_brand = track_brands.get(track_id, "Vehicle")
                            if current_brand == "police_car":
                                risk_level, color = "WHITELISTED", (255, 191, 0)

                    if risk_level == "HIGH RISK": high_risk_count += 1

                    active_objects_data.append({
                        "track_id": track_id,
                        "type": "HUMAN" if cls_idx == 0 else "VEHICLE",
                        "brand": current_brand, 
                        "individual_risk": risk_level,
                        "duration": round(stay_duration, 1)
                    })
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, f"ID:{track_id} {current_brand}", (x1, y1 - 5), 1, 0.7, color, 1)

                    # Sampled CSV Logging
                    if frame_count % 5 == 0:
                        with open(CSV_FILE, mode='a', newline='') as f:
                            csv.writer(f).writerow([round(stay_duration, 4), round(cx, 4), round(cy, 4), round(area, 4), cls_idx, time.strftime("%Y-%m-%d %H:%M:%S")])
            
            target_risk = min(100.0, (high_risk_count * 35.0) + (len(active_ids) * 5.0))

        # Risk Smoothing
        if target_risk > actual_scene_risk: actual_scene_risk = target_risk
        else: actual_scene_risk = max(target_risk, actual_scene_risk - (10.0 * delta_time))

        # Cleanup loitering cache
        for tid in list(loitering_times.keys()):
            if tid not in active_ids:
                if (current_time - last_seen_times.get(tid, 0)) > FORGET_THRESHOLD:
                    del loitering_times[tid]
                    if tid in last_seen_times: del last_seen_times[tid]
                    if tid in notified_ids: notified_ids.remove(tid)
                    if tid in track_brands: del track_brands[tid]

        # HUD UI
        cv_color = (0, 0, 255) if actual_scene_risk >= 80 else (0, 255, 255) if actual_scene_risk >= 40 else (0, 255, 0)
        status = "CRITICAL" if actual_scene_risk >= 80 else "ELEVATED" if actual_scene_risk >= 40 else "SECURE"
        cv2.rectangle(frame, (0, 0), (w, 45), (0, 0, 0), -1) 
        cv2.putText(frame, f"RISK: {actual_scene_risk:.1f} | FPS: {int(fps)}", (10, 15), 1, 0.9, (255, 255, 255), 1)
        cv2.putText(frame, f"STATUS: {status}", (10, 35), 1, 0.9, cv_color, 1)

        # MQTT Publishing
        new_threat = any(obj["individual_risk"] == "HIGH RISK" and obj["track_id"] not in notified_ids for obj in active_objects_data)
        if (current_time - last_send_time) >= SEND_INTERVAL or new_threat:
            for obj in active_objects_data:
                if obj["individual_risk"] == "HIGH RISK": notified_ids.add(obj["track_id"])
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

        cv2.imshow('Pi Sentry', frame)
        frame_count += 1
        if cv2.waitKey(1) & 0xFF == ord('q'): break
finally:
    vs.stop()
    cv2.destroyAllWindows()
