import cv2
import time
from ultralytics import YOLO

# 1. Load Models
detector = YOLO('yolo26n.pt')  # Standard Detector
classifier = YOLO('runs/classify/train3/weights/best.pt')  # Your Custom Model

cap = cv2.VideoCapture(0)

# 2. Tracking & Loitering Config
TARGET_CLASSES = [0, 2, 7]  # COCO indices for Car and Truck
loitering_times = {}     # {track_id: start_time}
ALERT_THRESHOLD = 3     # Seconds before a vehicle is "suspicious"

while True:
    ret, frame = cap.read()
    if not ret: break

    # --- STEP 1: DETECTION & TRACKING ---
    # use persist=True to keep IDs consistent across frames
    results = detector.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False)

    if results[0].boxes.id is not None:
        boxes = results[0].boxes.xyxy.int().cpu().tolist()
        class_ids = results[0].boxes.cls.int().cpu().tolist()
        track_ids = results[0].boxes.id.int().cpu().tolist()

        for box, cls_idx, track_id in zip(boxes, class_ids, track_ids):
            # Only process if it's a Car or Truck
            if cls_idx in TARGET_CLASSES and TARGET_CLASSES:
                # --- STEP 2: LOITERING LOGIC ---
                if track_id not in loitering_times:
                    loitering_times[track_id] = time.time()
                
                stay_duration = time.time() - loitering_times[track_id]
                
                # --- STEP 3: TRIGGERED CLASSIFICATION ---
                # Only classify if the car has stayed longer than our threshold
                if stay_duration >= ALERT_THRESHOLD:
                    x1, y1, x2, y2 = box
                    car_crop = frame[y1:y2, x1:x2]

                    if car_crop.size > 0 and TARGET_CLASSES.index(cls_idx) != 0: # Ensure we have a valid crop and it's not a bus
                        # Identify the car model using your custom classifier
                        cls_res = classifier(car_crop, verbose=False)
                        brand = cls_res[0].names[cls_res[0].probs.top1]
                        
                        if(brand == "police_car"):
                            label = f"WHITELISTED VEHICLE: {brand} ({stay_duration:.1f}s)"
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 3) # Blue for police
                            cv2.putText(frame, label, (x1, y1 - 10), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
                        else:
                            # Visualization
                            label = f"SUSPECT: {brand} ({stay_duration:.1f}s)"
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3) # Red for suspicious
                            cv2.putText(frame, label, (x1, y1 - 10), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                    elif car_crop.size > 0 and TARGET_CLASSES.index(cls_idx) == 0: # If it's a bus, we can also check for loitering without classification
                        # If no valid crop or classification, do nothing special
                        label = f"SUSPECT: LOITERING HUMAN DETECTED ({stay_duration:.1f}s)"
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3) # Red for suspicious
                        cv2.putText(frame, label, (x1, y1 - 10), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        
                    
                    continue # Skip normal drawing if already flagged

                # Normal Visualization for non-suspicious cars
                cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
                cv2.putText(frame, f"ID:{track_id} {stay_duration:.1f}s", (box[0], box[1]-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    cv2.imshow('Smart Sentry Node', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()