import pandas as pd
from sklearn.ensemble import IsolationForest
import joblib

# 1. Load your collected data
df = pd.read_csv('sentry_behavior_database.csv')

# 2. Select the features for training
# We drop 'class_id' from the training features but use it if doing decentralized models
features = df[['duration', 'cx', 'cy', 'area']]

# 3. Train the Isolation Forest
# We set a low contamination because we assume our training data is 99% "Normal"
model = IsolationForest(contamination=0.01, random_state=42)
model.fit(features.values)

# 4. Save the "Brain"
joblib.dump(model, 'risk_model.joblib')
print("✅ Risk model trained and saved as 'risk_model.joblib'!")