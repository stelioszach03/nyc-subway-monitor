#!/bin/bash

echo "🚇 NYC Subway Monitor - Starting System"
echo "======================================"

# Environment setup
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
    echo "📝 Creating .env from .env.sample..."
    cp .env.sample "$ENV_FILE"
fi

# Create necessary directories
mkdir -p data/kafka data/zookeeper/{data,log} models

# Καθαρισμός ορφανών containers
docker compose down --remove-orphans

# Set trap to handle script interruption
trap cleanup_on_exit INT TERM
function cleanup_on_exit() {
    echo -e "\n⚠️ Startup interrupted. Cleaning up..."
    docker compose down
    exit 1
}

# Βελτιωμένη συνάρτηση για αναμονή υπηρεσιών
wait_for_service() {
    local service=$1
    local max_attempts=${2:-30}
    local retry_interval=${3:-5}
    local attempt=1
    
    echo "⏳ Waiting for $service to be ready..."
    while [ $attempt -le $max_attempts ]; do
        if docker compose ps "$service" | grep -q "healthy"; then
            echo "✅ $service is ready!"
            return 0
        fi
        
        # Έλεγχος αν η υπηρεσία έχει ξεκινήσει αλλά δεν είναι ακόμη υγιής
        if docker compose ps "$service" | grep -q "Up"; then
            if [ "$service" = "kafka" ] && [ $attempt -ge 15 ]; then
                # Ειδικός χειρισμός για το Kafka - δημιουργία θέματος για βοήθεια
                echo "🔄 Trying to create Kafka topic to help with startup..."
                docker compose exec kafka kafka-topics --create --if-not-exists --bootstrap-server localhost:9092 --replication-factor 1 --partitions 1 --topic subway-feeds
                docker compose restart kafka
                sleep 20
            fi
        fi
        
        # Έλεγχος αν η υπηρεσία απέτυχε να ξεκινήσει
        if ! docker compose ps "$service" | grep -q "Up"; then
            echo "❌ $service failed to start! Checking logs..."
            docker compose logs --tail 20 "$service"
            return 1
        fi
        
        echo -n "."
        sleep $retry_interval
        attempt=$((attempt + 1))
    done
    
    echo -e "\n⚠️ $service is taking longer than expected to be healthy, but might still be starting up."
    echo "Continuing startup sequence but services depending on $service might fail."
    return 0  # Συνεχίζουμε παρά το timeout
}

# Απενεργοποίηση αποθήκευσης των προειδοποιήσεων για το version του docker-compose.yaml
export COMPOSE_IGNORE_OBSOLETE=1

# Start infrastructure services one by one with careful ordering
echo "🔄 Starting Zookeeper service..."
docker compose up -d zookeeper
if ! wait_for_service "zookeeper" 20 3; then exit 1; fi

echo "🔄 Starting Kafka service..."
docker compose up -d kafka
# Αύξηση του χρόνου αναμονής για το Kafka και προσαρμογή του retry interval
if ! wait_for_service "kafka" 40 10; then 
    echo "⚠️ Kafka is taking longer than expected. Creating topic and continuing..."
    docker compose exec -T kafka kafka-topics --create --if-not-exists --bootstrap-server localhost:9092 --replication-factor 1 --partitions 1 --topic subway-feeds
fi

echo "🔄 Starting Redis and TimescaleDB services..."
docker compose up -d redis timescaledb
if ! wait_for_service "redis" 20 3; then exit 1; fi
if ! wait_for_service "timescaledb" 20 3; then exit 1; fi

# Create initial model if needed
if [ ! -f "models/anomaly_model.onnx" ]; then
    echo "🧠 Creating initial ML model..."
    chmod +x ./create_onnx_model.sh
    ./create_onnx_model.sh
    # Check if model creation was successful
    if [ ! -f "models/anomaly_model.onnx" ]; then
        echo "❌ Failed to create initial model! Check logs for details."
        exit 1
    fi
fi

# Start ML and API services
echo "🔄 Starting ML service..."
docker compose up -d ml
if ! wait_for_service "ml" 40 5; then 
    echo "⚠️ ML service is taking longer than expected. Continuing startup..."
fi

echo "🔄 Starting API service..."
docker compose up -d api
if ! wait_for_service "api" 40 5; then 
    echo "⚠️ API service is taking longer than expected. Continuing startup..."
fi

# Start remaining services
echo "🔄 Starting all remaining services..."
docker compose up -d ingest stream web trainer

# Verify all services are running
echo "🔍 Verifying all services..."
if docker compose ps | grep -q "Exit"; then
    echo "⚠️ Some services failed to start properly. Check logs for details."
    docker compose ps
    echo "Run 'docker compose logs <service>' for more details."
    echo "Continuing anyway..."
else
    echo "✅ All services started successfully!"
fi

# Triggering initial model training
echo "🧠 Triggering initial model training..."
docker compose exec -T trainer python /app/train.py || echo "⚠️ Initial training didn't complete - will retry automatically"

echo ""
echo "🚀 NYC Subway Monitor is now running!"
echo "· Web UI: http://localhost:3000"
echo "· API: http://localhost:8000"
echo "· ML Service: http://localhost:8001"
echo ""
echo "📊 System is now collecting data and training models continuously."
echo "📝 Check health with: ./check-health.sh"
echo "📉 To stop the system: docker compose down"