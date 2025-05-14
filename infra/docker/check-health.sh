#!/bin/bash

echo "🔍 NYC Subway Monitor - System Health Check"
echo "==========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to check service health
check_service() {
    local service=$1
    local url=$2
    local timeout=${3:-10}
    
    echo -n "Checking $service... "
    
    response=$(curl -s -m $timeout -o /dev/null -w "%{http_code}" "$url" 2>/dev/null)
    
    if [ "$response" -eq 200 ]; then
        echo -e "${GREEN}OK ($response)${NC}"
        return 0
    elif [ "$response" -gt 0 ]; then
        echo -e "${RED}FAIL (HTTP $response)${NC}"
        return 1
    else
        echo -e "${RED}FAIL (Connection Error)${NC}"
        return 2
    fi
}

# Function to check ML model status
check_ml_model() {
    echo -n "Checking ML model status... "
    
    response=$(curl -s -m 10 "http://localhost:8001/health" 2>/dev/null)
    if [ $? -ne 0 ]; then
        echo -e "${RED}FAIL (Connection Error)${NC}"
        return 1
    fi
    
    model_status=$(echo "$response" | grep -o '"model_status":"[^"]*' | cut -d'"' -f4)
    model_type=$(echo "$response" | grep -o '"model_type":"[^"]*' | cut -d'"' -f4)
    last_modified=$(echo "$response" | grep -o '"model_last_modified":"[^"]*' | cut -d'"' -f4)
    
    if [ "$model_status" = "loaded" ]; then
        echo -e "${GREEN}$model_status ($model_type)${NC}"
        echo "  Last updated: $last_modified"
        return 0
    else
        echo -e "${YELLOW}$model_status${NC}"
        echo "  Model not properly loaded. Check ML service logs."
        return 1
    fi
}

# Function to check data ingestion
check_data_ingestion() {
    echo -n "Checking data ingestion... "
    
    # Check active trains
    response=$(curl -s -m 10 "http://localhost:8000/trains?limit=1" 2>/dev/null)
    if [ $? -ne 0 ]; then
        echo -e "${RED}FAIL (Connection Error)${NC}"
        return 1
    fi
    
    train_count=$(echo "$response" | grep -o '"trip_id"' | wc -l)
    
    if [ "$train_count" -gt 0 ]; then
        total_trains=$(curl -s -m 10 "http://localhost:8000/trains?limit=100" 2>/dev/null | grep -o '"trip_id"' | wc -l)
        echo -e "${GREEN}$total_trains active trains${NC}"
        return 0
    else
        echo -e "${RED}No active trains${NC}"
        echo "  The ingest service may not be receiving data from MTA feeds."
        echo "  Check the ingest service logs for details."
        return 1
    fi
}

# Function to check metrics
check_metrics() {
    echo -n "Checking metrics data... "
    
    response=$(curl -s -m 10 "http://localhost:8000/subway-metrics" 2>/dev/null)
    if [ $? -ne 0 ]; then
        echo -e "${RED}FAIL (Connection Error)${NC}"
        return 1
    fi
    
    metrics_count=$(echo "$response" | grep -o '"route_id"' | wc -l)
    
    if [ "$metrics_count" -gt 0 ]; then
        echo -e "${GREEN}$metrics_count routes with metrics${NC}"
        return 0
    else
        echo -e "${YELLOW}No metrics available${NC}"
        echo "  The stream service may not be processing data correctly."
        echo "  Check the stream service logs for details."
        return 1
    fi
}

# Function to check anomaly detection
check_anomaly_detection() {
    echo -n "Checking anomaly detection... "
    
    response=$(curl -s -m 10 "http://localhost:8001/scores" 2>/dev/null)
    if [ $? -ne 0 ]; then
        echo -e "${RED}FAIL (Connection Error)${NC}"
        return 1
    fi
    
    score_count=$(echo "$response" | grep -o '"score"' | wc -l)
    
    if [ "$score_count" -gt 0 ]; then
        echo -e "${GREEN}$score_count routes with anomaly scores${NC}"
        
        # Check if any anomalies detected
        anomaly_count=$(curl -s -m 10 "http://localhost:8000/alerts" 2>/dev/null | grep -o '"id"' | wc -l)
        if [ "$anomaly_count" -gt 0 ]; then
            echo "  ${YELLOW}$anomaly_count active alerts detected${NC}"
        else
            echo "  No anomalies detected (system normal)"
        fi
        
        return 0
    else
        echo -e "${YELLOW}No anomaly scores available${NC}"
        echo "  The ML service may not be calculating scores correctly."
        echo "  Check the ML service logs for details."
        return 1
    fi
}

# Function to check container status
check_containers() {
    echo "Container Status:"
    echo "-----------------"
    
    # Get all container statuses
    containers=$(docker compose ps --format "{{.Name}}|{{.Status}}|{{.Health}}" | sort)
    
    # Count containers by state
    total_containers=$(echo "$containers" | wc -l)
    running_containers=$(echo "$containers" | grep -c "Up ")
    healthy_containers=$(echo "$containers" | grep -c "(healthy)")
    unhealthy_containers=$(echo "$containers" | grep -c "(unhealthy)")
    
    echo -e "Total: $total_containers | Running: ${BLUE}$running_containers${NC} | Healthy: ${GREEN}$healthy_containers${NC} | Unhealthy: ${RED}$unhealthy_containers${NC}"
    echo ""
    
    # Display detailed status
    echo "Detailed Status:"
    echo "$containers" | while IFS="|" read -r name status health; do
        if [[ "$health" == "(healthy)" ]]; then
            echo -e "  ${GREEN}✓${NC} $name - $status $health"
        elif [[ "$health" == "(unhealthy)" ]]; then
            echo -e "  ${RED}✗${NC} $name - $status $health"
        elif [[ "$status" == *"Up"* ]]; then
            echo -e "  ${BLUE}○${NC} $name - $status $health"
        else
            echo -e "  ${RED}✗${NC} $name - $status $health"
        fi
    done
}

# Function to check for errors in logs
check_logs() {
    local service=$1
    local hours=${2:-1}
    local count=${3:-10}
    
    echo "Recent errors in $service logs (last $hours hour$([ "$hours" -gt 1 ] && echo "s")):"
    
    # Convert hours to nanoseconds for Docker logs --since
    local since="${hours}h"
    
    # Find errors/warnings in logs
    errors=$(docker compose logs --tail 1000 --since "$since" "$service" 2>&1 | grep -i -E 'error|exception|fail|critical|fatal|unexpected' | tail -n "$count")
    warnings=$(docker compose logs --tail 1000 --since "$since" "$service" 2>&1 | grep -i -E 'warning|warn' | tail -n "$count")
    
    if [ -z "$errors" ]; then
        echo -e "  ${GREEN}No errors found${NC}"
    else
        echo -e "  ${RED}Errors:${NC}"
        echo "$errors" | sed 's/^/    /'
    fi
    
    if [ -n "$warnings" ]; then
        echo -e "  ${YELLOW}Warnings:${NC}"
        echo "$warnings" | sed 's/^/    /'
    fi
}

# Function to check database
check_database() {
    echo -n "Checking database... "
    
    # Run a simple query using docker exec
    result=$(docker compose exec -T timescaledb psql -U "${POSTGRES_USER:-subway}" -d "${POSTGRES_DB:-subway_monitor}" -c "SELECT COUNT(*) FROM train_delays;" 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        count=$(echo "$result" | grep -v "count" | grep -v "^-" | grep -v "row" | tr -d ' ')
        if [[ "$count" =~ ^[0-9]+$ ]]; then
            echo -e "${GREEN}OK ($count delay records)${NC}"
            return 0
        else
            echo -e "${YELLOW}Connected, but no valid data${NC}"
            return 1
        fi
    else
        echo -e "${RED}FAIL${NC}"
        return 2
    fi
}

# Function to check model training
check_training() {
    echo -n "Checking model training... "
    
    # Check if the model file exists
    if docker compose exec -T ml test -f /app/models/anomaly_model.onnx 2>/dev/null; then
        # Get model file modification time
        model_time=$(docker compose exec -T ml stat -c %Y /app/models/anomaly_model.onnx 2>/dev/null)
        current_time=$(date +%s)
        
        # Calculate age in hours
        age_seconds=$((current_time - model_time))
        age_hours=$((age_seconds / 3600))
        
        if [ "$age_hours" -lt 24 ]; then
            echo -e "${GREEN}OK (model is $age_hours hours old)${NC}"
            
            # Get feature info
            feature_info=$(docker compose exec -T ml cat /app/models/feature_info.json 2>/dev/null)
            if [ -n "$feature_info" ]; then
                trained_at=$(echo "$feature_info" | grep -o '"trained_at":"[^"]*' | cut -d'"' -f4)
                echo "  Last trained at: $trained_at"
                
                feature_count=$(echo "$feature_info" | grep -o '"feature_columns"' | wc -l)
                if [ "$feature_count" -gt 0 ]; then
                    echo "  Feature information available"
                fi
            fi
            
            return 0
        else
            echo -e "${YELLOW}WARNING (model is $age_hours hours old)${NC}"
            echo "  The model hasn't been retrained recently. Check trainer service logs."
            return 1
        fi
    else
        echo -e "${RED}FAIL (model not found)${NC}"
        echo "  The model file does not exist. Check if the trainer service is working."
        return 2
    fi
}

# Function to check disk space
check_disk_space() {
    echo -n "Checking disk space... "
    
    # Check disk space for Docker volumes
    docker_root=$(docker info 2>/dev/null | grep "Docker Root Dir" | awk '{print $4}')
    
    if [ -z "$docker_root" ]; then
        docker_root="/var/lib/docker"  # Default location
    fi
    
    disk_usage=$(df -h "$docker_root" | tail -n 1)
    disk_used_percent=$(echo "$disk_usage" | awk '{print $5}' | tr -d '%')
    
    if [ "$disk_used_percent" -gt 90 ]; then
        echo -e "${RED}CRITICAL ($disk_used_percent% used)${NC}"
        echo "  $disk_usage"
        echo "  Docker volume storage is nearly full. Free up space or expand disk."
        return 2
    elif [ "$disk_used_percent" -gt 80 ]; then
        echo -e "${YELLOW}WARNING ($disk_used_percent% used)${NC}"
        echo "  $disk_usage"
        echo "  Docker volume storage is getting full. Monitor closely."
        return 1
    else
        echo -e "${GREEN}OK ($disk_used_percent% used)${NC}"
        return 0
    fi
}

# Function to check system memory
check_memory() {
    echo -n "Checking system memory... "
    
    # Check available memory
    mem_info=$(free -m | grep Mem)
    total_mem=$(echo "$mem_info" | awk '{print $2}')
    used_mem=$(echo "$mem_info" | awk '{print $3}')
    free_mem=$(echo "$mem_info" | awk '{print $4}')
    used_percent=$((used_mem * 100 / total_mem))
    
    if [ "$used_percent" -gt 90 ]; then
        echo -e "${RED}CRITICAL ($used_percent% used, $free_mem MB free)${NC}"
        echo "  System memory is critically low. Check for memory leaks or increase RAM."
        return 2
    elif [ "$used_percent" -gt 80 ]; then
        echo -e "${YELLOW}WARNING ($used_percent% used, $free_mem MB free)${NC}"
        echo "  System memory usage is high. Monitor closely."
        return 1
    else
        echo -e "${GREEN}OK ($used_percent% used, $free_mem MB free)${NC}"
        return 0
    fi
}

# Main health check
echo "1. Service Availability:"
echo "------------------------"
check_service "API" "http://localhost:8000/health" 5
api_status=$?
check_service "Web Frontend" "http://localhost:3000" 5
web_status=$?
check_service "ML Service" "http://localhost:8001/health" 5
ml_status=$?
echo ""

echo "2. Data and Model Status:"
echo "-------------------------"
check_ml_model
ml_model_status=$?
check_data_ingestion
data_status=$?
check_metrics
metrics_status=$?
check_anomaly_detection
anomaly_status=$?
check_database
db_status=$?
check_training
training_status=$?
echo ""

echo "3. System Health:"
echo "-----------------"
check_containers
container_status=$?
check_disk_space
disk_status=$?
check_memory
memory_status=$?
echo ""

echo "4. Recent Errors:"
echo "-----------------"
check_logs "api" 1 5
check_logs "ml" 1 5
check_logs "ingest" 1 5
check_logs "stream" 1 5
check_logs "trainer" 1 5
echo ""

# Calculate overall health score
health_score=100

# Major components (each -20 if critical)
[ $api_status -gt 0 ] && health_score=$((health_score - 20))
[ $ml_status -gt 0 ] && health_score=$((health_score - 20))
[ $data_status -gt 0 ] && health_score=$((health_score - 20))
[ $metrics_status -gt 0 ] && health_score=$((health_score - 15))
[ $ml_model_status -gt 0 ] && health_score=$((health_score - 15))

# Minor components (each -10 if critical)
[ $web_status -gt 0 ] && health_score=$((health_score - 10))
[ $training_status -gt 0 ] && health_score=$((health_score - 10))
[ $db_status -gt 1 ] && health_score=$((health_score - 10))
[ $disk_status -gt 1 ] && health_score=$((health_score - 10))
[ $memory_status -gt 1 ] && health_score=$((health_score - 10))

# Ensure score stays within bounds
health_score=$(( health_score < 0 ? 0 : health_score ))

echo "============================================="
echo -n "Overall System Health: "

if [ $health_score -ge 90 ]; then
    echo -e "${GREEN}$health_score% - GOOD${NC}"
    echo "The NYC Subway Monitor is running properly!"
elif [ $health_score -ge 70 ]; then
    echo -e "${YELLOW}$health_score% - DEGRADED${NC}"
    echo "The system is running with some issues that should be addressed."
else
    echo -e "${RED}$health_score% - CRITICAL${NC}"
    echo "The system has serious issues that require immediate attention!"
fi

echo ""
echo "Recommendations:"
if [ $api_status -gt 0 ] || [ $ml_status -gt 0 ] || [ $data_status -gt 0 ]; then
    echo "  - Critical services are not responding. Check logs and restart services:"
    echo "    docker compose restart api ml ingest stream"
fi

if [ $ml_model_status -gt 0 ] || [ $training_status -gt 0 ]; then
    echo "  - Model training issues detected. Try manual model creation:"
    echo "    ./create_onnx_model.sh"
fi

if [ $disk_status -gt 0 ]; then
    echo "  - Disk space is getting low. Consider cleanup:"
    echo "    docker system prune -a"
fi

echo "  - For more detailed troubleshooting:"
echo "    docker compose logs [service-name]"
echo ""
echo "To restart the entire system:"
echo "  docker compose down && ./start.sh"