from ultralytics import YOLO
import os
import cv2

# 1. Load YOUR newly trained model
# (Update this path to where the training step saved the file)
model = YOLO('runs/classify/train4/weights/best.pt')

# 2. Path to your test folder
test_folder = r"C:\GitHub\INF2009-Project\dataset\test"

# 3. Loop through images and predict
for filename in os.listdir(test_folder):
    if filename.endswith((".jpg", ".png", ".jpeg")):
        filepath = os.path.join(test_folder, filename)
        
        # Run inference
        results = model(filepath)
        
        # Extract the result
        # top1 gives the index of the most likely class
        top_class_index = results[0].probs.top1
        top_class_name = results[0].names[top_class_index]
        confidence = results[0].probs.top1conf.item()
        
        print(f"Image: {filename} --> Prediction: {top_class_name} ({confidence:.2%})")

        # Optional: Show the image with the label
        img = cv2.imread(filepath)
        cv2.putText(img, f"{top_class_name} {confidence:.1%}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow("Result", img)
        cv2.waitKey(0) # Press any key to see the next image

cv2.destroyAllWindows()