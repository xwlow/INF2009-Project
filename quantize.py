from ultralytics import YOLO

# 1. Load your original 'best.pt'
model = YOLO('runs/classify/train3/weights/best.pt')

# 2. Export to OpenVINO with INT8 Quantization
# 'int8=True' is the trigger. 
# We use 'data' to provide the calibration images.
model.export(format='openvino', int8=True)