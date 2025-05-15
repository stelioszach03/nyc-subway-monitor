# services/ingest/main.py
import os
import time
import json
import logging
import schedule
import requests
import yaml
from datetime import datetime
from google.transit import gtfs_realtime_pb2
from kafka import KafkaProducer
from kafka.errors import KafkaTimeoutError, NoBrokersAvailable 
from sqlalchemy import create_engine, text

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Kafka settings
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = "subway-feeds"

# Database configuration
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "timescaledb")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "subway")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "subway_password")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "subway_monitor")

# ---- NEW: static stops lookup ----------------------------------
STOPS_FILE = os.environ.get("STOPS_FILE", "/app/stops.txt")
STOPS = {}
if os.path.exists(STOPS_FILE):
    import csv
    with open(STOPS_FILE, newline="", encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        for row in rdr:
            STOPS[row["stop_id"]] = (float(row["stop_lat"]), float(row["stop_lon"]))
    logger.info(f"Loaded {len(STOPS):,} GTFS stops from {STOPS_FILE}")
else:
    logger.warning(f"GTFS stops file not found at {STOPS_FILE}; TripUpdates will get dummy coords")
# ----------------------------------------------------------------

def create_kafka_producer():
    """Create and return a Kafka producer with retry."""
    max_retries = 10
    retry_backoff = 5  # seconds
    
    for retry in range(max_retries):
        try:
            logger.info(f"Attempting to create Kafka producer (attempt {retry+1}/{max_retries})...")
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda x: json.dumps(x).encode('utf-8'),
                retries=5,
                acks='all',
                request_timeout_ms=30000,
                max_block_ms=60000,
                retry_backoff_ms=1000
            )
            # Test connection
            producer.list_topics(timeout_ms=10000)
            logger.info("Successfully connected to Kafka")
            return producer
        except (KafkaTimeoutError, NoBrokersAvailable) as e:
            logger.warning(f"Kafka connection failed (attempt {retry+1}): {e}")
            if retry < max_retries - 1:
                logger.info(f"Retrying in {retry_backoff} seconds...")
                time.sleep(retry_backoff)
                retry_backoff = min(30, retry_backoff * 2)  # Exponential backoff up to 30 seconds
            else:
                logger.error(f"Failed to create Kafka producer after {max_retries} attempts")
                logger.warning("Will continue without Kafka and store data directly to database")
                return None
        except Exception as e:
            logger.error(f"Unexpected error creating Kafka producer: {e}")
            if retry < max_retries - 1:
                logger.info(f"Retrying in {retry_backoff} seconds...")
                time.sleep(retry_backoff)
                retry_backoff = min(30, retry_backoff * 2)
            else:
                logger.error(f"Failed to create Kafka producer after {max_retries} attempts")
                return None

def create_db_engine():
    """Create database engine for historical data storage."""
    try:
        db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
        return create_engine(db_url, pool_size=5, max_overflow=10)
    except Exception as e:
        logger.error(f"Failed to create database engine: {e}")
        return None

def load_feeds_config():
    """Load the feeds configuration from YAML file."""
    try:
        with open('/app/feeds.yaml', 'r') as f:
            config = yaml.safe_load(f)
            return config['feeds']
    except Exception as e:
        logger.error(f"Failed to load feeds configuration: {e}")
        return []

def fetch_gtfs_realtime_feed(feed_url, feed_name):
    """Fetch subway feed data from MTA API with improved error handling."""
    headers = {
        "User-Agent": "NYC-Subway-Monitor/1.0",
        "Accept": "application/x-protobuf"  # CRITICAL: This ensures we get binary protobuf data
    }
    try:
        logger.info(f"Fetching {feed_name} from {feed_url}")
        response = requests.get(feed_url, headers=headers, timeout=30)
        
        # Check response headers for debugging
        logger.debug(f"Response status: {response.status_code}")
        logger.debug(f"Content-Type: {response.headers.get('Content-Type', 'Not set')}")
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '').lower()
            if 'protobuf' in content_type or 'octet-stream' in content_type or 'application/' in content_type:
                logger.info(f"Successfully fetched {feed_name} - {len(response.content)} bytes")
                return response.content
            else:
                logger.warning(f"Unexpected content type for {feed_name}: {content_type}")
                # If the content looks like protobuf despite the header, try to use it anyway
                if len(response.content) > 100 and not response.content.startswith(b'<'):
                    logger.info(f"Attempting to use response despite content type mismatch")
                    return response.content
                logger.debug(f"Response preview: {response.content[:200]}")
                return None
        else:
            logger.error(f"Failed to fetch feed {feed_name}: {response.status_code}")
            if response.status_code == 403:
                logger.error(f"Response content: {response.text[:500]}")
            return None
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching feed {feed_name}")
        return None
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error fetching feed {feed_name}")
        return None
    except Exception as e:
        logger.error(f"Error fetching feed {feed_name}: {e}")
        return None

def parse_gtfs_feed(feed_data, expected_lines=None):
    """Parse GTFS-RT binary data into Python objects."""
    feed = gtfs_realtime_pb2.FeedMessage()
    
    try:
        # Validate that we have binary data
        if not isinstance(feed_data, bytes):
            logger.error("Feed data is not binary - cannot parse")
            return []
        
        # Check for common error patterns in the response
        if feed_data.startswith(b'<?xml'):
            logger.error("Received XML response instead of protobuf - likely wrong URL or error response")
            logger.error(f"Feed content sample: {feed_data[:200]}")
            return []
        
        feed.ParseFromString(feed_data)
        logger.debug(f"Successfully parsed feed with {len(feed.entity)} entities")
        
        # Count entity types for debugging
        vehicle_count = 0
        trip_update_count = 0
        alert_count = 0
        
        vehicles = []
        for entity in feed.entity:
            # Parse VehiclePosition entities (might not be present in subway feeds)
            if entity.HasField('vehicle'):
                vehicle = entity.vehicle
                vehicle_count += 1
                
                # Extract vehicle position data
                if vehicle.HasField('position') and vehicle.HasField('trip'):
                    # Filter by expected lines if provided
                    if expected_lines and vehicle.trip.route_id not in expected_lines:
                        continue
                    
                    # Basic validation
                    if not vehicle.trip.route_id:
                        continue
                        
                    # Parse timestamp
                    ts = datetime.fromtimestamp(vehicle.timestamp)
                    
                    # Create vehicle data object
                    vehicle_data = {
                        "type": "vehicle_position",
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
            
            # Parse TripUpdate entities (main entity type for MTA subway feeds)
            if entity.HasField('trip_update'):
                trip_update = entity.trip_update
                trip_update_count += 1
                
                # Basic validation
                if not trip_update.trip.route_id:
                    continue
                
                # Filter by expected lines if provided
                if expected_lines and trip_update.trip.route_id not in expected_lines:
                    continue
                
                # Get timestamp
                update_ts = datetime.now()
                if trip_update.HasField('timestamp'):
                    update_ts = datetime.fromtimestamp(trip_update.timestamp)
                
                # Process stop time updates
                for stop_update in trip_update.stop_time_update:
                    # Get delay information
                    delay = None
                    arrival_time = None
                    departure_time = None
                    
                    if stop_update.HasField('arrival'):
                        arrival_time = stop_update.arrival.time
                        if stop_update.arrival.HasField('delay'):
                            delay = stop_update.arrival.delay
                    
                    if stop_update.HasField('departure'):
                        departure_time = stop_update.departure.time
                        if stop_update.departure.HasField('delay') and delay is None:
                            delay = stop_update.departure.delay
                    
                    # Αν δεν υπάρχει delay, θεωρούμε 0
                    if delay is None:
                        delay = 0
                    
                    # Create a vehicle-like object for compatibility with existing code
                    train_data = {
                        "type": "trip_update",
                        "trip_id": trip_update.trip.trip_id,
                        "route_id": trip_update.trip.route_id,
                        "timestamp": update_ts.isoformat(),
                        "stop_id": stop_update.stop_id,
                        "stop_sequence": stop_update.stop_sequence,
                        "delay": delay,
                        "arrival_time": arrival_time,
                        "departure_time": departure_time,
                        "current_status": "SCHEDULED",  # Default status
                        "vehicle_id": trip_update.vehicle.id if trip_update.HasField('vehicle') else "unknown",
                        "direction_id": trip_update.trip.direction_id if trip_update.trip.HasField('direction_id') else 0
                    }
                    
                    # For compatibility with existing code that expects lat/lon
                    if stop_update.stop_id in STOPS:
                        train_data["latitude"], train_data["longitude"] = STOPS[stop_update.stop_id]
                    else:
                        # fallback για άγνωστο stop_id
                        train_data["latitude"] = 40.7128
                        train_data["longitude"] = -74.006
                    
                    vehicles.append(train_data)
            
            # Count alerts for debugging
            if entity.HasField('alert'):
                alert_count += 1
        
        logger.debug(f"Entity types in feed: vehicles={vehicle_count}, trip_updates={trip_update_count}, alerts={alert_count}")
        logger.info(f"Extracted {len(vehicles)} updates from feed")
        return vehicles
    except Exception as e:
        logger.error(f"Error parsing GTFS feed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Log some debug info about the feed data
        if isinstance(feed_data, bytes):
            logger.error(f"Feed data preview: {feed_data[:100]}")
        return []

def store_historical_data(vehicles, db_engine):
    """Store raw vehicle data for historical analysis and model training."""
    if not vehicles or not db_engine:
        return
    
    try:
        # Create table if not exists
        create_table_query = """
        CREATE TABLE IF NOT EXISTS train_history (
            id SERIAL PRIMARY KEY,
            trip_id VARCHAR(50),
            route_id VARCHAR(10), 
            timestamp TIMESTAMP NOT NULL,
            latitude FLOAT,
            longitude FLOAT,
            current_status VARCHAR(50),
            delay INTEGER,
            vehicle_id VARCHAR(50),
            stop_id VARCHAR(20),
            created_at TIMESTAMP DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_train_history_timestamp ON train_history(timestamp);
        CREATE INDEX IF NOT EXISTS idx_train_history_route_id ON train_history(route_id);
        """
        
        with db_engine.connect() as conn:
            conn.execute(text(create_table_query))
            conn.commit()
            
            # Insert historical data
            for vehicle in vehicles:
                insert_query = """
                INSERT INTO train_history (trip_id, route_id, timestamp, latitude, longitude, current_status, delay, vehicle_id, stop_id)
                VALUES (:trip_id, :route_id, :timestamp, :latitude, :longitude, :current_status, :delay, :vehicle_id, :stop_id)
                """
                conn.execute(text(insert_query), {
                    'trip_id': vehicle['trip_id'],
                    'route_id': vehicle['route_id'],
                    'timestamp': vehicle['timestamp'],
                    'latitude': vehicle['latitude'],
                    'longitude': vehicle['longitude'],
                    'current_status': vehicle['current_status'],
                    'delay': vehicle.get('delay', 0),
                    'vehicle_id': vehicle['vehicle_id'],
                    'stop_id': vehicle.get('stop_id', None)
                })
            conn.commit()
        
        logger.info(f"Stored {len(vehicles)} historical records")
    except Exception as e:
        logger.error(f"Error storing historical data: {e}")
        import traceback
        logger.error(traceback.format_exc())

# Βελτιωμένη συνάρτηση δημιουργίας θέματος Kafka
def ensure_kafka_topic_exists():
    """Ensure the Kafka topic exists."""
    import subprocess
    
    try:
        cmd = [
            "kafka-topics", 
            "--create", 
            "--if-not-exists",
            "--bootstrap-server", KAFKA_BOOTSTRAP_SERVERS,
            "--replication-factor", "1",
            "--partitions", "1",
            "--topic", KAFKA_TOPIC
        ]
        
        # Προσπάθεια εκτέλεσης της εντολής
        logger.info(f"Ensuring Kafka topic {KAFKA_TOPIC} exists...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"Kafka topic {KAFKA_TOPIC} is ready")
            return True
        else:
            logger.warning(f"Failed to create Kafka topic: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error ensuring Kafka topic: {e}")
        return False

def ingest_realtime_feeds():
    """Fetch, parse, and publish subway data to Kafka."""
    # Ensure Kafka topic exists
    ensure_kafka_topic_exists()
    
    producer = create_kafka_producer()
    db_engine = create_db_engine()
    
    if not db_engine:
        logger.error("Cannot proceed without database connection")
        return
    
    feeds = load_feeds_config()
    if not feeds:
        logger.error("No feeds configured in feeds.yaml")
        return
        
    realtime_feeds = [f for f in feeds if f.get('type') == 'realtime']
    
    if not realtime_feeds:
        logger.warning("No realtime feeds configured")
        return
    
    all_vehicles = []
    
    for feed in realtime_feeds:
        logger.info(f"Processing feed: {feed['name']}")
        
        # Fetch feed
        feed_data = fetch_gtfs_realtime_feed(feed['url'], feed['name'])
        if not feed_data:
            logger.warning(f"Skipping feed {feed['name']} - no data received")
            continue
            
        # Parse feed
        expected_lines = feed.get('lines', [])
        vehicles = parse_gtfs_feed(feed_data, expected_lines)
        
        if vehicles:
            logger.info(f"Parsed {len(vehicles)} vehicles/trips from feed {feed['name']}")
            
            # Publish to Kafka if available
            if producer:
                for vehicle in vehicles:
                    try:
                        producer.send(KAFKA_TOPIC, value=vehicle)
                    except Exception as e:
                        logger.error(f"Error sending to Kafka: {e}")
            
            # Collect for historical storage
            all_vehicles.extend(vehicles)
        else:
            logger.warning(f"No vehicles/trips found in feed {feed['name']}")
    
    # Store historical data
    if db_engine and all_vehicles:
        store_historical_data(all_vehicles, db_engine)
    elif not all_vehicles:
        logger.warning("No vehicles/trips parsed from any feed")
    
    # Make sure all messages are sent
    if producer:
        producer.flush()
        producer.close()
    logger.info(f"Feed ingestion completed - processed {len(all_vehicles)} total vehicles/trips")

def run_scheduled_task():
    """Run the ingestion process on schedule."""
    logger.info("Running scheduled feed ingestion")
    try:
        ingest_realtime_feeds()
    except Exception as e:
        logger.error(f"Error in scheduled task: {e}")
        import traceback
        logger.error(traceback.format_exc())

def main():
    """Main entry point."""
    logger.info("NYC Subway Monitor - Enhanced Ingest Service Starting")
    logger.info(f"Log level: {os.environ.get('LOG_LEVEL', 'INFO')}")
    
    # Validate configuration
    feeds = load_feeds_config()
    if not feeds:
        logger.error("No feeds configured in feeds.yaml! Please add feed configurations.")
        # Create a dummy feed configuration if none exists
        try:
            with open('/app/feeds.yaml', 'w') as f:
                f.write("""# NYC MTA Subway Feeds Configuration
feeds:
  # Real-time GTFS-RT feeds by line group
  - name: "ACE Lines"
    type: "realtime"
    url: "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace"
    lines: ["A", "C", "E"]
    frequency: "30s"
    
  - name: "BDFM Lines"
    type: "realtime"  
    url: "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm"
    lines: ["B", "D", "F", "M"]
    frequency: "30s"
""")
            logger.info("Created default feeds.yaml file with sample MTA feeds")
            feeds = load_feeds_config()
        except Exception as e:
            logger.error(f"Failed to create default feeds.yaml: {e}")
            return
    
    logger.info(f"Loaded {len(feeds)} feed configurations")
    
    # Ensure Kafka topic exists
    ensure_kafka_topic_exists()
    
    # For testing, run once immediately
    logger.info("Running initial ingestion...")
    run_scheduled_task()
    
    # Schedule to run every 30 seconds
    schedule.every(30).seconds.do(run_scheduled_task)
    
    # Keep the process running
    logger.info("Starting scheduler loop...")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()