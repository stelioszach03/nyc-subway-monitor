#!/bin/bash
# Quick fix script for NYC Subway Monitor
# Applies all fixes without rebuilding containers

set -e

echo "🚇 NYC Subway Monitor - Applying All Fixes"
echo "=========================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check if we're in the project root
if [ ! -f "docker-compose.yml" ] && [ ! -f "infra/docker-compose.yml" ]; then
    echo -e "${RED}Error: Please run from project root${NC}"
    exit 1
fi

# Determine compose file location
if [ -f "infra/docker-compose.yml" ]; then
    COMPOSE_FILE="infra/docker-compose.yml"
    COMPOSE_DIR="infra"
else
    COMPOSE_FILE="docker-compose.yml"
    COMPOSE_DIR="."
fi

echo -e "${YELLOW}Step 1: Applying docker-compose override...${NC}"
cd $COMPOSE_DIR

# Check if override exists, if not create it
if [ ! -f "docker-compose.override.yml" ]; then
    echo "Creating docker-compose.override.yml..."
    cat > docker-compose.override.yml << 'EOF'
version: '3.8'

services:
  permissions-fix:
    image: busybox
    user: root
    volumes:
      - model_artifacts:/models
      - ./backend/data:/data
    command: >
      sh -c "
      mkdir -p /models/artifacts &&
      chown -R 1000:1000 /models &&
      chmod -R 755 /models &&
      chown -R 1000:1000 /data &&
      chmod -R 755 /data &&
      echo 'Permissions fixed'
      "
    
  backend:
    depends_on:
      permissions-fix:
        condition: service_completed_successfully
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    environment:
      - UVICORN_HOST=0.0.0.0
      - UVICORN_PORT=8000
    volumes:
      - model_artifacts:/app/models/artifacts
      - ./backend/data:/app/data

  frontend:
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
      - NEXT_PUBLIC_WS_URL=ws://localhost:8000

volumes:
  model_artifacts:
    driver: local
EOF
fi

cd -

echo -e "${YELLOW}Step 2: Fixing permissions on running containers...${NC}"

# Get backend container ID
BACKEND_CONTAINER=$(docker-compose -f $COMPOSE_FILE ps -q backend 2>/dev/null || true)

if [ ! -z "$BACKEND_CONTAINER" ]; then
    echo "Fixing permissions in backend container..."
    docker exec -u 0 $BACKEND_CONTAINER bash -c "
        mkdir -p /app/models/artifacts &&
        chown -R appuser:appuser /app/models &&
        chmod -R 755 /app/models &&
        mkdir -p /app/data &&
        chown -R appuser:appuser /app/data &&
        chmod -R 755 /app/data
    " || echo -e "${YELLOW}Warning: Could not fix permissions in container${NC}"
fi

echo -e "${YELLOW}Step 3: Restarting services with fixes...${NC}"
cd $COMPOSE_DIR

# Stop services
docker-compose stop backend frontend

# Start with override
docker-compose up -d

cd -

echo -e "${YELLOW}Step 4: Waiting for services to be ready...${NC}"
sleep 10

# Test backend health
echo -e "${YELLOW}Testing backend connection...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8000/health/live > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Backend is healthy${NC}"
        break
    fi
    echo "Waiting for backend... ($i/30)"
    sleep 2
done

# Test frontend
echo -e "${YELLOW}Testing frontend...${NC}"
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Frontend is responding${NC}"
else
    echo -e "${YELLOW}Frontend may still be starting...${NC}"
fi

echo -e "\n${GREEN}✅ All fixes applied!${NC}"
echo -e "\nServices status:"
cd $COMPOSE_DIR
docker-compose ps
cd -

echo -e "\n${YELLOW}Monitor logs with:${NC}"
echo "  cd $COMPOSE_DIR && docker-compose logs -f backend frontend"

echo -e "\n${YELLOW}If issues persist:${NC}"
echo "  1. Check permissions: docker exec -it \$(docker-compose -f $COMPOSE_FILE ps -q backend) ls -la /app/models/"
echo "  2. Check API: curl http://localhost:8000/api/v1/docs"
echo "  3. Check frontend: http://localhost:3000"