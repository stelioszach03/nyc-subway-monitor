#!/bin/bash

# NYC Subway Monitor - Local Setup Script
# Supports Windows (Git Bash/WSL), macOS, and Linux

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        OS="windows"
    else
        print_error "Unsupported operating system: $OSTYPE"
        exit 1
    fi
    print_status "Detected OS: $OS"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install Python if not available
install_python() {
    if command_exists python3; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
        if [[ $(echo "$PYTHON_VERSION >= 3.8" | bc -l) -eq 1 ]]; then
            print_success "Python $PYTHON_VERSION found"
            PYTHON_CMD="python3"
            return
        fi
    fi

    print_warning "Python 3.8+ not found. Installing..."
    
    case $OS in
        "linux")
            if command_exists apt-get; then
                sudo apt-get update
                sudo apt-get install -y python3 python3-pip python3-venv python3-dev
            elif command_exists yum; then
                sudo yum install -y python3 python3-pip python3-venv python3-devel
            elif command_exists dnf; then
                sudo dnf install -y python3 python3-pip python3-venv python3-devel
            else
                print_error "Package manager not found. Please install Python 3.8+ manually."
                exit 1
            fi
            ;;
        "macos")
            if command_exists brew; then
                brew install python@3.12
            else
                print_error "Homebrew not found. Please install Python 3.8+ manually or install Homebrew first."
                exit 1
            fi
            ;;
        "windows")
            print_error "Please install Python 3.8+ from https://python.org/downloads/ and run this script again."
            exit 1
            ;;
    esac
    
    PYTHON_CMD="python3"
}

# Install Node.js if not available
install_nodejs() {
    if command_exists node; then
        NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
        if [[ $NODE_VERSION -ge 18 ]]; then
            print_success "Node.js $(node --version) found"
            return
        fi
    fi

    print_warning "Node.js 18+ not found. Installing..."
    
    case $OS in
        "linux")
            # Install Node.js via NodeSource
            curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
            sudo apt-get install -y nodejs
            ;;
        "macos")
            if command_exists brew; then
                brew install node
            else
                print_error "Homebrew not found. Please install Node.js 18+ manually or install Homebrew first."
                exit 1
            fi
            ;;
        "windows")
            print_error "Please install Node.js 18+ from https://nodejs.org/ and run this script again."
            exit 1
            ;;
    esac
}

# Install SQLite if not available
install_sqlite() {
    if command_exists sqlite3; then
        print_success "SQLite found"
        return
    fi

    print_warning "SQLite not found. Installing..."
    
    case $OS in
        "linux")
            if command_exists apt-get; then
                sudo apt-get install -y sqlite3 libsqlite3-dev
            elif command_exists yum; then
                sudo yum install -y sqlite sqlite-devel
            elif command_exists dnf; then
                sudo dnf install -y sqlite sqlite-devel
            fi
            ;;
        "macos")
            if command_exists brew; then
                brew install sqlite
            else
                print_error "Homebrew not found. Please install SQLite manually."
                exit 1
            fi
            ;;
        "windows")
            print_warning "SQLite should be available with Python. If not, please install it manually."
            ;;
    esac
}

# Setup Python virtual environment
setup_python_env() {
    print_status "Setting up Python virtual environment..."
    
    cd backend
    
    if [ ! -d "venv" ]; then
        $PYTHON_CMD -m venv venv
    fi
    
    # Activate virtual environment
    if [[ "$OS" == "windows" ]]; then
        source venv/Scripts/activate
    else
        source venv/bin/activate
    fi
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install dependencies
    print_status "Installing Python dependencies..."
    # Try minimal requirements first, then full requirements
    if [ -f "requirements_minimal.txt" ]; then
        print_status "Installing minimal Python dependencies first..."
        pip install -r requirements_minimal.txt
        print_status "Minimal dependencies installed. You can install full ML dependencies later with:"
        print_status "pip install torch scipy"
    else
        pip install -r requirements.txt
    fi
    
    cd ..
}

# Setup Node.js environment
setup_nodejs_env() {
    print_status "Setting up Node.js environment..."
    
    cd frontend
    
    # Install dependencies
    print_status "Installing Node.js dependencies..."
    npm install
    
    cd ..
}

# Create local configuration
create_local_config() {
    print_status "Creating local configuration..."
    
    # Copy environment file
    if [ ! -f ".env" ]; then
        cp .env.example .env
        print_success "Created .env file from .env.example"
    fi
    
    # Update .env for local setup
    cat > .env << EOF
# --- Local Development Configuration ---
# Database (SQLite)
DATABASE_URL=sqlite+aiosqlite:///./subway_monitor.db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=subway_monitor

# Redis (In-memory fallback)
REDIS_URL=memory://localhost

# API Configuration
API_V1_PREFIX=/api/v1
CORS_ORIGINS=["http://localhost:3000","http://localhost:3001","http://localhost:51962","http://localhost:56419"]
DEBUG=true

# ML Configuration
MODEL_RETRAIN_HOUR=3
ANOMALY_CONTAMINATION=0.05
LSTM_SEQUENCE_LENGTH=24
LSTM_HIDDEN_SIZE=128

# Feed Configuration
FEED_UPDATE_INTERVAL=30
FEED_TIMEOUT=10
MAX_RETRIES=3

# Feature Engineering
HEADWAY_WINDOW_MINUTES=30
ROLLING_WINDOW_HOURS=1

# WebSocket
WS_HEARTBEAT_INTERVAL=30
WS_MAX_CONNECTIONS=1000

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
NEXT_PUBLIC_MAPBOX_TOKEN=pk.eyJ1Ijoic3RlbGlvc3phY2gwMDMiLCJhIjoiY205bmNqanJuMGpyZzJqc2VibG91aHh6MSJ9._RaxW8Cprc33mxaUfsMEnw

# Monitoring
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
EOF
}

# Create startup script
create_startup_script() {
    print_status "Creating startup script..."
    
    cat > start.sh << 'EOF'
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
source $VENV_ACTIVATE
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
EOF

    chmod +x start.sh
}

# Main setup function
main() {
    print_status "NYC Subway Monitor - Local Setup"
    print_status "================================="
    
    detect_os
    install_python
    install_nodejs
    install_sqlite
    setup_python_env
    setup_nodejs_env
    create_local_config
    create_startup_script
    
    print_success "Setup completed successfully!"
    print_status ""
    print_status "To start the application, run:"
    print_status "  ./start.sh"
    print_status ""
    print_status "The application will be available at:"
    print_status "  Frontend: http://localhost:3000"
    print_status "  Backend API: http://localhost:8000"
    print_status "  API Docs: http://localhost:8000/api/v1/docs"
}

# Run main function
main "$@"