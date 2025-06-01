# NYC Subway Monitor - Local Setup (No Docker)

A real-time NYC subway monitoring system that runs locally on Windows, macOS, and Linux without Docker dependencies.

## 🚀 Quick Start

### Prerequisites
- **Windows**: Git Bash or WSL
- **macOS**: Terminal with Homebrew
- **Linux**: Terminal with package manager (apt/yum)

### One-Command Setup

```bash
# Clone and setup (first time)
git clone https://github.com/stelioszach03/nyc-subway-monitor.git
cd nyc-subway-monitor
git checkout local-setup-no-docker
chmod +x setup.sh
./setup.sh --minimal

# Start the application
./start.sh
```

That's it! The application will be running at:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/api/v1/docs

## 📋 What's Included

### ✅ Features
- **Real-time MTA data ingestion** (8 subway feeds)
- **Live train positions** for all NYC subway lines
- **Station information** (1,497 stations)
- **RESTful API** with comprehensive endpoints
- **Health monitoring** and feed status
- **Anomaly detection** (basic version without ML)
- **Cross-platform compatibility** (Windows/macOS/Linux)

### 🗂️ Architecture
- **Backend**: FastAPI with SQLite database
- **Frontend**: Next.js React application
- **Database**: SQLite (no PostgreSQL required)
- **Cache**: In-memory (no Redis required)
- **Data Source**: Live MTA GTFS-RT feeds

## 🛠️ Setup Options

### Minimal Setup (Recommended)
```bash
./setup.sh --minimal
```
- Installs only essential dependencies
- Faster setup (~2-3 minutes)
- No ML/PyTorch dependencies
- Perfect for development and testing

### Full Setup
```bash
./setup.sh
```
- Includes all dependencies including ML libraries
- Longer setup time (~5-10 minutes)
- Enables advanced anomaly detection features

## 📊 API Endpoints

### Core Endpoints
- `GET /health/live` - Service health check
- `GET /health/ready` - Readiness probe
- `GET /api/v1/stations/` - List all subway stations
- `GET /api/v1/feeds/positions/{line}` - Get train positions for a line
- `GET /api/v1/feeds/status` - Feed ingestion status
- `GET /api/v1/anomalies/stats` - Anomaly statistics

### Example Usage
```bash
# Get all stations
curl http://localhost:8000/api/v1/stations/

# Get train positions for line 1
curl http://localhost:8000/api/v1/feeds/positions/1

# Get feed status
curl http://localhost:8000/api/v1/feeds/status
```

## 🔧 Development

### Project Structure
```
nyc-subway-monitor/
├── setup.sh              # Automated setup script
├── start.sh               # Application startup script
├── backend/               # FastAPI backend
│   ├── app/
│   │   ├── main.py       # Application entry point
│   │   ├── routers/      # API endpoints
│   │   ├── db/           # Database models and operations
│   │   └── services/     # Business logic
│   ├── requirements.txt  # Python dependencies
│   └── requirements_minimal.txt  # Minimal dependencies
├── frontend/              # Next.js frontend
│   ├── src/
│   ├── package.json
│   └── next.config.js
└── data/                  # GTFS static data
```

### Manual Commands
```bash
# Backend only
cd backend
source venv/bin/activate  # or venv\Scripts\activate on Windows
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend only
cd frontend
npm run dev
```

## 📈 Live Data

The system processes real-time data from MTA's GTFS-RT feeds:
- **Feed 1**: 4/5/6 lines (~3,000 train positions)
- **Feed A**: A/C/E lines (~1,700 train positions)
- **Feed B**: B/D/F/M lines (~1,400 train positions)
- **Feed G**: G line (~300 train positions)
- **Feed J**: J/Z lines (~300 train positions)
- **Feed L**: L line (~400 train positions)
- **Feed N**: N/Q/R/W lines (~1,900 train positions)
- **Feed SI**: Staten Island Railway (~120 train positions)

**Total**: ~8,000+ live train positions updated every 30 seconds

## 🔍 Troubleshooting

### Common Issues

**Port already in use:**
```bash
# Kill existing processes
pkill -f uvicorn
pkill -f "next dev"
./start.sh
```

**Permission denied:**
```bash
chmod +x setup.sh start.sh
```

**Python/Node not found:**
- Run `./setup.sh` again - it will install missing dependencies

**Database issues:**
```bash
# Reset database
rm -f backend/subway_monitor.db
./start.sh
```

### Logs
- Backend logs: Real-time in terminal
- Database file: `backend/subway_monitor.db`
- Virtual environment: `backend/venv/`

## 🌟 Key Improvements from Docker Version

1. **No Docker dependency** - Runs natively on all platforms
2. **Faster startup** - No container overhead
3. **Easier development** - Direct file access and debugging
4. **Automatic dependency management** - Setup script handles everything
5. **Cross-platform compatibility** - Works on Windows, macOS, Linux
6. **Simplified deployment** - Just run two scripts

## 📝 License

This project is licensed under the MIT License.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally with `./setup.sh --minimal && ./start.sh`
5. Submit a pull request

## 📞 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the API documentation at http://localhost:8000/api/v1/docs
3. Open an issue on GitHub

---

**Made with ❤️ for NYC subway riders**