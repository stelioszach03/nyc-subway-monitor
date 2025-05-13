# services/trainer/train.py

import os
import json
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sqlalchemy import create_engine, text
import requests

# Υποστήριξη για ONNX εξαγωγή
try:
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    print("ONNX export not available. Using pickle format instead.")

# Διαμόρφωση από μεταβλητές περιβάλλοντος
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "timescaledb")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "subway")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "subway_password")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "subway_monitor")
ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "http://ml:8000")

# Διαδρομή εξόδου μοντέλου
MODEL_OUTPUT_PATH = os.environ.get("MODEL_OUTPUT_PATH", "/app/models/anomaly_model.onnx")

def get_historical_data():
    """Λήψη ιστορικών δεδομένων για εκπαίδευση."""
    print("Σύνδεση με τη βάση δεδομένων...")
    db_url = (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    engine = create_engine(db_url)
    
    end_date = datetime.now()
    # Χρησιμοποίηση περισσότερων δεδομένων για καλύτερη εκπαίδευση
    start_date = end_date - timedelta(days=14)  # 2 εβδομάδες δεδομένων
    print(f"Λήψη δεδομένων από {start_date} έως {end_date}...")
    
    query = f"""
    SELECT
        route_id,
        timestamp,
        latitude,
        longitude,
        delay,
        current_status,
        vehicle_id
    FROM train_history
    WHERE timestamp BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'
      AND delay IS NOT NULL
    ORDER BY timestamp
    """
    
    df = pd.read_sql(query, engine)
    print(f"Ελήφθησαν {len(df)} εγγραφές")
    
    if df.empty:
        print("Δεν βρέθηκαν ιστορικά δεδομένα. Δημιουργία συνθετικών δεδομένων για αρχική εκπαίδευση...")
        # Δημιουργία συνθετικών δεδομένων για όλες τις γραμμές του μετρό
        dummy_data = []
        routes = ['1','2','3','4','5','6','7','A','C','E','B','D','F','M','G','J','Z','L','N','Q','R','W','S']
        
        # Δημιουργία κανονικών σεναρίων καθυστέρησης
        for i in range(2000):  # Περισσότερα σημεία δεδομένων
            route = routes[i % len(routes)]
            
            # Διαφορετικά πρότυπα καθυστέρησης για διαφορετικές γραμμές
            if route in ['A', 'C', 'E', '4', '5', '6']:  # Γραμμές με συνήθως μεγαλύτερες καθυστερήσεις
                delay = np.random.normal(120, 60)
            else:  # Πιο αξιόπιστες γραμμές
                delay = np.random.normal(45, 30)
                
            # Μερικά τρένα χωρίς καθυστέρηση
            if np.random.random() < 0.2:
                delay = np.random.normal(5, 10)
                
            # Αρνητικές καθυστερήσεις (τρένα που είναι νωρίτερα) σπάνια συμβαίνουν
            if np.random.random() < 0.05:
                delay = -np.random.normal(30, 15)
                
            # Εξαιρετικά σπάνιες μεγάλες καθυστερήσεις (ανωμαλίες)
            if np.random.random() < 0.02:
                delay = np.random.normal(600, 120)
                
            timestamp = datetime.now() - timedelta(minutes=30*i % 1440)  # Κατανομή χρόνου σε 24 ώρες
            
            dummy_data.append({
                'route_id': route,
                'timestamp': timestamp,
                'latitude': 40.7589 + np.random.normal(0, 0.1),
                'longitude': -73.9851 + np.random.normal(0, 0.1),
                'delay': max(-120, delay),  # Περιορισμός αρνητικών καθυστερήσεων
                'current_status': np.random.choice(['STOPPED_AT', 'IN_TRANSIT_TO']),
                'vehicle_id': f"{route}_{i % 30}"  # Προσομοίωση διαφορετικών οχημάτων
            })
            
        df = pd.DataFrame(dummy_data)
        print(f"Δημιουργήθηκαν {len(df)} συνθετικές εγγραφές για αρχική εκπαίδευση")
    
    return df

def extract_features(df):
    """Εξαγωγή χαρακτηριστικών για ανίχνευση ανωμαλιών με βελτιωμένη επεξεργασία."""
    print("Εξαγωγή χαρακτηριστικών...")
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Προσθήκη χρονικών χαρακτηριστικών
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['is_weekend'] = df['day_of_week'].isin([5,6]).astype(int)
    df['time_bucket'] = df['timestamp'].dt.floor('5min')
    df['part_of_day'] = pd.cut(
        df['hour'], 
        bins=[0, 6, 10, 15, 19, 24], 
        labels=['night', 'morning_rush', 'midday', 'evening_rush', 'evening']
    )
    
    # Ομαδοποίηση δεδομένων ανά γραμμή, χρονικό παράθυρο και ώρα της ημέρας
    # για την αντιμετώπιση περιοδικών μοτίβων
    agg = df.groupby(['route_id', 'time_bucket', 'part_of_day']).agg({
        'delay': ['mean', 'std', 'max', 'min', 'count'],
        'hour': 'first',
        'day_of_week': 'first',
        'is_weekend': 'first',
        'vehicle_id': 'nunique'  # Αριθμός μοναδικών οχημάτων
    }).reset_index()
    
    # Επιπεδοποίηση των στηλών
    agg.columns = ['_'.join(col).rstrip('_') for col in agg.columns]
    
    # Μετονομασία στηλών για ευκολότερη αναφορά
    rename_dict = {
        'delay_mean': 'avg_delay',
        'delay_std': 'delay_std',
        'delay_max': 'max_delay',
        'delay_min': 'min_delay',
        'delay_count': 'train_count',
        'hour_first': 'hour',
        'day_of_week_first': 'day_of_week',
        'is_weekend_first': 'is_weekend',
        'vehicle_id_nunique': 'active_vehicles'
    }
    agg.rename(columns=rename_dict, inplace=True)
    
    # Υπολογισμός πρόσθετων χαρακτηριστικών
    agg['delay_per_train'] = agg['avg_delay'] / agg['train_count'].clip(lower=1)
    agg['delay_variability'] = agg['delay_std'] / agg['train_count'].clip(lower=1)
    agg['delay_std'] = agg['delay_std'].fillna(0)
    agg['delay_variability'] = agg['delay_variability'].fillna(0)
    agg['vehicles_per_train'] = agg['active_vehicles'] / agg['train_count'].clip(lower=1)
    
    # Δημιουργία μεταβλητής στόχου για εποπτευόμενη εκπαίδευση
    # Εντοπισμός ανωμαλιών με βάση το 99ο εκατοστημόριο για κάθε γραμμή
    agg['is_anomaly'] = 0
    for route in agg['route_id'].unique():
        for part in agg['part_of_day'].unique():
            mask = (agg['route_id'] == route) & (agg['part_of_day'] == part)
            if mask.sum() > 10:  # Αρκετά δεδομένα για υπολογισμό αξιόπιστου κατωφλίου
                th = agg.loc[mask, 'avg_delay'].quantile(0.99)
                agg.loc[mask & (agg['avg_delay'] > th), 'is_anomaly'] = 1
    
    # Συμπλήρωση ελλειπουσών τιμών
    agg = agg.fillna(0)
    
    print(f"Δημιουργήθηκαν {len(agg)} εγγραφές χαρακτηριστικών")
    print(f"Ανωμαλίες: {agg['is_anomaly'].sum()} / {len(agg)} ({agg['is_anomaly'].mean():.2%})")
    
    return agg

def train_model(features):
    """Εκπαίδευση μοντέλου ανίχνευσης ανωμαλιών με βελτιωμένες παραμέτρους."""
    print("\nΕκπαίδευση μοντέλου ανίχνευσης ανωμαλιών...")
    # Επιλογή χαρακτηριστικών για εκπαίδευση
    feature_cols = [
        'avg_delay', 'max_delay', 'min_delay', 'delay_std',
        'train_count', 'delay_per_train', 'delay_variability',
        'hour', 'day_of_week', 'is_weekend', 'active_vehicles'
    ]
    
    # Φίλτραρε χαρακτηριστικά που δεν υπάρχουν στο DataFrame
    feature_cols = [col for col in feature_cols if col in features.columns]
    
    X = features[feature_cols].values
    y = features['is_anomaly'].values
    
    print(f"Εκπαίδευση με {X.shape[0]} δείγματα, {X.shape[1]} χαρακτηριστικά")
    
    # Δημιουργία και εκπαίδευση μοντέλου
    scaler = StandardScaler()
    clf = IsolationForest(
        n_estimators=200,  # Περισσότερα δέντρα για καλύτερη απόδοση
        max_samples='auto',
        contamination=0.05,  # 5% αναμενόμενο ποσοστό ανωμαλιών
        random_state=42,
        n_jobs=-1  # Χρήση όλων των πυρήνων
    )
    
    pipeline = Pipeline([
        ('scaler', scaler),
        ('clf', clf)
    ])
    
    pipeline.fit(X)
    
    # Αξιολόγηση
    preds = (pipeline.predict(X) == -1).astype(int)
    true_anom = y.sum()
    pred_anom = preds.sum()
    overlap = ((y == 1) & (preds == 1)).sum()
    
    print(f"\nΠραγματικές ανωμαλίες: {true_anom}")
    print(f"Προβλεπόμενες ανωμαλίες: {pred_anom}")
    print(f"Επικαλυπτόμενες ανωμαλίες: {overlap}")
    
    if true_anom > 0 and pred_anom > 0:
        precision = overlap / pred_anom if pred_anom > 0 else 0
        recall = overlap / true_anom if true_anom > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        print(f"Precision: {precision:.4f}")
        print(f"Recall: {recall:.4f}")
        print(f"F1 Score: {f1:.4f}")
    
    return pipeline, feature_cols

def export_model(pipeline, feature_cols):
    """Εξαγωγή εκπαιδευμένου μοντέλου σε μορφή ONNX."""
    print("\nΕξαγωγή μοντέλου...")
    model_dir = os.path.dirname(MODEL_OUTPUT_PATH)
    os.makedirs(model_dir, exist_ok=True)
    
    # Επιλογή μεταξύ ONNX και pickle βάσει διαθεσιμότητας
    if ONNX_AVAILABLE and MODEL_OUTPUT_PATH.endswith('.onnx'):
        try:
            # Προετοιμασία για μετατροπή σε ONNX
            n_features = len(feature_cols)
            initial_types = [('input', FloatTensorType([None, n_features]))]
            
            # Μετατροπή μοντέλου σε ONNX
            onx = convert_sklearn(
                pipeline,
                initial_types=initial_types,
                name="subway_anomaly_detection",
                target_opset=15  # Νεότερη έκδοση ONNX
            )
            
            # Αποθήκευση μοντέλου ONNX
            with open(MODEL_OUTPUT_PATH, "wb") as f:
                f.write(onx.SerializeToString())
            print(f"Το μοντέλο ONNX εξήχθη στο {MODEL_OUTPUT_PATH}")
            
            # Αποθήκευση και του pickle για συμβατότητα
            pkl_path = MODEL_OUTPUT_PATH.replace('.onnx', '.pkl')
            with open(pkl_path, 'wb') as f:
                pickle.dump(pipeline, f)
            print(f"Το μοντέλο pickle αποθηκεύτηκε στο {pkl_path} για συμβατότητα")
        except Exception as e:
            print(f"Σφάλμα στην εξαγωγή ONNX: {e}")
            print("Χρήση εξαγωγής pickle ως εναλλακτικής...")
            pkl_path = MODEL_OUTPUT_PATH.replace('.onnx', '.pkl')
            with open(pkl_path, 'wb') as f:
                pickle.dump(pipeline, f)
            print(f"Το μοντέλο pickle αποθηκεύτηκε στο {pkl_path}")
    else:
        # Αποθήκευση σε μορφή pickle
        pkl_path = MODEL_OUTPUT_PATH.replace('.onnx', '.pkl')
        with open(pkl_path, 'wb') as f:
            pickle.dump(pipeline, f)
        print(f"Το μοντέλο pickle αποθηκεύτηκε στο {pkl_path}")
    
    # Αποθήκευση του scaler ξεχωριστά
    scaler = pipeline.named_steps['scaler']
    with open(os.path.join(model_dir, "scaler.pkl"), 'wb') as f:
        pickle.dump(scaler, f)
    print(f"Ο scaler εξήχθη στο {os.path.join(model_dir, 'scaler.pkl')}")
    
    # Αποθήκευση πληροφοριών χαρακτηριστικών
    info = {
        'feature_columns': feature_cols, 
        'trained_at': datetime.now().isoformat(),
        'model_version': datetime.now().strftime('%Y%m%d_%H%M%S')
    }
    with open(os.path.join(model_dir, 'feature_info.json'), 'w') as f:
        json.dump(info, f, indent=2)
    print(f"Οι πληροφορίες χαρακτηριστικών αποθηκεύτηκαν στο {os.path.join(model_dir, 'feature_info.json')}")

def notify_ml_service():
    """Ειδοποίηση της υπηρεσίας ML να επαναφορτώσει το μοντέλο."""
    try:
        print(f"Ειδοποίηση ML service στο {ML_SERVICE_URL} για επαναφόρτωση μοντέλου...")
        response = requests.post(f"{ML_SERVICE_URL}/reload-model", timeout=10)
        if response.status_code == 200:
            print("Επιτυχής ειδοποίηση της υπηρεσίας ML")
            print(f"Απάντηση: {response.json()}")
            return True
        else:
            print(f"Αποτυχία ειδοποίησης της υπηρεσίας ML: {response.status_code}")
            print(f"Απάντηση: {response.text}")
            return False
    except Exception as e:
        print(f"Σφάλμα κατά την ειδοποίηση της υπηρεσίας ML: {e}")
        return False

def main():
    """Κύρια συνάρτηση εκπαίδευσης."""
    print("=== Έναρξη Εκπαίδευσης Μοντέλου Ανίχνευσης Ανωμαλιών NYC Subway ===")
    print(f"Χρόνος έναρξης: {datetime.now().isoformat()}")
    print("="*80)
    
    # Λήψη ιστορικών δεδομένων
    df = get_historical_data()
    
    # Εξαγωγή χαρακτηριστικών
    features = extract_features(df)
    
    # Έλεγχος για επαρκή δεδομένα
    if len(features) < 100:
        print(f"Προειδοποίηση: μόνο {len(features)} εγγραφές για εκπαίδευση. Τα αποτελέσματα μπορεί να υποβαθμιστούν.")
    
    # Εκπαίδευση μοντέλου
    pipeline, cols = train_model(features)
    
    # Εξαγωγή μοντέλου
    export_model(pipeline, cols)
    
    # Ειδοποίηση της υπηρεσίας ML
    notify_ml_service()
    
    print("\nΗ εκπαίδευση μοντέλου ολοκληρώθηκε επιτυχώς!")
    print(f"Χρόνος λήξης: {datetime.now().isoformat()}")

if __name__ == "__main__":
    main()