# services/ingest/main.py
import os
import time
import json
import logging
import schedule
import requests
from datetime import datetime
from google.transit import gtfs_realtime_pb2
from kafka import KafkaProducer

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# MTA API settings - NO KEY REQUIRED!
MTA_FEED_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"
MTA_FEEDS = [
    "1", "2", "11", "16", "21", "26", "31", "36", "51"  # Different subway line feeds
]

# Kafka settings
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = "subway-feeds"

def create_kafka_producer():
    """Create and return a Kafka producer."""
    try:
        return KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda x: json.dumps(x).encode('utf-8'),
            retries=5,
            acks='all',
            request_timeout_ms=30000,
            max_block_ms=30000,
            retry_backoff_ms=1000
        )
    except Exception as e:
        logger.error(f"Failed to create Kafka producer: {e}")
        return None

def fetch_mta_feed(feed_id):
    """Fetch subway feed data from MTA API - NO KEY REQUIRED!"""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; NYC-Subway-Monitor/1.0)"
    }
    try:
        url = f"{MTA_FEED_URL}-{feed_id}"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.content
        else:
            logger.error(f"Failed to fetch feed {feed_id}: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error fetching feed {feed_id}: {e}")
        return None

def parse_gtfs_feed(feed_data):
    """Parse GTFS-RT binary data into Python objects."""
    feed = gtfs_realtime_pb2.FeedMessage()
    
    try:
        feed.ParseFromString(feed_data)
        
        vehicles = []
        for entity in feed.entity:
            if entity.HasField('vehicle'):
                vehicle = entity.vehicle
                
                # Extract vehicle position data
                if vehicle.HasField('position') and vehicle.HasField('trip'):
                    # Basic validation
                    if not vehicle.trip.route_id:
                        continue
                        
                    # Parse timestamp
                    ts = datetime.fromtimestamp(vehicle.timestamp)
                    
                    # Create vehicle data object
                    vehicle_data = {
                        "trip_id": vehicle.trip.trip_id,
                        "route_id": vehicle.trip.route_id,
                        "timestamp": ts.isoformat(),
                        "latitude": vehicle.position.latitude,
                        "longitude": vehicle.position.longitude,
                        "current_status": str(vehicle.current_status),
                        "current_stop_sequence": vehicle.current_stop_sequence if vehicle.HasField('current_stop_sequence') else None,
                        "delay": vehicle.delay if vehicle.HasField('delay') else None,
                        "vehicle_id": vehicle.vehicle.id if vehicle.HasField('vehicle') else "unknown",
                        "direction_id": vehicle.trip.direction_id if vehicle.trip.HasField('direction_id') else 0
                    }
                    
                    vehicles.append(vehicle_data)
        
        return vehicles
    except Exception as e:
        logger.error(f"Error parsing GTFS feed: {e}")
        return []

def ingest_feeds():
    """Fetch, parse, and publish subway data to Kafka."""
    producer = create_kafka_producer()
    if not producer:
        logger.error("Cannot proceed without Kafka producer")
        return
    
    for feed_id in MTA_FEEDS:
        logger.info(f"Processing feed {feed_id}")
        
        # Fetch feed
        feed_data = fetch_mta_feed(feed_id)
        if not feed_data:
            continue
            
        # Parse feed
        vehicles = parse_gtfs_feed(feed_data)
        logger.info(f"Parsed {len(vehicles)} vehicles from feed {feed_id}")
        
        # Publish to Kafka
        for vehicle in vehicles:
            try:
                producer.send(KAFKA_TOPIC, value=vehicle)
            except Exception as e:
                logger.error(f"Error sending to Kafka: {e}")
    
    # Make sure all messages are sent
    producer.flush()
    producer.close()
    logger.info("Feed ingestion completed")

def run_scheduled_task():
    """Run the ingestion process on schedule."""
    logger.info("Running scheduled feed ingestion")
    try:
        ingest_feeds()
    except Exception as e:
        logger.error(f"Error in scheduled task: {e}")

def main():
    """Main entry point."""
    logger.info("NYC Subway Monitor - Ingest Service Starting")
    
    # For testing, run once immediately
    run_scheduled_task()
    
    # Schedule to run every 30 seconds
    schedule.every(30).seconds.do(run_scheduled_task)
    
    # Keep the process running
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()