import time

import cv2
from gpiozero import MotionSensor
from ultralytics import YOLO


PIR_PIN = 4
CAMERA_INDEX = 0
WINDOW_NAME = "Back Camera Live Feed"
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
MOTION_HOLD_SECONDS = 60
POLL_INTERVAL = 0.1
TARGET_CLASSES = {0: "Person", 2: "Car", 7: "Truck"}


def load_detector():
    for model_path in ("yolo26n_openvino_model/", "yolo26n.pt"):
        try:
            return YOLO(model_path)
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


def annotate_detections(frame, detector):
    results = detector.track(frame, imgsz=320, persist=True, tracker="bytetrack.yaml", verbose=False)

    if not results or results[0].boxes is None or results[0].boxes.id is None:
        return frame

    boxes = results[0].boxes.xyxy.int().cpu().tolist()
    class_ids = results[0].boxes.cls.int().cpu().tolist()
    track_ids = results[0].boxes.id.int().cpu().tolist()

    for box, class_id, track_id in zip(boxes, class_ids, track_ids):
        if class_id not in TARGET_CLASSES:
            continue

        x1, y1, x2, y2 = box
        label = f"{TARGET_CLASSES[class_id]} ID:{track_id}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            frame,
            label,
            (x1, max(y1 - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

    return frame


def main():
    detector = load_detector()
    pir = MotionSensor(PIR_PIN)
    cap = None
    motion_deadline = 0.0

    print("Watching for motion... Press 'q' in the video window to stop.")

    try:
        while True:
            now = time.time()

            if pir.motion_detected:
                motion_deadline = now + MOTION_HOLD_SECONDS

                if cap is None:
                    cap = open_camera()
                    print("Motion detected. Camera started.")

            if cap is not None:
                ret, frame = cap.read()
                if not ret:
                    print("Camera frame read failed. Retrying...")
                    time.sleep(POLL_INTERVAL)
                    continue

                frame = annotate_detections(frame, detector)
                cv2.putText(
                    frame,
                    "Motion detected",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                )
                cv2.imshow(WINDOW_NAME, frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

                if now > motion_deadline:
                    cap.release()
                    cap = None
                    cv2.destroyWindow(WINDOW_NAME)
                    print("No motion. Camera stopped.")
            else:
                time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
