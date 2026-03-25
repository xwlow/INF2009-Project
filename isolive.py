import cv2
import time
import csv
import os
import joblib
import numpy as np
from ultralytics import YOLO

# --- 1. CONFIGURATION ---
MQTT_ENABLED = False  # Set to True once you've set up your broker
LOG_FILE = 'sentry_behavior_database.csv'
MODEL_PATH = 'risk_model.joblib'
TARGET_CLASSES = [0, 2, 7]  # Person, Car, Truck

# --- 2. INITIALIZATION ---
detector = YOLO('yolo26n.pt')
cap = cv2.VideoCapture(0)

# Load the "Brain" if it exists, otherwise start in "Learning Only" mode
if os.path.exists(MODEL_PATH):
    risk_engine = joblib.load(MODEL_PATH)
    MODE = "SENTRY"
    print("🛡️ SENTRY MODE: Model loaded. Monitoring for anomalies.")
else:
    MODE = "LEARNING"
    print("🔴 LEARNING MODE: No model found. Logging data to build baseline.")

# Prepare CSV Header
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['duration', 'cx', 'cy', 'area', 'class_id', 'timestamp'])

# Tracking dictionaries
loitering_times = {}
prev_positions = {}
max_durations = {} # Store max duration reached by an ID before it left

while True:
    ret, frame = cap.read()
    if not ret: break
    h, w, _ = frame.shape

    # --- STEP 1: DETECTION & TRACKING ---
    results = detector.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False)

    active_ids_this_frame = []

    if results[0].boxes.id is not None:
        boxes = results[0].boxes.xyxy.int().cpu().tolist()
        class_ids = results[0].boxes.cls.int().cpu().tolist()
        track_ids = results[0].boxes.id.int().cpu().tolist()

        for box, cls_idx, track_id in zip(boxes, class_ids, track_ids):
            if cls_idx in TARGET_CLASSES:
                active_ids_this_frame.append(track_id)
                
                # Initialize tracking for new IDs
                if track_id not in loitering_times:
                    loitering_times[track_id] = time.time()
                
                # Calculate Features
                stay_duration = time.time() - loitering_times[track_id]
                x1, y1, x2, y2 = box
                cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
                area = ((x2 - x1) * (y2 - y1)) / (h * w)
                
                max_durations[track_id] = [stay_duration, cx, cy, area, cls_idx]

                # --- STEP 2: REAL-TIME RISK INFERENCE ---
                risk_level = "PENDING"
                color = (255, 255, 0) # Cyan for pending

                if MODE == "SENTRY":
                    # Predict using the 4 features: [duration, cx, cy, area]
                    
                    features = np.array([[stay_duration, cx, cy, area]])
                    prediction = risk_engine.predict(features)[0]
                    
                    if prediction == -1:
                        risk_level = "HIGH RISK"
                        color = (0, 0, 255) # Red
                    else:
                        risk_level = "NORMAL"
                        color = (0, 255, 0) # Green

                # --- STEP 3: VISUALIZATION ---
                label = f"ID:{track_id} {risk_level} ({stay_duration:.1f}s)"
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, label, (x1, y1 - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    # --- STEP 4: ASYCHRONOUS DATA LOGGING ---
    # Check for IDs that have left the frame to log their final behavior
    all_tracked_ids = list(loitering_times.keys())
    for tid in all_tracked_ids:
        if tid not in active_ids_this_frame:
            # The object has left! Log its most 'mature' data point
            data = max_durations[tid]
            with open(LOG_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(data + [time.strftime("%Y-%m-%d %H:%M:%S")])
            
            # Clean up memory
            del loitering_times[tid]
            del max_durations[tid]
            print(f"📁 Logged final data for ID {tid} to database.")

    cv2.imshow('Smart Sentry: Detection + Recording', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()