import cv2
import time
import csv
import os
import joblib
import numpy as np
from ultralytics import YOLO
import paho.mqtt.client as mqtt
import json
from flask import Flask, Response, render_template_string
import threading

# --- 1. CONFIGURATION ---
LOG_FILE = 'sentry_behavior_database.csv'
HUMAN_MODEL = 'human_risk_model.joblib'
VEHICLE_MODEL = 'vehicle_risk_model.joblib'
TARGET_CLASSES = [0, 2, 7]  # 0=Person, 2=Car, 7=Truck
ALERT_THRESHOLD = 240       # Seconds before triggering brand classifier
CAMERA_LOCATION = "Front Gate"
LAPTOP_IP = "172.20.10.2"   # Your WSL/Windows Host IP

# --- 2. INITIALIZATION ---
# Using OpenVINO versions for Pi 5 performance
detector = YOLO('yolo26n_openvino_model/') 
classifier = YOLO('runs/classify/train3/weights/best_openvino_model/') 
cap = cv2.VideoCapture(0)

# Set Resolution to 640x480 for a balance of speed and brand detail
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# --- 3. MQTT SETUP ---
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
try:
    mqtt_client.connect(LAPTOP_IP, 1883, 60)
    mqtt_client.loop_start() # Background thread for networking
    print(f"📡 MQTT Connected to {LAPTOP_IP}")
except Exception as e:
    print(f"⚠️ MQTT Offline: {e}")

# --- 4. DATABASE & MODEL LOADING ---
models = {}
if os.path.exists(HUMAN_MODEL):
    models[0] = joblib.load(HUMAN_MODEL)
if os.path.exists(VEHICLE_MODEL):
    v_model = joblib.load(VEHICLE_MODEL)
    models[2] = v_model
    models[7] = v_model

if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['duration', 'cx', 'cy', 'area', 'class_id', 'timestamp'])

# Tracking dictionaries
loitering_times = {}
max_stats = {} 
notified_ids = set()
prev_time = 0

print("🛡️ SENTRY ACTIVE: Monitoring Multi-Class Risks...")

# # Global variable to hold the latest frame
# output_frame = None
# lock = threading.Lock()

# app = Flask(__name__)

# def generate():
#     global output_frame, lock
#     while True:
#         with lock:
#             if output_frame is None:
#                 continue
#             # Encode the frame as JPEG
#             (flag, encodedImage) = cv2.imencode(".jpg", output_frame)
#             if not flag:
#                 continue
#         # Yield the output frame in the byte format required for MJPEG
#         yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 
#               bytearray(encodedImage) + b'\r\n')

# @app.route("/video_feed")
# def video_feed():
#     return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

# # Start the Flask server in a separate thread so it doesn't block the AI
# def start_web_server():
#     app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, use_reloader=False)

# threading.Thread(target=start_web_server, daemon=True).start()

# --- 5. MAIN PROCESSING LOOP ---
while True:
    ret, frame = cap.read()
    if not ret: break
    h, w, _ = frame.shape
    
    # Calculate FPS
    curr_time = time.time()
    fps = 1 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 0
    prev_time = curr_time

    # STEP 1: DETECTION & TRACKING
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

                # STEP 2: RISK INFERENCE (Isolation Forest)
                risk_level = "NORMAL"
                color = (0, 255, 0) # Default Green
                
                feat_array = np.array([[stay_duration, cx, cy, area]])
                if cls_idx in models:
                    prediction = models[cls_idx].predict(feat_array)[0]
                    if prediction == -1:
                        risk_level = "HIGH RISK"
                        color = (0, 0, 255) # Red

                # STEP 3: BRAND CLASSIFICATION (Vehicles only)
                brand = "Person" if cls_idx == 0 else "Unknown"
                
                # If it's a vehicle and loitering or high risk, trigger classifier
                if cls_idx in [2, 7] and (stay_duration >= ALERT_THRESHOLD or risk_level == "HIGH RISK"):
                    car_crop = frame[y1:y2, x1:x2]
                    if car_crop.size > 0:
                        cls_res = classifier(car_crop, verbose=False)
                        brand = cls_res[0].names[cls_res[0].probs.top1]
                        
                        if brand == "police_car":
                            risk_level = "WHITELISTED"
                            color = (255, 0, 0) # Blue

                # STEP 4: MQTT ALERTING (Consolidated)
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
                    print(f"🚀 CLOUD ALERT: ID {track_id} ({brand})")

                # STEP 5: VISUALIZATION
                label = f"ID:{track_id} {risk_level} ({brand})"
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, label, (x1, y1 - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                
                # After all visualization is done:
    
    # cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    # with lock:
    #     output_frame = frame.copy()

    # STEP 6: DATA LOGGING & CLEANUP
    for tid in list(loitering_times.keys()):
        if tid not in active_ids:
            # Save session to CSV
            with open(LOG_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(max_stats[tid] + [time.strftime("%Y-%m-%d %H:%M:%S")])
            
            # Clean up memory
            if tid in notified_ids: notified_ids.remove(tid)
            del loitering_times[tid]
            del max_stats[tid]

    # UI Overlays
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.imshow('Smart Sentry Pro (Full Integrated)', frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'): break

# --- 6. SHUTDOWN ---
mqtt_client.loop_stop()
cap.release()
cv2.destroyAllWindows()