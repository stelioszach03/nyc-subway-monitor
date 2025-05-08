# nyc-subway-monitor/services/ml/dags/train_anomaly_model_dag.py
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

# Path to the model training script
TRAIN_SCRIPT_PATH = "/opt/airflow/dags/scripts/train.py"
MODEL_OUTPUT_PATH = "/opt/airflow/ml_models/anomaly_model.onnx"

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'train_subway_anomaly_model',
    default_args=default_args,
    description='Nightly training of the subway anomaly detection model',
    schedule_interval='0 2 * * *',  # Run at 2 AM every day
    start_date=datetime(2025, 5, 1),
    catchup=False,
    tags=['ml', 'subway'],
)

# Check if enough data is available
def check_data_availability(**context):
    """Check if enough data is available for training."""
    import os
    from sqlalchemy import create_engine, text
    
    # Database connection
    POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "timescaledb")
    POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
    POSTGRES_USER = os.environ.get("POSTGRES_USER", "subway")
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "subway_password")
    POSTGRES_DB = os.environ.get("POSTGRES_DB", "subway_monitor")
    
    # Connect to database
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    engine = create_engine(db_url)
    
    # Get data count from the last 24 hours
    yesterday = datetime.now() - timedelta(days=1)
    
    query = f"""
    SELECT COUNT(*) as record_count
    FROM train_delays
    WHERE window_end >= '{yesterday.isoformat()}'
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query)).fetchone()
        count = result[0] if result else 0
    
    # Require at least 1000 records for training
    min_records = 1000
    has_enough_data = count >= min_records
    
    context['ti'].xcom_push(key='has_enough_data', value=has_enough_data)
    context['ti'].xcom_push(key='record_count', value=count)
    
    print(f"Found {count} records from the last 24 hours. Minimum required: {min_records}")
    
    return has_enough_data

# Train the model
def train_model(**context):
    """Execute the model training script."""
    import subprocess
    import os
    
    # Environment variables for the training script
    env = os.environ.copy()
    env["MODEL_OUTPUT_PATH"] = MODEL_OUTPUT_PATH
    
    # Run the training script
    result = subprocess.run(
        ["python", TRAIN_SCRIPT_PATH],
        env=env,
        capture_output=True,
        text=True
    )
    
    print("Training output:")
    print(result.stdout)
    
    if result.returncode != 0:
        print("Error output:")
        print(result.stderr)
        raise Exception("Model training failed")
    
    # Check if model file was created
    if not os.path.exists(MODEL_OUTPUT_PATH):
        raise Exception(f"Model file was not created at {MODEL_OUTPUT_PATH}")
    
    return True

# Validate the trained model
def validate_model(**context):
    """Validate that the model works correctly."""
    import os
    import onnxruntime as ort
    import numpy as np
    
    # Load the ONNX model
    if not os.path.exists(MODEL_OUTPUT_PATH):
        raise Exception(f"Model file not found at {MODEL_OUTPUT_PATH}")
    
    session = ort.InferenceSession(MODEL_OUTPUT_PATH)
    
    # Create dummy input for testing
    dummy_input = np.array([[100.0, 300.0, 0.0, 50.0, 5.0, 20.0]], dtype=np.float32)
    
    # Run inference
    input_name = session.get_inputs()[0].name
    result = session.run(None, {input_name: dummy_input})
    
    # Ensure we got a valid result
    if result is None or len(result) == 0:
        raise Exception("Model validation failed: no output produced")
    
    print(f"Model validation successful. Sample score: {result[0]}")
    return True

# Deploy the model to the ML service
def deploy_model(**context):
    """Copy the model to the ML service deployment path."""
    import os
    import shutil
    
    # Source and destination paths
    source_path = MODEL_OUTPUT_PATH
    dest_path = "/app/models/anomaly_model.onnx"
    
    # Ensure the destination directory exists
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    # Copy the model file
    shutil.copy(source_path, dest_path)
    
    print(f"Model deployed from {source_path} to {dest_path}")
    return True

# Task to check if enough data is available
check_data_task = PythonOperator(
    task_id='check_data_availability',
    python_callable=check_data_availability,
    provide_context=True,
    dag=dag,
)

# Conditional task to train the model if enough data is available
train_model_task = PythonOperator(
    task_id='train_model',
    python_callable=train_model,
    provide_context=True,
    dag=dag,
)

# Task to validate the trained model
validate_model_task = PythonOperator(
    task_id='validate_model',
    python_callable=validate_model,
    provide_context=True,
    dag=dag,
)

# Task to deploy the model
deploy_model_task = PythonOperator(
    task_id='deploy_model',
    python_callable=deploy_model,
    provide_context=True,
    dag=dag,
)

# Define task dependencies
check_data_task >> train_model_task >> validate_model_task >> deploy_model_task