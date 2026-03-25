import time

import cv2
from ultralytics import YOLO


CAMERA_INDEX = 0
WINDOW_NAME = "Back Camera Live Feed"
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
TARGET_CLASSES = {0: "Person", 2: "Car", 7: "Truck"}
HUMAN_LOITER_SECONDS = 10
VEHICLE_LOITER_SECONDS = 5
TRACK_FORGET_SECONDS = 2
DETECTION_IMAGE_SIZE = 640


def load_detector():
    for model_path in ("yolo26n_openvino_model/", "yolo26n.pt"):
        try:
            detector = YOLO(model_path)
            image_size = 320 if "openvino" in model_path.lower() else DETECTION_IMAGE_SIZE
            return detector, image_size
        except Exception:
            continue

    raise RuntimeError("Unable to load a YOLO detector from yolo26n_openvino_model/ or yolo26n.pt.")


def open_camera():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not cap.isOpened():
        raise RuntimeError("Unable to open camera.")

    return cap


def get_suspicion_rule(class_id, stay_duration):
    if class_id == 0 and stay_duration >= HUMAN_LOITER_SECONDS:
        return "LOITERING HUMAN"

    if class_id in (2, 7) and stay_duration >= VEHICLE_LOITER_SECONDS:
        return "LOITERING VEHICLE"

    return None


def annotate_detections(frame, detector, image_size, loitering_times, last_seen_times):
    current_time = time.time()
    results = detector.track(
        frame,
        imgsz=image_size,
        conf=0.25,
        persist=True,
        tracker="bytetrack.yaml",
        verbose=False,
    )
    active_ids = set()
    suspicious_count = 0

    if not results or results[0].boxes is None:
        for track_id in list(last_seen_times.keys()):
            if current_time - last_seen_times[track_id] > TRACK_FORGET_SECONDS:
                last_seen_times.pop(track_id, None)
                loitering_times.pop(track_id, None)
        return frame, 0

    boxes = results[0].boxes.xyxy.int().cpu().tolist()
    class_ids = results[0].boxes.cls.int().cpu().tolist()
    if results[0].boxes.id is not None:
        track_ids = results[0].boxes.id.int().cpu().tolist()
    else:
        track_ids = [None] * len(boxes)

    for box, class_id, track_id in zip(boxes, class_ids, track_ids):
        if class_id not in TARGET_CLASSES:
            continue

        is_tracked = track_id is not None
        stay_duration = 0.0
        if is_tracked:
            active_ids.add(track_id)
            if track_id not in loitering_times:
                loitering_times[track_id] = current_time
            last_seen_times[track_id] = current_time
            stay_duration = current_time - loitering_times[track_id]

        suspicion_rule = get_suspicion_rule(class_id, stay_duration)
        x1, y1, x2, y2 = box
        color = (0, 255, 0)
        label = TARGET_CLASSES[class_id]

        if is_tracked:
            label = f"{label} ID:{track_id} {stay_duration:.1f}s"

        if is_tracked and suspicion_rule is not None:
            suspicious_count += 1
            color = (0, 0, 255)
            label = f"SUSPECT: {suspicion_rule} ID:{track_id} {stay_duration:.1f}s"

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            label,
            (x1, max(y1 - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
        )

    for track_id in list(last_seen_times.keys()):
        if track_id not in active_ids and current_time - last_seen_times[track_id] > TRACK_FORGET_SECONDS:
            last_seen_times.pop(track_id, None)
            loitering_times.pop(track_id, None)

    return frame, suspicious_count


def main():
    detector, image_size = load_detector()
    cap = open_camera()
    loitering_times = {}
    last_seen_times = {}

    print("Camera started. Press 'q' in the video window to stop.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Camera frame read failed. Retrying...")
                time.sleep(0.1)
                continue

            frame, suspicious_count = annotate_detections(
                frame,
                detector,
                image_size,
                loitering_times,
                last_seen_times,
            )

            if suspicious_count >= 3:
                scene_status = "CRITICAL THREAT"
                scene_color = (0, 0, 255)
            elif suspicious_count >= 1:
                scene_status = "ELEVATED WARNING"
                scene_color = (0, 255, 255)
            else:
                scene_status = "SECURE"
                scene_color = (0, 255, 0)

            frame_width = frame.shape[1]
            cv2.rectangle(frame, (0, 0), (frame_width, 45), (0, 0, 0), -1)
            cv2.putText(frame, f"SUSPICIOUS TRACKS: {suspicious_count}", (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(frame, f"STATUS: {scene_status}", (10, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.6, scene_color, 2)
            cv2.imshow(WINDOW_NAME, frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
