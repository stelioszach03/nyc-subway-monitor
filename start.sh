#!/bin/bash

# NYC Subway Monitor - Startup Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect OS for virtual environment activation
if [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    VENV_ACTIVATE="backend/venv/Scripts/activate"
else
    VENV_ACTIVATE="backend/venv/bin/activate"
fi

# Function to cleanup background processes
cleanup() {
    print_status "Shutting down services..."
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

print_status "Starting NYC Subway Monitor..."

# Check if virtual environment exists
if [ ! -f "$VENV_ACTIVATE" ]; then
    print_error "Virtual environment not found. Please run setup.sh first."
    exit 1
fi

# Start backend
print_status "Starting backend server..."
cd backend
source venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# Wait for backend to start
sleep 5

# Start frontend
print_status "Starting frontend server..."
cd frontend
npm run dev -- --port 3000 --hostname 0.0.0.0 &
FRONTEND_PID=$!
cd ..

print_success "Services started successfully!"
print_status "Backend API: http://localhost:8000"
print_status "Frontend: http://localhost:3000"
print_status "API Documentation: http://localhost:8000/api/v1/docs"
print_status ""
print_status "Press Ctrl+C to stop all services"

# Wait for processes
wait
