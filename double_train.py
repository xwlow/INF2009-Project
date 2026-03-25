import pandas as pd
from sklearn.ensemble import IsolationForest
import joblib
import os

# 1. Load the database
df = pd.read_csv('sentry_behavior_database.csv')

# 2. Define our Experts
# 0 = Person, 2 = Car, 7 = Truck (COCO indices)
experts = {
    "human": [0],
    "vehicle": [2, 7]
}

for name, ids in experts.items():
    # Filter data for this specific expert
    subset = df[df['class_id'].isin(ids)]
    
    if len(subset) < 20:
        print(f"⚠️ Not enough data for {name} expert (Need ~100 rows, got {len(subset)}). Skipping.")
        continue

    # Select features (Duration, CX, CY, Area)
    features = subset[['duration', 'cx', 'cy', 'area']]

    # Train the specialist
    model = IsolationForest(contamination=0.01, random_state=42)
    model.fit(features.values)

    # Save the specialized "Brain"
    model_name = f'{name}_risk_model.joblib'
    joblib.dump(model, model_name)
    print(f"✅ {name.upper()} Specialist trained and saved as '{model_name}'!")