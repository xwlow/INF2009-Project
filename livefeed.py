import cv2
from ultralytics import YOLO

# --- CONFIGURATION ---
# 1. Load the Standard Detector (Finds the car)
detector = YOLO('yolov8n.pt') 

# 2. Load YOUR Custom Classifier (Identifies the brand)
# Replace this path with your actual trained model path
classifier = YOLO('runs/classify/train4/weights/best.pt')

# 3. Open the Camera (Use '0' for webcam, or a URL for IP Camera/RTSP)
cap = cv2.VideoCapture(0) 
# For a video file, use: cap = cv2.VideoCapture("traffic_video.mp4")

# Optimization: Only classify valid objects (e.g., Car=2, Truck=7 in COCO)
TARGET_CLASSES = [2, 7] 

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # --- STEP 1: DETECTION ---
    # Run the detector on the full frame
    # stream=True is faster for video as it doesn't accumulate memory
    detect_results = detector(frame, stream=True)

    for result in detect_results:
        for box in result.boxes:
            # Check if the detected object is a Car/Truck
            class_id = int(box.cls[0])
            
            if class_id in TARGET_CLASSES:
                # --- STEP 2: PREPARE COORDINATES ---
                # Get the bounding box coordinates
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                
                # Ensure coordinates stay within the image boundaries
                h, w, _ = frame.shape
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                # --- STEP 3: CROP & CLASSIFY ---
                # Cut out the car from the image
                car_crop = frame[y1:y2, x1:x2]

                # Safety check: ensure crop is not empty
                if car_crop.size > 0:
                    # Run your custom classifier on just this small crop
                    classify_results = classifier(car_crop, verbose=False)
                    
                    # Get the top prediction
                    top_result = classify_results[0].probs
                    class_name = classify_results[0].names[top_result.top1]
                    confidence = top_result.top1conf.item()

                    # --- STEP 4: VISUALIZE ---
                    # Draw Box
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    
                    # Draw Label (e.g., "Toyota 95%")
                    label = f"{class_name} {confidence:.0%}"
                    cv2.putText(frame, label, (x1, y1 - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    # Show the live feed
    cv2.imshow('Live Car Recognizer', frame)

    # Press 'q' to quit
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()