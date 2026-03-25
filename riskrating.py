import cv2
import time
import csv
import os
import joblib
import numpy as np
import base64
import json
import threading
from ultralytics import YOLO
import paho.mqtt.client as mqtt

# --- 1. CONFIGURATION ---
LOG_FILE = 'sentry_behavior_database.csv'
HUMAN_MODEL = 'human_risk_model.joblib'
VEHICLE_MODEL = 'vehicle_risk_model.joblib'
TARGET_CLASSES = [0, 2, 7]  # 0: Person, 2: Car, 7: Truck
ALERT_THRESHOLD = 240       # Loitering limit
CAMERA_LOCATION = "Front Gate"
LAPTOP_IP = "172.20.10.2"   
INTERVAL = 1.0              # Volume update frequency

# --- 2. THREADED CAMERA CLASS ---
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
print("⚙️ Initializing YOLO Models (OpenVINO)...")
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

# Load ML Risk Models
models = {}
print("⚙️ Loading ML Risk Models...")
if os.path.exists(HUMAN_MODEL): 
    models[0] = joblib.load(HUMAN_MODEL)
    print("   ✅ Human Model Loaded")
if os.path.exists(VEHICLE_MODEL):
    v_model = joblib.load(VEHICLE_MODEL)
    models[2], models[7] = v_model, v_model
    print("   ✅ Vehicle Model Loaded")

loitering_times, max_stats = {}, {}
notified_ids = set()
last_send_time = 0
prev_frame_time = 0
actual_scene_risk = 0.0

print("🛡️ SENTRY ACTIVE: Monitoring Multi-Class Risks...")

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
        
        # Detection & Tracking
        results = detector.track(frame, imgsz=640, persist=True, tracker="bytetrack.yaml", verbose=False)
        active_ids = []
        active_objects_data = []
        high_risk_count = 0
        target_risk = 0.0

        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.int().cpu().tolist()
            class_ids = results[0].boxes.cls.int().cpu().tolist()
            track_ids = results[0].boxes.id.int().cpu().tolist()

            for box, cls_idx, track_id in zip(boxes, class_ids, track_ids):
                if cls_idx in TARGET_CLASSES:
                    active_ids.append(track_id)
                    if track_id not in loitering_times: loitering_times[track_id] = time.time()
                    
                    stay_duration = time.time() - loitering_times[track_id]
                    x1, y1, x2, y2 = box
                    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
                    area = ((x2 - x1) * (y2 - y1)) / (h * w)

                    # --- STEP 1: BEHAVIOR RISK INFERENCE ---
                    risk_level, color = "NORMAL", (0, 255, 0)
                    feat_array = np.array([[stay_duration, cx, cy, area]])
                    if cls_idx in models:
                        prediction = models[cls_idx].predict(feat_array)[0]
                        if prediction == -1: risk_level, color = "HIGH RISK", (0, 0, 255)

                    # --- STEP 2: BRAND CLASSIFICATION & WHITELISTING ---
                    # Only run classifier for Vehicles (Car=2, Truck=7)
                    brand_label = "Human" if cls_idx == 0 else "Unknown Vehicle"
                    
                    if cls_idx in [2, 7]:
                        # Crop the vehicle from the frame
                        car_crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
                        if car_crop.size > 0:
                            # Run the OpenVINO Brand Classifier
                            cls_res = classifier(car_crop, verbose=False)
                            brand_label = cls_res[0].names[cls_res[0].probs.top1]

                            # Whitelist Logic
                            if brand_label == "police_car":
                                risk_level = "WHITELISTED"
                                color = (255, 191, 0) # Deep Blue
                            elif risk_level == "HIGH RISK":
                                high_risk_count += 1

                    # --- STEP 3: PREPARE PAYLOAD ---
                    active_objects_data.append({
                        "track_id": track_id,
                        "type": "HUMAN" if cls_idx == 0 else "VEHICLE",
                        "label": brand_label,
                        "individual_risk": risk_level,
                        "duration": round(stay_duration, 1)
                    })

                    # VISUALIZATION
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, f"ID:{track_id} {brand_label}", (x1, y1 - 5), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 2)

            # Update Scene Risk Score
            target_risk = (high_risk_count * 30.0) + (len(active_ids) * 5.0)
            target_risk = min(target_risk, 100.0)

        # Scene Risk Smoothing (Memory Engine)
        if target_risk > actual_scene_risk:
            actual_scene_risk = target_risk
        else:
            actual_scene_risk = max(target_risk, actual_scene_risk - (5.0 * delta_time))

        # --- 5. MQTT TRANSPORT ---
        if (current_time - last_send_time) >= INTERVAL or high_risk_count > 0:
            _, buffer = cv2.imencode('.jpg', frame)
            img_str = base64.b64encode(buffer).decode('utf-8')

            payload = {
                "timestamp": time.strftime("%H:%M:%S"),
                "location": CAMERA_LOCATION,
                "scene_risk_score": round(actual_scene_risk, 1),
                "active_threats": high_risk_count,
                "objects": active_objects_data,
                "image": img_str
            }
            mqtt_client.publish("sentry/alerts", json.dumps(payload))
            last_send_time = current_time

        # HUD Overlay
        cv2.putText(frame, f"RISK: {actual_scene_risk:.1f} FPS: {int(fps)}", (10, 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        cv2.imshow('Pi Sentry Causeway', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

except KeyboardInterrupt:
    print("\n🛑 Shutting down Sentry...")
finally:
    vs.stop()
    mqtt_client.loop_stop()
    cv2.destroyAllWindows()