# services/ingest/main.py
import os
import time
import json
import logging
import schedule
import requests
import yaml
from datetime import datetime
from nyct_gtfs import NYCTFeed
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

# Cache proxy configuration
CACHE_HOST = os.environ.get("CACHE_HOST", "cache")
CACHE_PORT = os.environ.get("CACHE_PORT", "80")
CACHE_URL_BASE = f"http://{CACHE_HOST}:{CACHE_PORT}"

# ---- GTFS Stops lookup ----------------------------------
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

# Feed URL mappings - original to cache
FEED_URL_MAP = {
    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace": f"{CACHE_URL_BASE}/gtfs-ace",
    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm": f"{CACHE_URL_BASE}/gtfs-bdfm",
    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g": f"{CACHE_URL_BASE}/gtfs-g",
    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz": f"{CACHE_URL_BASE}/gtfs-jz",
    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l": f"{CACHE_URL_BASE}/gtfs-l",
    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw": f"{CACHE_URL_BASE}/gtfs-nqrw",
    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs": f"{CACHE_URL_BASE}/gtfs-123456",
    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-si": f"{CACHE_URL_BASE}/gtfs-si",
}

# Feed polling frequency (in seconds)
FEED_POLL_FREQUENCY = {
    "ACE Lines": 5,
    "BDFM Lines": 5,
    "G Line": 5,
    "JZ Lines": 5,
    "L Line": 15,
    "NQRW Lines": 5,
    "Trip Updates (1-7)": 5,
    "Staten Island Railway": 30,
}

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
    """Fetch subway feed data from MTA API through the cache proxy."""
    # Map to cached URL if available
    cached_url = FEED_URL_MAP.get(feed_url, feed_url)
    
    headers = {
        "User-Agent": "NYC-Subway-Monitor/1.0",
        "Accept": "application/x-protobuf"  # CRITICAL: This ensures we get binary protobuf data
    }
    
    try:
        logger.info(f"Fetching {feed_name} from {cached_url}")
        response = requests.get(cached_url, headers=headers, timeout=10)  # Reduced timeout since using local cache
        
        # Check response headers for debugging
        logger.debug(f"Response status: {response.status_code}")
        logger.debug(f"Content-Type: {response.headers.get('Content-Type', 'Not set')}")
        logger.debug(f"Cache-Status: {response.headers.get('X-Cache-Status', 'Not set')}")
        
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
    try:
        f = NYCTFeed(feed_bytes=feed_data)
    except Exception as err:
        logger.error(f'NYCTFeed parse error: {err}')
        return []

    vehicles = []

    # Trip updates
    for trip in f.trips:
        if expected_lines and trip['route_id'] not in expected_lines:
            continue

        # First stop (for coordinates)
        stop_id = trip['stops'][0]['stop_id'] if trip['stops'] else None
        lat, lon = STOPS.get(stop_id, (40.7128, -74.0060))

        vehicles.append({
            "type": "trip_update",
            "trip_id": trip['trip_id'],
            "route_id": trip['route_id'],
            "timestamp": datetime.utcfromtimestamp(trip['timestamp']).isoformat(),
            "stop_id": stop_id,
            "stop_sequence": trip['stops'][0]['stop_sequence'] if trip['stops'] else None,
            "delay": trip.get('delay', 0) or 0,
            "vehicle_id": trip.get('vehicle_id', 'unknown'),
            "direction_id": trip.get('direction_id', 0),
            "latitude": lat,
            "longitude": lon,
            "current_status": trip.get('current_status', 'SCHEDULED')
        })

    # Vehicle positions
    for v in f.vehicles:
        if expected_lines and v['route_id'] not in expected_lines:
            continue

        lat = v.get('latitude', 40.7128)
        lon = v.get('longitude', -74.0060)

        vehicles.append({
            "type": "vehicle_position",
            "trip_id": v.get('trip_id'),
            "route_id": v['route_id'],
            "timestamp": datetime.utcfromtimestamp(v['timestamp']).isoformat(),
            "latitude": lat,
            "longitude": lon,
            "current_status": v.get('current_status', 'IN_TRANSIT_TO'),
            "delay": v.get('delay', 0),
            "vehicle_id": v.get('vehicle_id', 'unknown'),
            "direction_id": v.get('direction_id', 0),
        })

    logger.info(
        f"Extracted {len(f.trips)} trip_updates + {len(f.vehicles)} vehicle_positions "
        f"→ {len(vehicles)} records total")
    return vehicles

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
                    'current_status': vehicle.get('current_status', 'SCHEDULED'),
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

def process_feed(feed_name, feed_config, kafka_producer, db_engine):
    """Process a single feed based on its configuration."""
    try:
        # Extract feed details
        feed_url = feed_config['url']
        expected_lines = feed_config.get('lines', [])
        
        logger.info(f"Processing feed: {feed_name}")
        
        # Fetch feed through cache
        feed_data = fetch_gtfs_realtime_feed(feed_url, feed_name)
        if not feed_data:
            logger.warning(f"Skipping feed {feed_name} - no data received")
            return
            
        # Parse feed
        vehicles = parse_gtfs_feed(feed_data, expected_lines)
        
        if vehicles:
            logger.info(f"Parsed {len(vehicles)} vehicles/trips from feed {feed_name}")
            
            # Publish to Kafka if available
            if kafka_producer:
                for vehicle in vehicles:
                    try:
                        kafka_producer.send(KAFKA_TOPIC, value=vehicle)
                    except Exception as e:
                        logger.error(f"Error sending to Kafka: {e}")
            
            # Store for historical analysis
            if db_engine:
                store_historical_data(vehicles, db_engine)
        else:
            logger.warning(f"No vehicles/trips found in feed {feed_name}")
    except Exception as e:
        logger.error(f"Error processing feed {feed_name}: {e}")
        import traceback
        logger.error(traceback.format_exc())

def setup_feed_processing():
    """Set up scheduled feed processing based on feed configurations."""
    # Ensure Kafka topic exists
    ensure_kafka_topic_exists()
    
    # Create shared resources
    kafka_producer = create_kafka_producer()
    db_engine = create_db_engine()
    
    if not db_engine:
        logger.error("Cannot proceed without database connection")
        return False
    
    # Load feed configurations
    feeds = load_feeds_config()
    if not feeds:
        logger.error("No feeds configured in feeds.yaml")
        return False
    
    # Filter realtime feeds
    realtime_feeds = [f for f in feeds if f.get('type') == 'realtime']
    if not realtime_feeds:
        logger.warning("No realtime feeds configured")
        return False
    
    # Run initial processing for all feeds
    logger.info("Running initial processing for all feeds")
    for feed in realtime_feeds:
        process_feed(feed['name'], feed, kafka_producer, db_engine)
    
    # Close initial Kafka producer
    if kafka_producer:
        kafka_producer.flush()
        kafka_producer.close()
    
    # Schedule feeds based on their polling frequency
    for feed in realtime_feeds:
        feed_name = feed['name']
        # Determine polling frequency - use feed-specific setting or default from our mapping
        frequency = int(feed.get('frequency', '30s').rstrip('s'))
        frequency = FEED_POLL_FREQUENCY.get(feed_name, frequency)
        
        logger.info(f"Scheduling feed {feed_name} to run every {frequency} seconds")
        
        # Create a closure to capture feed config
        def create_feed_processor(feed_name, feed_config):
            def process_specific_feed():
                # Create new producer and engine for each run to ensure fresh connections
                producer = create_kafka_producer()
                engine = create_db_engine()
                
                logger.debug(f"Running scheduled processing for feed: {feed_name}")
                process_feed(feed_name, feed_config, producer, engine)
                
                # Clean up resources
                if producer:
                    producer.flush()
                    producer.close()
            
            return process_specific_feed
        
        # Schedule the feed
        schedule.every(frequency).seconds.do(create_feed_processor(feed_name, feed))
    
    return True

def main():
    """Main entry point."""
    logger.info("NYC Subway Monitor - Enhanced Ingest Service Starting")
    logger.info(f"Log level: {os.environ.get('LOG_LEVEL', 'INFO')}")
    
    # Wait for cache service to be ready
    max_retries = 10
    retry_count = 0
    while retry_count < max_retries:
        try:
            health_url = f"{CACHE_URL_BASE}/health"
            logger.info(f"Checking if cache service is ready: {health_url}")
            response = requests.get(health_url, timeout=5)
            if response.status_code == 200:
                logger.info("Cache service is ready")
                break
            else:
                logger.warning(f"Cache service returned status {response.status_code}")
        except Exception as e:
            logger.warning(f"Cache service not ready yet: {e}")
        
        retry_count += 1
        sleep_time = min(30, 2 ** retry_count)
        logger.info(f"Retrying in {sleep_time} seconds (attempt {retry_count}/{max_retries})")
        time.sleep(sleep_time)
    
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
    frequency: "5s"
    
  - name: "BDFM Lines"
    type: "realtime"  
    url: "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm"
    lines: ["B", "D", "F", "M"]
    frequency: "5s"
""")
            logger.info("Created default feeds.yaml file with sample MTA feeds")
            feeds = load_feeds_config()
        except Exception as e:
            logger.error(f"Failed to create default feeds.yaml: {e}")
            return
    
    logger.info(f"Loaded {len(feeds)} feed configurations")
    
    # Set up feed processing
    if not setup_feed_processing():
        logger.error("Failed to set up feed processing")
        return
    
    # Keep the process running
    logger.info("Starting scheduler loop...")
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Ingest service stopped by user")
    except Exception as e:
        logger.error(f"Error in scheduler loop: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()