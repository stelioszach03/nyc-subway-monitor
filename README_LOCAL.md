# NYC Subway Monitor - Local Development Setup

This guide will help you set up and run the NYC Subway Monitor locally on Windows, macOS, or Linux without Docker.

## 🚀 Quick Start

### 1. Clone and Setup
```bash
git clone https://github.com/stelioszach03/nyc-subway-monitor.git
cd nyc-subway-monitor
chmod +x setup.sh
./setup.sh
```

### 2. Start the Application
```bash
chmod +x start.sh
./start.sh
```

### 3. Access the Application
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## 📋 Prerequisites

The setup script will automatically install these dependencies, but you can install them manually if needed:

### All Platforms
- **Python 3.9+** with pip
- **Node.js 18+** with npm
- **Git**

### Platform-Specific
- **macOS**: Homebrew (for package management)
- **Linux**: Package manager (apt, yum, etc.)
- **Windows**: Git Bash or WSL recommended

## 🛠 Manual Setup (Alternative)

If you prefer to set up manually:

### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Frontend Setup
```bash
cd frontend
npm install
```

### Database Setup
The application now uses SQLite by default, which requires no additional setup. The database file will be created automatically at `backend/subway_monitor.db`.

## 🔧 Configuration

### Environment Variables
Create a `.env` file in the backend directory:

```bash
# Database (SQLite - default)
DATABASE_URL=sqlite+aiosqlite:///./subway_monitor.db

# API Configuration
DEBUG=true
CORS_ORIGINS=["http://localhost:3000"]

# MTA API (optional - for live data)
MTA_API_KEY=your_mta_api_key_here

# Mapbox (optional - for maps)
NEXT_PUBLIC_MAPBOX_TOKEN=your_mapbox_token_here
```

### Live Data Setup
To get live subway data:

1. Get an MTA API key from [MTA Developer Resources](https://api.mta.info/)
2. Add it to your `.env` file as `MTA_API_KEY`
3. The application will automatically start fetching live data

## 📁 Project Structure

```
nyc-subway-monitor/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── main.py         # Application entry point
│   │   ├── config.py       # Configuration
│   │   ├── db/             # Database models and connection
│   │   ├── ml/             # Machine learning models
│   │   ├── routers/        # API endpoints
│   │   └── utils/          # Utilities (including in-memory cache)
│   ├── requirements.txt    # Python dependencies
│   └── subway_monitor.db   # SQLite database (created automatically)
├── frontend/               # Next.js frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── pages/          # Next.js pages
│   │   └── utils/          # Frontend utilities
│   ├── package.json        # Node.js dependencies
│   └── next.config.mjs     # Next.js configuration
├── logs/                   # Application logs
├── setup.sh               # Automated setup script
├── start.sh               # Application startup script
└── README_LOCAL.md        # This file
```

## 🔍 Troubleshooting

### Common Issues

#### Port Already in Use
```bash
# Kill processes on ports 3000 and 8000
lsof -ti:3000 | xargs kill -9
lsof -ti:8000 | xargs kill -9
```

#### Python Virtual Environment Issues
```bash
# Recreate virtual environment
cd backend
rm -rf venv
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Node.js Dependencies Issues
```bash
# Clear npm cache and reinstall
cd frontend
rm -rf node_modules package-lock.json
npm cache clean --force
npm install
```

#### Database Issues
```bash
# Reset database
cd backend
rm -f subway_monitor.db
python -c "
import asyncio
from app.db.database import init_db
asyncio.run(init_db())
"
```

### Logs
Check the logs for detailed error information:
- Backend: `logs/backend.log`
- Frontend: `logs/frontend.log`

### Health Checks
- Backend health: http://localhost:8000/health/live
- Backend readiness: http://localhost:8000/health/ready

## 🚇 Features

### Real-Time Data
- Live subway positions and predictions
- Service alerts and delays
- Station-by-station updates

### Machine Learning
- Anomaly detection for delays and service disruptions
- Predictive models for headway and dwell time
- Automated model training and deployment

### Visualization
- Interactive subway map
- Real-time charts and graphs
- Historical data analysis

### API
- RESTful API for all data
- WebSocket support for real-time updates
- Comprehensive API documentation

## 🔄 Development Workflow

### Starting Development
```bash
./start.sh
```

### Stopping Services
Press `Ctrl+C` in the terminal running `start.sh`

### Backend Development
```bash
cd backend
source venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Development
```bash
cd frontend
npm run dev
```

### Running Tests
```bash
# Backend tests
cd backend
python -m pytest

# Frontend tests
cd frontend
npm test
```

## 📊 Monitoring

### Metrics
- Prometheus metrics: http://localhost:8000/metrics
- Application health: http://localhost:8000/health/ready

### Performance
- Database queries are optimized for SQLite
- In-memory caching for improved performance
- Efficient real-time data processing

## 🔒 Security

### Local Development
- CORS configured for localhost
- Debug mode enabled by default
- No authentication required for local development

### Production Considerations
- Set `DEBUG=false` in production
- Configure proper CORS origins
- Add authentication and authorization
- Use PostgreSQL for production database
- Use Redis for production caching

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally using `./start.sh`
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

If you encounter any issues:

1. Check the troubleshooting section above
2. Review the logs in the `logs/` directory
3. Open an issue on GitHub with:
   - Your operating system
   - Error messages from logs
   - Steps to reproduce the issue

## 🎯 Next Steps

After getting the application running:

1. **Get MTA API Key**: For live data functionality
2. **Get Mapbox Token**: For enhanced map features
3. **Explore the API**: Visit http://localhost:8000/docs
4. **Customize Configuration**: Edit `.env` file as needed
5. **Contribute**: Help improve the project!