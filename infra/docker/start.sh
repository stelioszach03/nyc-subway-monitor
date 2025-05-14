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

# Set trap to handle script interruption
trap cleanup_on_exit INT TERM
function cleanup_on_exit() {
    echo -e "\n⚠️ Startup interrupted. Cleaning up..."
    docker compose down
    exit 1
}

# Function to wait for service health with better error handling
wait_for_service() {
    local service=$1
    local max_attempts=${2:-30}
    local attempt=1
    
    echo "⏳ Waiting for $service to be ready..."
    while [ $attempt -le $max_attempts ]; do
        if docker compose ps "$service" | grep -q "healthy"; then
            echo "✅ $service is ready!"
            return 0
        fi
        
        # Check if service failed to start
        if ! docker compose ps "$service" | grep -q "Up"; then
            echo "❌ $service failed to start! Checking logs..."
            docker compose logs --tail 20 "$service"
            return 1
        fi
        
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo -e "\n❌ Timed out waiting for $service to be ready after $max_attempts attempts!"
    docker compose logs --tail 20 "$service"
    return 1
}

# Start infrastructure services
echo "🔄 Starting infrastructure services..."
docker compose up -d zookeeper kafka redis timescaledb

# Wait for infrastructure services
if ! wait_for_service "zookeeper"; then exit 1; fi
if ! wait_for_service "kafka"; then exit 1; fi
if ! wait_for_service "redis"; then exit 1; fi
if ! wait_for_service "timescaledb"; then exit 1; fi

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
if ! wait_for_service "ml"; then exit 1; fi

echo "🔄 Starting API service..."
docker compose up -d api
if ! wait_for_service "api"; then exit 1; fi

# Start remaining services
echo "🔄 Starting all remaining services..."
docker compose up -d ingest stream web trainer

# Verify all services are running
echo "🔍 Verifying all services..."
if docker compose ps | grep -q "Exit"; then
    echo "⚠️ Some services failed to start properly. Check logs for details."
    docker compose ps
    echo "Run 'docker compose logs <service>' for more details."
else
    echo "✅ All services started successfully!"
fi

echo ""
echo "🚀 NYC Subway Monitor is now running!"
echo "· Web UI: http://localhost:3000"
echo "· API: http://localhost:8000"
echo "· ML Service: http://localhost:8001"
echo ""
echo "📊 System is now collecting data and training models continuously."
echo "📝 Check health with: ./check-health.sh"
echo "📉 To stop the system: docker compose down"