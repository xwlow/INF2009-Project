from ultralytics import YOLO

def main():
    # 1. Load the pre-trained Classification model
    # Note the '-cls' suffix. This is CRITICAL.
    # It tells YOLO we are doing classification, not detection.
    model = YOLO('yolov8n-cls.pt') 

    # 2. Train the model
    # 'data' points to the folder containing 'train' and 'val'
    # 'epochs' is how many times it studies the data (start with 20-50)
    results = model.train(data=r'C:\GitHub\INF2009-Project\dataset', epochs=20, imgsz=224)

if __name__ == '__main__':
    main()