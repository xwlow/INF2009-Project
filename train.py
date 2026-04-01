from ultralytics import YOLO

def train_model():
    # 1. Load the model
    model = YOLO('yolo26n-cls.pt')

    # 2. Start the training
    results = model.train(
        data='C:\\GitHub\\INF2009-Project\\custom_dataset', 
        epochs=50,
        imgsz=224,
        batch=32,
        patience=10,
        project='brand_sentry',
        name='v1_clean_data',
        workers=4  # You can reduce this if your laptop struggles
    )

if __name__ == '__main__':
    train_model()