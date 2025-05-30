# NYC Subway Monitor 🚇

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?style=for-the-badge&logo=fastapi)
![Next.js](https://img.shields.io/badge/Next.js-15.2-black?style=for-the-badge&logo=next.js)
![TypeScript](https://img.shields.io/badge/TypeScript-5.5-blue?style=for-the-badge&logo=typescript)
![Docker](https://img.shields.io/badge/Docker-Compose-blue?style=for-the-badge&logo=docker)
![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-orange?style=for-the-badge&logo=github-actions)

**Real-time anomaly detection for NYC subway operations using ML models and streaming data**

[Demo](https://subway-monitor.demo) • [Documentation](./docs) • [API Reference](./docs/api)

</div>

## 🎯 Overview

NYC Subway Monitor ingests real-time GTFS-RT feeds from the MTA, engineers time-series features, and uses machine learning to detect operational anomalies. The system provides a live dashboard with interactive maps and timeline visualizations.

### Key Features

- **Real-time Data Ingestion**: Async polling of public MTA GTFS-RT feeds (no API key required)
- **ML-Powered Detection**: Isolation Forest + LSTM autoencoder ensemble
- **Interactive Dashboard**: Mapbox-powered visualization with WebSocket streaming
- **Production-Ready**: Docker, CI/CD, monitoring, and horizontal scaling support

## 🏗️ Architecture

```mermaid
graph TB
    subgraph "Data Sources"
        MTA[MTA GTFS-RT Feeds]
    end
    
    subgraph "Backend Services"
        API[FastAPI Server]
        WS[WebSocket Server]
        ML[ML Pipeline]
        DB[(TimescaleDB)]
        Redis[(Redis Cache)]
    end
    
    subgraph "ML Models"
        IF[Isolation Forest]
        LSTM[LSTM Autoencoder]
    end
    
    subgraph "Frontend"
        Next[Next.js App]
        Map[Mapbox GL]
        D3[D3 Timeline]
    end
    
    MTA -->|Async Fetch| API
    API --> DB
    API --> Redis
    API --> ML
    ML --> IF
    ML --> LSTM
    API --> WS
    WS -->|Real-time| Next
    Next --> Map
    Next --> D3
🚀 Quick Start
Prerequisites

Docker & Docker Compose
Node.js 20+ (for local development)
Python 3.12+ (for local development)
Mapbox API token (free tier works)

1. Clone and Setup
bashgit clone https://github.com/your-org/nyc-subway-monitor.git
cd nyc-subway-monitor

# Copy environment variables
cp .env.example .env

# Add your Mapbox token to .env
echo "MAPBOX_TOKEN=your_mapbox_token_here" >> .env
2. Start Services
bash# Start all services
docker-compose up --build

# Or run individually
docker-compose up -d timescaledb redis  # Start databases
cd backend && uvicorn app.main:app --reload  # Start backend
cd frontend && npm run dev  # Start frontend
3. Access Dashboard

Dashboard: http://localhost:3000
API Docs: http://localhost:8000/api/v1/docs
Grafana: http://localhost:3001 (admin/admin)
Prometheus: http://localhost:9090

📊 ML Models
Isolation Forest

Fast unsupervised anomaly detection
Handles multimodal distributions
5% contamination rate
Features: headway, dwell time, delays

LSTM Autoencoder

Captures temporal patterns
Sequence length: 24 time steps
Architecture: 128 → 64 → 32 → 64 → 128
Threshold: 95th percentile reconstruction error

🔌 API Reference
REST Endpoints
bash# Get anomalies
GET /api/v1/anomalies?line=6&start_date=2024-01-01

# Get train positions
GET /api/v1/feeds/positions/nqrw

# Trigger detection
POST /api/v1/anomalies/detect
WebSocket
javascript// Subscribe to anomalies
ws.send({
  type: 'subscribe',
  filters: { line: '6', severity_min: 0.7 }
})
🧪 Testing
bash# Backend tests
cd backend
pytest --cov=app

# Frontend tests
cd frontend
npm test

# E2E tests
npm run test:e2e
📈 Performance

Ingestion rate: ~1000 updates/second
Detection latency: <100ms p99
Dashboard FPS: 60 (GPU accelerated)
Storage: ~50GB/month with 7-day retention

🚢 Deployment
Kubernetes
bash# Apply manifests
kubectl apply -f k8s/manifests/

# Check status
kubectl get pods -n subway-monitor
Environment Variables
VariableDescriptionDefaultPOSTGRES_HOSTTimescaleDB hostlocalhostREDIS_URLRedis connection URLredis://localhost:6379FEED_UPDATE_INTERVALSeconds between fetches30MODEL_RETRAIN_HOURHour to retrain models (UTC)3
🤝 Contributing

Fork the repository
Create a feature branch (git checkout -b feat/amazing-feature)
Commit changes using conventional commits
Push to branch (git push origin feat/amazing-feature)
Open a Pull Request

📝 License
MIT License - see LICENSE file
🙏 Acknowledgments

MTA for public GTFS-RT feeds
nyctrains package maintainers
TimescaleDB for time-series optimization


<div align="center">
Built with ❤️ for NYC's 4.5 million daily riders
</div>
```