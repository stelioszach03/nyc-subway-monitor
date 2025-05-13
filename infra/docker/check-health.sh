#!/bin/bash

echo "🔍 NYC Subway Monitor - Έλεγχος Υγείας Συστήματος"
echo "================================================="

# Χρώματα για την έξοδο
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Συνάρτηση ελέγχου υγείας υπηρεσίας
check_service() {
    local service=$1
    local url=$2
    
    echo -n "Έλεγχος $service... "
    
    response=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    
    if [ "$response" -eq 200 ]; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}ΑΠΟΤΥΧΙΑ (HTTP $response)${NC}"
        return 1
    fi
}

# Συνάρτηση ελέγχου κατάστασης μοντέλου ML
check_ml_model() {
    echo -n "Έλεγχος κατάστασης μοντέλου ML... "
    
    response=$(curl -s "http://localhost:8001/health")
    model_status=$(echo "$response" | grep -o '"model_status":"[^"]*' | cut -d'"' -f4)
    model_type=$(echo "$response" | grep -o '"model_type":"[^"]*' | cut -d'"' -f4)
    last_modified=$(echo "$response" | grep -o '"model_last_modified":"[^"]*' | cut -d'"' -f4)
    
    if [ "$model_status" = "loaded" ]; then
        echo -e "${GREEN}$model_status ($model_type) - Τελευταία ενημέρωση: $last_modified${NC}"
        return 0
    else
        echo -e "${YELLOW}$model_status${NC}"
        return 1
    fi
}

# Συνάρτηση ελέγχου εισαγωγής δεδομένων
check_data_ingestion() {
    echo -n "Έλεγχος εισαγωγής δεδομένων... "
    
    # Έλεγχος ενεργών τρένων
    train_count=$(curl -s "http://localhost:8000/trains" | grep -o '"trip_id"' | wc -l)
    
    if [ "$train_count" -gt 0 ]; then
        echo -e "${GREEN}$train_count ενεργά τρένα${NC}"
        return 0
    else
        echo -e "${RED}Δεν υπάρχουν ενεργά τρένα${NC}"
        return 1
    fi
}

# Συνάρτηση ελέγχου μετρικών
check_metrics() {
    echo -n "Έλεγχος μετρικών... "
    
    metrics_count=$(curl -s "http://localhost:8000/subway-metrics" | grep -o '"route_id"' | wc -l)
    
    if [ "$metrics_count" -gt 0 ]; then
        echo -e "${GREEN}$metrics_count γραμμές με μετρικές${NC}"
        return 0
    else
        echo -e "${YELLOW}Δεν υπάρχουν μετρικές${NC}"
        return 1
    fi
}

# Συνάρτηση ελέγχου διαθέσιμων container
check_containers() {
    echo "Κατάσταση containers:"
    echo "-----------------------"
    docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" | while read line; do
        if [[ $line == *"(healthy)"* ]]; then
            echo -e "${GREEN}$line${NC}"
        elif [[ $line == *"(unhealthy)"* ]]; then
            echo -e "${RED}$line${NC}"
        elif [[ $line == *"Name"* ]]; then
            echo -e "$line"
        else
            echo -e "${YELLOW}$line${NC}"
        fi
    done
}

# Συνάρτηση ελέγχου σφαλμάτων στα logs
check_errors() {
    local service=$1
    local count=10
    
    echo "Πρόσφατα σφάλματα στο $service:"
    docker compose logs --tail $count $service | grep -i "error\|exception\|failed" || echo "  ${GREEN}Δεν βρέθηκαν πρόσφατα σφάλματα${NC}"
}

# Κύριος έλεγχος υγείας
echo "1. Έλεγχοι υπηρεσιών:"
echo "---------------------"
check_service "API" "http://localhost:8000/health"
check_service "Frontend" "http://localhost:3000"
check_service "ML υπηρεσία" "http://localhost:8001/health"
echo ""

echo "2. Έλεγχοι δεδομένων και μοντέλου:"
echo "---------------------------------"
check_ml_model
check_data_ingestion
check_metrics
echo ""

echo "3. Κατάσταση containers:"
echo "------------------------"
check_containers
echo ""

echo "4. Έλεγχος σφαλμάτων στα logs:"
echo "------------------------------"
check_errors "api"
echo ""
check_errors "ml"
echo ""
check_errors "ingest"
echo ""
check_errors "stream"
echo ""
check_errors "trainer"
echo ""

echo "==============================================="
echo "Ο έλεγχος υγείας ολοκληρώθηκε!"
echo ""
echo "Εάν βρέθηκαν προβλήματα, δοκιμάστε:"
echo "  - Επανεκκίνηση μιας υπηρεσίας: docker compose restart [υπηρεσία]"
echo "  - Πλήρης επανεκκίνηση: ./start.sh"
echo "  - Επαναδημιουργία μοντέλου: ./create_onnx_model.sh"