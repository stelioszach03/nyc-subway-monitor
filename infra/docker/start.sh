#!/bin/bash

echo "🚀 Έναρξη NYC Subway Monitor"
echo "============================="

# Έλεγχος εάν υπάρχει το αρχείο .env, αλλιώς δημιουργία από το .env.sample
if [ ! -f ".env" ]; then
    echo "Δημιουργία .env από .env.sample..."
    cp .env.sample .env
fi

# Δημιουργία φακέλων για μόνιμα δεδομένα
mkdir -p data/kafka
mkdir -p data/zookeeper/{data,log}
mkdir -p models

# Έναρξη όλων των υπηρεσιών με τη σωστή σειρά
echo "Έναρξη υποδομής (βάσεις δεδομένων και μηνύματα)..."
docker compose up -d zookeeper kafka redis timescaledb

# Αναμονή για την ετοιμότητα της υποδομής
echo "Αναμονή για ετοιμότητα υποδομής..."
WAIT_TIMEOUT=300  # 5 λεπτά μέγιστη αναμονή
WAIT_START=$(date +%s)

wait_for_service() {
    local service=$1
    echo "Αναμονή για $service..."
    while ! docker compose ps $service | grep -q "healthy"; do
        NOW=$(date +%s)
        if [ $((NOW - WAIT_START)) -gt $WAIT_TIMEOUT ]; then
            echo "Λήξη χρονικού ορίου αναμονής για $service!"
            exit 1
        fi
        echo -n "."
        sleep 2
    done
    echo "$service είναι έτοιμο!"
}

wait_for_service "zookeeper"
wait_for_service "kafka"
wait_for_service "redis"
wait_for_service "timescaledb"

# Δημιουργία αρχικού μοντέλου ML
if [ ! -f "models/anomaly_model.onnx" ]; then
    echo "Δημιουργία αρχικού μοντέλου..."
    chmod +x ./create_onnx_model.sh
    ./create_onnx_model.sh
fi

# Έναρξη υπηρεσιών ML και API
echo "Έναρξη υπηρεσιών ML και API..."
docker compose up -d ml

# Αναμονή για την ετοιμότητα της υπηρεσίας ML
wait_for_service "ml"

# Έναρξη υπηρεσίας API
docker compose up -d api

# Αναμονή για την ετοιμότητα της υπηρεσίας API
wait_for_service "api"

# Έναρξη υπόλοιπων υπηρεσιών
echo "Έναρξη υπηρεσιών εισαγωγής δεδομένων, ροής και frontend..."
docker compose up -d ingest stream web trainer

# Έλεγχος κατάστασης
echo ""
echo "Έλεγχος κατάστασης όλων των υπηρεσιών..."
docker compose ps

echo ""
echo "✅ Το NYC Subway Monitor εκκινήθηκε επιτυχώς!"
echo ""
echo "Frontend: http://localhost:3000"
echo "API: http://localhost:8000"
echo "ML υπηρεσία: http://localhost:8001"
echo ""
echo "Χρήσιμες εντολές:"
echo "  - Προβολή καταγραφών: docker compose logs -f [υπηρεσία]"
echo "  - Έλεγχος συστήματος: ./check-health.sh"
echo "  - Τερματισμός: docker compose down"