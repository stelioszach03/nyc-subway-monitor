# NYC Subway Monitor

A real-time monitoring system for the New York City Subway, providing live train positions, delay information, and anomaly detection.

## Architecture

- **Data Ingestion**: Pulls GTFS-RT Subway feeds every 30 seconds
- **Streaming Pipeline**: Processes data with Apache Kafka and Spark Structured Streaming
- **Storage**: Uses PostgreSQL with TimescaleDB for time-series data and Redis for real-time cache
- **Machine Learning**: Anomaly detection with Isolation Forest, exported to ONNX
- **API**: FastAPI for REST endpoints and WebSocket streaming
- **Frontend**: React 19 with Mapbox GL for visualization

## Directory Structure
nyc-subway-monitor/
├── infra/                 # Infrastructure configuration
│   ├── docker/            # Docker Compose for local dev
│   ├── helm/              # Helm charts for Kubernetes
│   └── k8s/               # Kubernetes manifests
├── services/              # Backend services
│   ├── ingest/            # GTFS feed ingestion service
│   ├── stream/            # Spark streaming pipeline
│   ├── ml/                # Machine learning service
│   └── api/               # FastAPI gateway
├── web/                   # React frontend
├── docs/                  # Documentation
└── docker/                # Docker-related files

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Node.js 22.4.0 LTS
- Python 3.11.12
- A Mapbox API token (free tier)

### Environment Variables

Create a `.env` file in the `infra/docker` directory based on the provided `.env.sample`:
Database
POSTGRES_USER=subway
POSTGRES_PASSWORD=subway_password
POSTGRES_DB=subway_monitor
Frontend
MAPBOX_TOKEN=your_mapbox_token_here
Services
LOG_LEVEL=INFO
ML
MODEL_PATH=/app/models/anomaly_model.onnx

### Local Development

1. Build and start the services:

```bash
cd nyc-subway-monitor/infra/docker
docker-compose up -d

Access the frontend at http://localhost:3000
Access the API documentation at http://localhost:8000/docs
Access Grafana dashboards at http://localhost:3001 (admin/admin)
Access Airflow at http://localhost:8080 (airflow/airflow)

Development Workflow

Start the services using Docker Compose
Develop the frontend:

bashcd nyc-subway-monitor/web
pnpm install
pnpm dev

Make changes to Python services and rebuild:

bashcd nyc-subway-monitor/infra/docker
docker-compose build <service_name>
docker-compose up -d <service_name>
Deployment
Kubernetes Deployment

Update the Helm values in infra/helm/values.yaml
Deploy using Helm:

bashcd nyc-subway-monitor/infra/helm
helm upgrade --install subway-monitor . -f values.yaml
CI/CD Pipeline
The project includes GitHub Actions workflows for:

Linting and testing
Building Docker images
Pushing to GitHub Container Registry
Deploying to Kubernetes via Argo CD

API Documentation

/trains - Get current train positions
/alerts - Get anomaly alerts
/metrics - Get performance metrics
/ws/live - WebSocket for real-time updates

Architecture Details
Feeds and Data Sources
MTA GTFS-RT feeds (no API key required):

123456: https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs
ACE: https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace
BDFM: https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm
G: https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g
JZ: https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz
NQRW: https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw
L: https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l
7: https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-7
SIR: https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-si

Machine Learning

Nightly retraining of the anomaly detection model
Uses 7 days of historical data for training
Anomaly scores published to API and WebSocket

License
MIT License

## Data Ingestion Service

Finally, let's create the data ingestion service:

```python
# nyc-subway-monitor/services/ingest/main.py
import os
import time
import json
import logging
import requests
import schedule
from typing import Dict, List, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import asyncio

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2
from kafka import KafkaProducer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('subway-ingest')

# Configuration from environment variables
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "subway-feeds")
FETCH_INTERVAL = int(os.environ.get("FETCH_INTERVAL", "30"))  # seconds

# MTA GTFS-RT feed URLs
FEED_URLS = {
    '123456': 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs',
    'ACE': 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace',
    'BDFM': 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm',
    'G': 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g',
    'JZ': 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz',
    'NQRW': 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw',
    'L': 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l',
    '7': 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-7',
    'SIR': 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-si'
}

def init_kafka_producer() -> KafkaProducer:
    """Initialize and return a Kafka producer."""
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

def fetch_feed(feed_id: str, url: str) -> List[Dict[str, Any]]:
    """Fetch and parse a GTFS-RT feed."""
    try:
        logger.info(f"Fetching feed {feed_id} from {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        
        trains = []
        timestamp = datetime.fromtimestamp(feed.header.timestamp)
        
        for entity in feed.entity:
            if entity.HasField('trip_update'):
                trip_update = entity.trip_update
                route_id = trip_update.trip.route_id
                trip_id = trip_update.trip.trip_id
                
                # Process stop time updates for delay information
                for stop_update in trip_update.stop_time_update:
                    delay = None
                    if stop_update.HasField('arrival') and stop_update.arrival.HasField('delay'):
                        delay = stop_update.arrival.delay
                    elif stop_update.HasField('departure') and stop_update.departure.HasField('delay'):
                        delay = stop_update.departure.delay
                    
                    trains.append({
                        'feed_id': feed_id,
                        'trip_id': trip_id,
                        'route_id': route_id,
                        'stop_id': stop_update.stop_id,
                        'stop_sequence': stop_update.stop_sequence,
                        'delay': delay,
                        'timestamp': timestamp.isoformat()
                    })
            
            if entity.HasField('vehicle'):
                vehicle = entity.vehicle
                route_id = vehicle.trip.route_id
                trip_id = vehicle.trip.trip_id
                
                # Process vehicle position
                if vehicle.HasField('position'):
                    trains.append({
                        'feed_id': feed_id,
                        'trip_id': trip_id,
                        'route_id': route_id,
                        'latitude': vehicle.position.latitude,
                        'longitude': vehicle.position.longitude,
                        'current_status': gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.Name(vehicle.current_status),
                        'current_stop_sequence': vehicle.current_stop_sequence,
                        'vehicle_id': vehicle.vehicle.id if vehicle.HasField('vehicle') else None,
                        'timestamp': timestamp.isoformat(),
                        'direction_id': vehicle.trip.direction_id if vehicle.trip.HasField('direction_id') else None
                    })
        
        logger.info(f"Processed {len(trains)} train updates from feed {feed_id}")
        return trains
    
    except DecodeError as e:
        logger.error(f"Failed to decode protobuf for feed {feed_id}: {e}")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch feed {feed_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error processing feed {feed_id}: {e}")
        return []

def fetch_all_feeds() -> None:
    """Fetch all GTFS-RT feeds and send to Kafka."""
    producer = init_kafka_producer()
    
    def process_feed(feed_id: str, url: str) -> None:
        trains = fetch_feed(feed_id, url)
        for train in trains:
            producer.send(KAFKA_TOPIC, value=train)
    
    # Fetch feeds in parallel
    with ThreadPoolExecutor(max_workers=len(FEED_URLS)) as executor:
        for feed_id, url in FEED_URLS.items():
            executor.submit(process_feed, feed_id, url)
    
    # Ensure all messages are sent
    producer.flush()
    logger.info(f"Completed fetching all feeds at {datetime.now().isoformat()}")

def start_scheduled_fetching() -> None:
    """Start scheduled fetching of feeds."""
    logger.info(f"Starting scheduled feed fetching every {FETCH_INTERVAL} seconds")
    
    # Run immediately on startup
    fetch_all_feeds()
    
    # Schedule regular runs
    schedule.every(FETCH_INTERVAL).seconds.do(fetch_all_feeds)
    
    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    logger.info("NYC Subway Monitor - Feed Ingestion Service starting up")
    start_scheduled_fetching()
Requirements for ingest service:
# nyc-subway-monitor/services/ingest/requirements.txt
kafka-python==2.0.2
requests==2.31.0
protobuf==4.25.1
schedule==1.2.1
gtfs-realtime-bindings==1.0.0
And its Dockerfile:
dockerfile# nyc-subway-monitor/services/ingest/Dockerfile
FROM python:3.11.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
This completes the core components of the NYC Subway Monitor system. The application now includes:

Data ingestion from MTA GTFS feeds
Spark streaming pipeline for processing
ML service for anomaly detection
FastAPI backend with REST and WebSocket endpoints
React 19 frontend with Mapbox visualization
Docker Compose for local development
Kubernetes/Helm configuration for production
Airflow DAG for nightly ML model training

The system follows the specified architecture and requirements, using all the specified technologies and versions. The code is type-annotated, follows modern best practices, and is structured for maintainability and scalability.