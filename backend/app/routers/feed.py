# --- backend/app/routers/feed.py ---
"""
GTFS-RT feed ingestion router.
Handles async fetching from MTA endpoints using nyctrains package.
"""

import asyncio
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.config import get_settings
from app.db import crud
from app.db.database import get_db, AsyncSessionLocal
from app.ml.features import FeatureExtractor
from app.schemas.feed import FeedUpdateResponse, TrainPositionResponse

# Initialize logger BEFORE using it
logger = structlog.get_logger()
settings = get_settings()

try:
    from nyctrains import NYCTFeed
except ImportError:
    NYCTFeed = None
    logger.warning("nyctrains not available, will use direct protobuf parsing")

router = APIRouter()

# Feed codes for NYC subway lines
FEED_CODES = {
    "1": ["1", "2", "3", "4", "5", "6", "7", "S"],
    "A": ["A", "C", "E"],
    "B": ["B", "D", "F", "M"],
    "G": ["G"],
    "J": ["J", "Z"],
    "L": ["L"],
    "N": ["N", "Q", "R", "W"],
    "SI": ["SI"],
}

# Global lock for station creation to prevent deadlocks
station_creation_lock = asyncio.Lock()

# Lock for feed processing to ensure sequential processing
feed_processing_lock = asyncio.Lock()


def serialize_datetime(obj: Any) -> Any:
    """Convert datetime objects to ISO format strings for JSON serialization."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: serialize_datetime(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetime(item) for item in obj]
    return obj


def load_stations_from_file() -> Dict[str, Dict]:
    """Load station data from stops.txt file (GTFS static data) with multiple fallback paths."""
    stations = {}
    
    # Try multiple possible paths
    possible_paths = [
        Path("/home/stelios/nyc-subway-monitor/backend/data/stations.txt"),
        Path("data/stations.txt"),
        Path("backend/data/stations.txt"),
        Path("../backend/data/stations.txt"),
        Path("data/stops.txt"),
        Path("backend/data/stops.txt"),
    ]
    
    file_to_load = None
    for path in possible_paths:
        if path.exists():
            file_to_load = path
            break
    
    if not file_to_load:
        logger.warning("Station files not found in any of the expected locations")
        logger.warning(f"Tried paths: {[str(p) for p in possible_paths]}")
        return stations
    
    try:
        with open(file_to_load, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                stop_id = row.get('stop_id', row.get('Station ID', ''))
                
                # Handle different possible column names
                name = row.get('stop_name', row.get('Stop Name', row.get('Station Name', '')))
                lat = float(row.get('stop_lat', row.get('GTFS Latitude', row.get('Latitude', '40.7484'))))
                lon = float(row.get('stop_lon', row.get('GTFS Longitude', row.get('Longitude', '-73.9857'))))
                
                if stop_id:
                    stations[stop_id] = {
                        "name": name,
                        "lat": lat,
                        "lon": lon,
                        "lines": [],
                        "parent_station": row.get('parent_station', ''),
                        "location_type": row.get('location_type', '0'),
                    }
        
        logger.info(f"Loaded {len(stations)} stations from {file_to_load.name}")
    except Exception as e:
        logger.error(f"Failed to load stations file: {e}")
        logger.error(f"File path: {file_to_load}")
    
    return stations


class FeedIngester:
    """Manages GTFS-RT feed ingestion with retries and backpressure."""
    
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.feature_extractor = FeatureExtractor()
        self.last_fetch: Dict[str, datetime] = {}
        # Load all stations from file
        self.station_cache = load_stations_from_file()
        self.unknown_stations = set()  # Track stations not in file
        self.station_creation_tasks = {}  # Track ongoing station creation
    
    async def fetch_feed(self, feed_code: str) -> Dict:
        """Fetch and parse single feed with exponential backoff."""
        retries = 0
        backoff = 1
        
        while retries < settings.max_retries:
            try:
                # Direct protobuf parsing since nyctrains isn't available
                import httpx
                from google.transit import gtfs_realtime_pb2
                
                # Map feed codes to URLs
                url_map = {
                    "1": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs",
                    "A": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
                    "B": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
                    "G": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
                    "J": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
                    "L": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
                    "N": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
                    "SI": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-si",
                }
                
                url = url_map.get(feed_code)
                if not url:
                    raise ValueError(f"Unknown feed code: {feed_code}")
                
                async with httpx.AsyncClient(timeout=settings.feed_timeout) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    
                    feed = gtfs_realtime_pb2.FeedMessage()
                    feed.ParseFromString(response.content)
                    return self._parse_gtfs_feed(feed, feed_code)
                        
            except Exception as e:
                retries += 1
                logger.warning(
                    f"Feed fetch failed",
                    feed_code=feed_code,
                    retry=retries,
                    error=str(e)
                )
                await asyncio.sleep(min(backoff, 30))
                backoff *= 2
        
        raise HTTPException(status_code=503, detail=f"Failed to fetch feed {feed_code}")
    
    def _parse_gtfs_feed(self, feed, feed_code: str) -> Dict:
        """Parse raw GTFS protobuf into our format."""
        trips = []
        alerts = []
        
        for entity in feed.entity:
            if entity.HasField('trip_update'):
                trip = entity.trip_update
                trip_id = trip.trip.trip_id
                route_id = trip.trip.route_id
                direction = trip.trip.direction_id if trip.trip.HasField('direction_id') else 0
                
                for stop_update in trip.stop_time_update:
                    arrival_time = None
                    departure_time = None
                    delay = 0
                    
                    if stop_update.HasField('arrival'):
                        arrival_time = datetime.fromtimestamp(stop_update.arrival.time)
                        if stop_update.arrival.HasField('delay'):
                            delay = stop_update.arrival.delay
                            
                    if stop_update.HasField('departure'):
                        departure_time = datetime.fromtimestamp(stop_update.departure.time)
                    
                    trips.append({
                        "trip_id": trip_id,
                        "route_id": route_id,
                        "direction": direction,
                        "stop_id": stop_update.stop_id,
                        "arrival_time": arrival_time,
                        "departure_time": departure_time,
                        "delay": delay,
                        "headsign": "",
                    })
            
            elif entity.HasField('alert'):
                alert = entity.alert
                alerts.append({
                    "alert_id": entity.id,
                    "header": alert.header_text.translation[0].text if alert.header_text.translation else "",
                    "description": alert.description_text.translation[0].text if alert.description_text.translation else "",
                })
        
        return {
            "trips": trips,
            "alerts": alerts,
            "timestamp": datetime.fromtimestamp(feed.header.timestamp),
            "feed_code": feed_code,
        }
    
    async def ensure_stations_exist(self, positions: List[Dict], db: AsyncSession):
        """Ensure all referenced stations exist in the database."""
        # Collect all unique station IDs
        station_ids = set()
        for pos in positions:
            if pos.get("current_station"):
                station_ids.add(pos["current_station"])
            if pos.get("next_station"):
                station_ids.add(pos["next_station"])
        
        # Use ON CONFLICT DO NOTHING to avoid duplicate key errors
        async with station_creation_lock:
            for station_id in station_ids:
                if not station_id:
                    continue
                
                try:
                    if station_id in self.station_cache:
                        # Station exists in our file
                        station_info = self.station_cache[station_id]
                        
                        # Extract lines from position data
                        lines = set()
                        for pos in positions:
                            if pos.get("current_station") == station_id or pos.get("next_station") == station_id:
                                route_id = pos.get("route_id", "").upper()
                                if route_id:
                                    lines.add(route_id)
                        
                        # Use raw SQL with ON CONFLICT to avoid race conditions
                        await db.execute(
                            text("""
                                INSERT INTO stations (id, name, lat, lon, lines, borough)
                                VALUES (:id, :name, :lat, :lon, :lines, :borough)
                                ON CONFLICT (id) DO UPDATE SET
                                    lines = CASE
                                        WHEN stations.lines IS NULL THEN EXCLUDED.lines
                                        ELSE stations.lines || EXCLUDED.lines
                                    END
                            """),
                            {
                                "id": station_id,
                                "name": station_info["name"],
                                "lat": station_info["lat"],
                                "lon": station_info["lon"],
                                "lines": list(lines),
                                "borough": None
                            }
                        )
                    else:
                        # Unknown station - create with placeholder data
                        if station_id not in self.unknown_stations:
                            self.unknown_stations.add(station_id)
                            logger.warning(f"Unknown station: {station_id}")
                        
                        # Extract route from positions
                        route_id = ""
                        for pos in positions:
                            if pos.get("current_station") == station_id or pos.get("next_station") == station_id:
                                route_id = pos.get("route_id", "").upper()
                                break
                        
                        # Create placeholder station with ON CONFLICT
                        await db.execute(
                            text("""
                                INSERT INTO stations (id, name, lat, lon, lines, borough)
                                VALUES (:id, :name, :lat, :lon, :lines, :borough)
                                ON CONFLICT (id) DO NOTHING
                            """),
                            {
                                "id": station_id,
                                "name": f"Station {station_id}",
                                "lat": 40.7484,  # NYC center
                                "lon": -73.9857,
                                "lines": [route_id] if route_id else [],
                                "borough": None
                            }
                        )
                    
                except Exception as e:
                    logger.error(f"Failed to create station {station_id}: {e}")
                    # Don't rollback here, let the outer transaction handle it
            
            # Commit all station inserts
            await db.commit()
    
    async def process_feed_data(self, feed_code: str, data: Dict, db: AsyncSession):
        """Extract features and persist to database."""
        start_time = datetime.utcnow()
        
        try:
            # Serialize datetime objects in the data for JSON storage
            serialized_data = serialize_datetime(data)
            
            # Store raw feed update first
            feed_update = await crud.create_feed_update(
                db,
                feed_id=feed_code,
                raw_data=serialized_data,
                num_trips=len(data.get("trips", [])),
                num_alerts=len(data.get("alerts", [])),
            )
            await db.flush()  # Flush but don't commit yet
            
            # Extract features for each trip
            positions = []
            for trip_data in data.get("trips", []):
                # Add delay information
                if "delay" in trip_data and trip_data["delay"] != 0:
                    trip_data["scheduled_arrival"] = trip_data["arrival_time"]
                    trip_data["delay_seconds"] = trip_data["delay"]
                else:
                    trip_data["delay_seconds"] = 0
                    
                position = self.feature_extractor.extract_trip_features(trip_data, feed_code)
                if position:
                    positions.append(position)
            
            # Ensure all stations exist BEFORE inserting positions
            await self.ensure_stations_exist(positions, db)
            
            # Now bulk insert positions
            if positions:
                await crud.bulk_create_train_positions(db, positions)
                await db.flush()
            
            # Calculate processing time
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            feed_update.processing_time_ms = processing_time
            
            # Final commit
            await db.commit()
            
            logger.info(
                "Feed processed",
                feed_code=feed_code,
                trips=len(positions),
                time_ms=processing_time
            )
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to process feed {feed_code}: {e}")
            raise
        
        return feed_update


# Global ingester instance
ingester = FeedIngester()


async def start_feed_ingestion():
    """Background task to continuously ingest feeds."""
    logger.info("Starting feed ingestion background task")
    
    while True:
        try:
            # Process feeds sequentially to avoid deadlocks
            async with feed_processing_lock:
                for feed_code in FEED_CODES.keys():
                    # Check if enough time has passed since last fetch
                    last = ingester.last_fetch.get(feed_code, datetime.min)
                    if (datetime.utcnow() - last).total_seconds() >= settings.feed_update_interval:
                        try:
                            # Create separate session for each feed
                            async with AsyncSessionLocal() as db:
                                await process_single_feed(feed_code, db)
                            ingester.last_fetch[feed_code] = datetime.utcnow()
                        except Exception as e:
                            logger.error(f"Failed to process feed {feed_code}: {e}")
            
            # Wait before next cycle
            await asyncio.sleep(settings.feed_update_interval)
            
        except Exception as e:
            logger.error(f"Feed ingestion error: {e}")
            await asyncio.sleep(10)


async def process_single_feed(feed_code: str, db: AsyncSession):
    """Process a single feed with error handling."""
    try:
        data = await ingester.fetch_feed(feed_code)
        await ingester.process_feed_data(feed_code, data, db)
    except Exception as e:
        logger.error(f"Failed to process feed {feed_code}", error=str(e))


@router.get("/status")
async def get_feed_status(db: AsyncSession = Depends(get_db)) -> Dict:
    """Get current feed ingestion status."""
    recent_updates = await crud.get_recent_feed_updates(db, limit=20)
    
    return {
        "active_feeds": list(FEED_CODES.keys()),
        "update_interval": settings.feed_update_interval,
        "recent_updates": [
            FeedUpdateResponse.from_orm(update) for update in recent_updates
        ],
        "queue_size": ingester.queue.qsize() if ingester.queue else 0,
        "loaded_stations": len(ingester.station_cache),
        "unknown_stations": len(ingester.unknown_stations),
    }


@router.get("/positions/{line}")
async def get_train_positions(
    line: str,
    db: AsyncSession = Depends(get_db)
) -> List[TrainPositionResponse]:
    """Get current train positions for a specific line."""
    positions = await crud.get_train_positions_by_line(db, line.upper(), limit=50)
    return [TrainPositionResponse.from_orm(pos) for pos in positions]


@router.post("/refresh/{feed_code}")
async def refresh_feed(
    feed_code: str,
    db: AsyncSession = Depends(get_db)
) -> FeedUpdateResponse:
    """Manually trigger feed refresh."""
    if feed_code not in FEED_CODES:
        raise HTTPException(status_code=404, detail=f"Unknown feed: {feed_code}")
    
    data = await ingester.fetch_feed(feed_code)
    feed_update = await ingester.process_feed_data(feed_code, data, db)
    
    return FeedUpdateResponse.from_orm(feed_update)
