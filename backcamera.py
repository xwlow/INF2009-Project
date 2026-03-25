import time

import cv2
from gpiozero import MotionSensor


PIR_PIN = 4
CAMERA_INDEX = 0
WINDOW_NAME = "Back Camera Live Feed"
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
MOTION_HOLD_SECONDS = 5
POLL_INTERVAL = 0.1


def open_camera():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not cap.isOpened():
        raise RuntimeError("Unable to open camera.")

    return cap


def main():
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
