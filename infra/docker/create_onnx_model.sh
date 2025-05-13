#!/bin/bash

echo "🔬 Δημιουργία μοντέλου ανίχνευσης ανωμαλιών ONNX..."

# Δημιουργία φακέλου για μοντέλα
mkdir -p models

# Εγκατάσταση Python και απαιτούμενων πακέτων
echo "📦 Εγκατάσταση απαιτούμενων πακέτων..."
docker run --rm -v $(pwd)/models:/app/models python:3.11-slim bash -c "pip install scikit-learn numpy pandas skl2onnx && echo '✅ Πακέτα εγκαταστάθηκαν επιτυχώς'"

# Δημιουργία Python script για το μοντέλο
echo "💻 Δημιουργία script εκπαίδευσης μοντέλου..."
cat > /tmp/create_model.py << 'PYTHON_CODE'
import numpy as np
import pickle
import os
import json
from datetime import datetime
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

# Ορισμός διαδρομών εξόδου
MODEL_PATH = "/app/models/anomaly_model.onnx"
MODEL_DIR = os.path.dirname(MODEL_PATH)
os.makedirs(MODEL_DIR, exist_ok=True)

print("Δημιουργία μοντέλου ανίχνευσης ανωμαλιών...")

# Εκπαίδευση μοντέλου Isolation Forest
# Δημιουργία συνθετικών δεδομένων που μοιάζουν με πρότυπα καθυστέρησης μετρό
n_samples = 2000
np.random.seed(42)

# Δημιουργία δεδομένων για κανονικές συνθήκες
X_normal = np.array([
    np.random.normal(60, 30, n_samples),      # avg_delay - μέση καθυστέρηση
    np.random.normal(120, 60, n_samples),     # max_delay - μέγιστη καθυστέρηση
    np.random.normal(30, 15, n_samples),      # min_delay - ελάχιστη καθυστέρηση
    np.random.normal(40, 20, n_samples),      # delay_std - τυπική απόκλιση καθυστέρησης
    np.random.randint(1, 10, n_samples),      # train_count - αριθμός τρένων
    np.random.normal(20, 10, n_samples),      # delay_per_train - καθυστέρηση ανά τρένο
    np.random.normal(10, 5, n_samples),       # delay_variability - διακύμανση καθυστέρησης
    np.random.randint(0, 24, n_samples),      # hour - ώρα ημέρας
    np.random.randint(0, 7, n_samples),       # day_of_week - ημέρα εβδομάδας
    np.random.binomial(1, 0.3, n_samples),    # is_weekend - είναι Σαββατοκύριακο
    np.random.randint(1, 8, n_samples)        # active_vehicles - ενεργά οχήματα
]).T

# Δημιουργία ανωμαλιών με υψηλές καθυστερήσεις
n_anomalies = 100
X_anomalies = np.array([
    np.random.normal(300, 60, n_anomalies),   # avg_delay
    np.random.normal(600, 120, n_anomalies),  # max_delay
    np.random.normal(150, 30, n_anomalies),   # min_delay
    np.random.normal(200, 40, n_anomalies),   # delay_std
    np.random.randint(1, 4, n_anomalies),     # train_count (λιγότερα τρένα)
    np.random.normal(200, 50, n_anomalies),   # delay_per_train
    np.random.normal(70, 20, n_anomalies),    # delay_variability 
    np.random.randint(0, 24, n_anomalies),    # hour
    np.random.randint(0, 7, n_anomalies),     # day_of_week
    np.random.binomial(1, 0.3, n_anomalies),  # is_weekend
    np.random.randint(1, 4, n_anomalies)      # active_vehicles (λιγότερα οχήματα)
]).T

# Συνδυασμός κανονικών και ανώμαλων δεδομένων
X = np.vstack([X_normal, X_anomalies])

print(f"Εκπαίδευση με {X.shape[0]} δείγματα, {X.shape[1]} χαρακτηριστικά")

# Δημιουργία και εκπαίδευση του pipeline μοντέλου
scaler = StandardScaler()
iso_forest = IsolationForest(
    contamination=0.05,  # 5% των δεδομένων αναμένεται να είναι ανωμαλίες
    random_state=42,
    n_estimators=200,
    max_samples='auto',
    n_jobs=-1
)

pipeline = Pipeline([
    ('scaler', scaler),
    ('isolation_forest', iso_forest)
])

pipeline.fit(X)

# Αποθήκευση του μοντέλου ως ONNX
feature_columns = [
    "avg_delay", "max_delay", "min_delay", "delay_std", 
    "train_count", "delay_per_train", "delay_variability",
    "hour", "day_of_week", "is_weekend", "active_vehicles"
]

initial_types = [('input', FloatTensorType([None, len(feature_columns)]))]
onx = convert_sklearn(
    pipeline, 
    initial_types=initial_types,
    target_opset=15,
    name="SubwayAnomalyDetection"
)

with open(MODEL_PATH, "wb") as f:
    f.write(onx.SerializeToString())

# Αποθήκευση και σε μορφή pickle για συμβατότητα
with open(MODEL_PATH.replace('.onnx', '.pkl'), 'wb') as f:
    pickle.dump(pipeline, f)

# Αποθήκευση scaler ξεχωριστά 
with open(os.path.join(MODEL_DIR, "scaler.pkl"), 'wb') as f:
    pickle.dump(scaler, f)

# Αποθήκευση πληροφοριών χαρακτηριστικών
feature_info = {
    'feature_columns': feature_columns,
    'trained_at': datetime.now().isoformat(),
    'model_version': 'initial'
}

with open(os.path.join(MODEL_DIR, "feature_info.json"), 'w') as f:
    json.dump(feature_info, f, indent=2)

print(f"✅ Δημιουργήθηκε μοντέλο ONNX στο {MODEL_PATH}")
print(f"✅ Δημιουργήθηκε μοντέλο Pickle στο {MODEL_PATH.replace('.onnx', '.pkl')}")
print(f"✅ Αποθηκεύτηκε scaler στο {os.path.join(MODEL_DIR, 'scaler.pkl')}")
print(f"✅ Αποθηκεύτηκαν πληροφορίες χαρακτηριστικών στο {os.path.join(MODEL_DIR, 'feature_info.json')}")
PYTHON_CODE

# Εκτέλεση του Python script για δημιουργία μοντέλου
echo "📋 Εκτέλεση script δημιουργίας μοντέλου..."
docker run --rm -v $(pwd)/models:/app/models -v /tmp/create_model.py:/app/create_model.py python:3.11-slim python /app/create_model.py

# Έλεγχος επιτυχίας δημιουργίας μοντέλου
echo "🔍 Επαλήθευση δημιουργίας μοντέλου..."
if [ -f "models/anomaly_model.onnx" ] && [ -f "models/anomaly_model.pkl" ]; then
    echo "✅ Επιτυχής δημιουργία μοντέλων ONNX και Pickle!"
    echo "✅ Μοντέλο ONNX: $(ls -lh models/anomaly_model.onnx | awk '{print $5}')"
    echo "✅ Μοντέλο Pickle: $(ls -lh models/anomaly_model.pkl | awk '{print $5}')"
else
    echo "❌ Αποτυχία δημιουργίας μοντέλου!"
    exit 1
fi

echo "🎉 Η δημιουργία του μοντέλου ολοκληρώθηκε με επιτυχία!"