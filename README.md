# NYC Subway Monitor

A real-time monitoring system for the New York City subway system with machine learning-based anomaly detection for identifying unusual delays and service disruptions.

![NYC Subway Monitor Dashboard](https://i.imgur.com/zCLfIV8.png)

## Overview

The NYC Subway Monitor is a comprehensive system that:

- **Captures real-time data** from MTA's GTFS-RT feeds
- **Processes and analyzes** subway train positions and delays
- **Detects anomalies** using machine learning
- **Visualizes** trains on an interactive map
- **Alerts** on detected service disruptions
- **Provides metrics** on system performance

The system continuously trains its anomaly detection model to improve accuracy over time. It's designed to run as a set of interconnected microservices using Docker containers for easy deployment.

## Architecture

![Architecture Diagram](https://i.imgur.com/kJLfIV8.png)

The system consists of several components:

- **Web Frontend**: React-based UI for visualization (port 3000)
- **API Service**: FastAPI backend providing data to the frontend (port 8000)
- **ML Service**: Provides anomaly detection using isolation forest (port 8001)
- **Ingest Service**: Collects data from MTA GTFS-RT feeds and publishes to Kafka
- **Stream Processing**: Processes and analyzes data using Spark
- **Trainer Service**: Periodically trains the anomaly detection model
- **Supporting Infrastructure**:
  - Kafka: Message broker for data streaming
  - TimescaleDB: Time-series database for historical data
  - Redis: In-memory store for real-time data and pub/sub

## Features

- **Live Map**: Real-time positions of all active subway trains
- **Delay Monitoring**: Track and visualize delays across all subway lines
- **Anomaly Detection**: ML-powered identification of unusual delays
- **Alert System**: Real-time notifications for potential issues
- **Performance Metrics**: Dashboard showing system-wide statistics
- **Continuous Learning**: Model improves over time with new data

## Quick Start

### Prerequisites

- Docker and Docker Compose
- 4GB+ RAM available
- 10GB+ disk space

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/nyc-subway-monitor.git
   cd nyc-subway-monitor/infra/docker
   ```

2. Start the system:
   ```bash
   ./start.sh
   ```

3. Access the application:
   - Web UI: http://localhost:3000
   - API: http://localhost:8000
   - ML Service: http://localhost:8001

The system will automatically fetch subway data, process it, train the anomaly detection model, and present results on the dashboard.

### System Health

Check the system's health:
```bash
./check-health.sh
```

## Configuration

### Environment Variables

Key configurations are managed through environment variables in `.env`:

- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`: Database credentials
- `MAPBOX_TOKEN`: Token for map visualization
- `VITE_API_URL`: API endpoint for frontend
- `LOG_LEVEL`: Logging verbosity (INFO, DEBUG, WARNING, ERROR)

### Feed Configuration

MTA GTFS-RT feed settings are in `infra/docker/feeds.yaml`:

```yaml
feeds:
  - name: "ACE Lines"
    type: "realtime"
    url: "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace"
    lines: ["A", "C", "E"]
    frequency: "30s"
  # Additional feeds...
```

### Docker Resources

Adjust resource limits in `docker-compose.yaml` based on your machine's capabilities.

## Development

### Project Structure

```
nyc-subway-monitor/
├── infra/
│   ├── docker/          # Docker setup & scripts
│   ├── helm/            # Kubernetes helm charts
│   └── k8s/             # Kubernetes manifests
├── services/
│   ├── api/             # FastAPI backend
│   ├── ingest/          # Data ingestion service
│   ├── ml/              # Machine learning service
│   ├── stream/          # Stream processing
│   └── trainer/         # Model training service
└── web/                 # React frontend
```

### Building Components

Individual services can be built with:

```bash
cd services/[service-name]
docker build -t subway-[service-name] .
```

### Testing

Each service has its own test suite:

```bash
cd services/[service-name]
python -m pytest
```

## Machine Learning

The system uses an Isolation Forest algorithm to detect anomalies in subway delays:

1. **Feature Engineering**:
   - Average delay per route
   - Maximum delay
   - Delay standard deviation
   - Number of trains per route
   - Time-based features (hour, day of week)

2. **Training**:
   - Occurs automatically every 2 hours
   - Uses historical data from TimescaleDB
   - Model and parameters saved to shared volume

3. **Inference**:
   - Real-time scoring of current subway conditions
   - Scores range from 0-1 (higher = more anomalous)
   - Visualized in the metrics dashboard

## Troubleshooting

### Common Issues

1. **Services fail to start**:
   ```bash
   docker compose logs [service-name]
   docker compose restart [service-name]
   ```

2. **No data appearing**:
   - Check MTA feed status: `docker compose logs ingest`
   - Verify Kafka connections: `docker compose logs kafka`

3. **Model not training**:
   - Check trainer logs: `docker compose logs trainer`
   - Manually create initial model: `./create_onnx_model.sh`

4. **High resource usage**:
   - Adjust resources in docker-compose.yaml
   - Run `docker system prune` to clear unused resources

### Complete Reset

To completely reset the system:

```bash
docker compose down -v  # Removes all data
./start.sh
```

## Contributing

Contributions are welcome! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- MTA for providing GTFS-RT feeds
- MapBox for mapping capabilities
- All open-source libraries used in this project