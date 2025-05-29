"""
GTFS-RT feed ingestion router.
Handles async fetching from MTA endpoints using nyct_gtfs package.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import crud
from app.db.database import get_db, AsyncSessionLocal
from app.ml.features import FeatureExtractor
from app.schemas.feed import FeedUpdateResponse, TrainPositionResponse

try:
    from nyct_gtfs import NYCTFeed
except ImportError:
    NYCTFeed = None
    logger.warning("nyct_gtfs not available, will use direct protobuf parsing")

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()

# Feed codes for NYC subway lines - nyct_gtfs groups them
FEED_CODES = {
    "1": ["1", "2", "3", "4", "5", "6", "7", "S"],  # All numbered lines + shuttle
    "A": ["A", "C", "E"],                            # 8th Avenue line
    "B": ["B", "D", "F", "M"],                       # 6th Avenue line  
    "G": ["G"],                                      # Crosstown
    "J": ["J", "Z"],                                 # Nassau Street
    "L": ["L"],                                      # Canarsie
    "N": ["N", "Q", "R", "W"],                       # Broadway
    "SI": ["SI"],                                    # Staten Island Railway
}

# Common station data with real GTFS stop IDs
STATION_DATA = {
    # Times Square - 42nd St
    "127": {"name": "Times Sq - 42 St", "lat": 40.755983, "lon": -73.986229, "lines": ["1", "2", "3", "7", "N", "Q", "R", "W", "S"]},
    "127N": {"name": "Times Sq - 42 St (Northbound)", "lat": 40.755983, "lon": -73.986229, "lines": ["1", "2", "3", "7"]},
    "127S": {"name": "Times Sq - 42 St (Southbound)", "lat": 40.755983, "lon": -73.986229, "lines": ["1", "2", "3", "7"]},
    "R16": {"name": "Times Sq - 42 St", "lat": 40.754672, "lon": -73.986754, "lines": ["N", "Q", "R", "W"]},
    "R16N": {"name": "Times Sq - 42 St (Northbound)", "lat": 40.754672, "lon": -73.986754, "lines": ["N", "Q", "R", "W"]},
    "R16S": {"name": "Times Sq - 42 St (Southbound)", "lat": 40.754672, "lon": -73.986754, "lines": ["N", "Q", "R", "W"]},
    
    # Union Square - 14th St
    "635": {"name": "Union Sq - 14 St", "lat": 40.734673, "lon": -73.989951, "lines": ["4", "5", "6", "L", "N", "Q", "R", "W"]},
    "635N": {"name": "Union Sq - 14 St (Uptown)", "lat": 40.734673, "lon": -73.989951, "lines": ["4", "5", "6"]},
    "635S": {"name": "Union Sq - 14 St (Downtown)", "lat": 40.734673, "lon": -73.989951, "lines": ["4", "5", "6"]},
    "L03": {"name": "14 St - Union Sq", "lat": 40.734789, "lon": -73.990770, "lines": ["L"]},
    "R17": {"name": "14 St - Union Sq", "lat": 40.735736, "lon": -73.990568, "lines": ["N", "Q", "R", "W"]},
    "R17N": {"name": "14 St - Union Sq (Uptown)", "lat": 40.735736, "lon": -73.990568, "lines": ["N", "Q", "R", "W"]},
    "R17S": {"name": "14 St - Union Sq (Downtown)", "lat": 40.735736, "lon": -73.990568, "lines": ["N", "Q", "R", "W"]},
    
    # Grand Central - 42nd St
    "631": {"name": "Grand Central - 42 St", "lat": 40.752199, "lon": -73.977599, "lines": ["4", "5", "6", "7", "S"]},
    "631N": {"name": "Grand Central - 42 St (Uptown)", "lat": 40.752199, "lon": -73.977599, "lines": ["4", "5", "6"]},
    "631S": {"name": "Grand Central - 42 St (Downtown)", "lat": 40.752199, "lon": -73.977599, "lines": ["4", "5", "6"]},
    "723": {"name": "Grand Central - 42 St", "lat": 40.751431, "lon": -73.976041, "lines": ["7"]},
    
    # 59th St
    "629": {"name": "59 St", "lat": 40.762526, "lon": -73.967967, "lines": ["4", "5", "6", "N", "Q", "R", "W"]},
    "629N": {"name": "59 St (Uptown)", "lat": 40.762526, "lon": -73.967967, "lines": ["4", "5", "6"]},
    "629S": {"name": "59 St (Downtown)", "lat": 40.762526, "lon": -73.967967, "lines": ["4", "5", "6"]},
    "R13": {"name": "Lexington Av/59 St", "lat": 40.762526, "lon": -73.967967, "lines": ["N", "Q", "R", "W"]},
    
    # 42nd St - Port Authority
    "A27": {"name": "42 St - Port Authority", "lat": 40.757308, "lon": -73.989735, "lines": ["A", "C", "E"]},
    "A27N": {"name": "42 St - Port Authority (Uptown)", "lat": 40.757308, "lon": -73.989735, "lines": ["A", "C", "E"]},
    "A27S": {"name": "42 St - Port Authority (Downtown)", "lat": 40.757308, "lon": -73.989735, "lines": ["A", "C", "E"]},
    
    # Additional stations
    "L01": {"name": "8 Av", "lat": 40.739777, "lon": -74.002578, "lines": ["L"]},
    "D17": {"name": "Grand St", "lat": 40.718267, "lon": -73.993753, "lines": ["B", "D"]},
    "Q01": {"name": "Canal St", "lat": 40.718803, "lon": -74.000193, "lines": ["N", "Q", "R", "W", "6"]},
}


class FeedIngester:
    """Manages GTFS-RT feed ingestion with retries and backpressure."""
    
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.feature_extractor = FeatureExtractor()
        self.last_fetch: Dict[str, datetime] = {}
        self.station_cache = STATION_DATA
    
    async def fetch_feed(self, feed_code: str) -> Dict:
        """Fetch and parse single feed with exponential backoff."""
        retries = 0
        backoff = 1
        
        while retries < settings.max_retries:
            try:
                if NYCTFeed:
                    # Use nyct_gtfs package - no API key needed in v2.0
                    feed = NYCTFeed(feed_code)
                    return self._parse_nyct_feed(feed, feed_code)
                else:
                    # Fallback to direct protobuf parsing
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
    
    def _parse_nyct_feed(self, feed, feed_code: str) -> Dict:
        """Parse nyct_gtfs Feed object into our format."""
        trips = []
        
        # Get feed timestamp
        feed_timestamp = feed.last_generated if hasattr(feed, 'last_generated') else datetime.utcnow()
        
        # Process each trip
        for trip in feed.trips:
            if not hasattr(trip, 'stop_time_updates') or not trip.stop_time_updates:
                continue
                
            # Use correct attribute names for Trip object
            trip_id = trip.trip_id  # NOT trip.id
            route_id = trip.route_id
            direction_text = trip.direction if hasattr(trip, 'direction') else "N"
            direction = 1 if direction_text in ["N", "NORTH", "UPTOWN"] else 0
            headsign = trip.headsign_text if hasattr(trip, 'headsign_text') else ""
            
            # Process stop time updates
            for stop_update in trip.stop_time_updates:
                stop_id = stop_update.stop_id
                
                # Get times
                arrival_time = stop_update.arrival if hasattr(stop_update, 'arrival') else None
                departure_time = stop_update.departure if hasattr(stop_update, 'departure') else None
                
                # Calculate delay if available
                delay = 0
                if hasattr(stop_update, 'delay'):
                    delay = stop_update.delay
                
                if arrival_time:
                    trips.append({
                        "trip_id": trip_id,
                        "route_id": route_id,
                        "direction": direction,
                        "stop_id": stop_id,
                        "arrival_time": arrival_time,
                        "departure_time": departure_time,
                        "delay": delay,
                        "headsign": headsign,
                    })
        
        # Process alerts if available
        alerts = []
        if hasattr(feed, 'alerts'):
            for alert in feed.alerts:
                alert_data = {
                    "alert_id": getattr(alert, 'id', 'unknown'),
                    "header": getattr(alert, 'header', ''),
                    "description": getattr(alert, 'description', ''),
                }
                alerts.append(alert_data)
        
        return {
            "trips": trips,
            "alerts": alerts,
            "timestamp": feed_timestamp,
            "feed_code": feed_code,
        }
    
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
    
    async def process_feed_data(self, feed_code: str, data: Dict, db: AsyncSession):
        """Extract features and persist to database."""
        start_time = datetime.utcnow()
        
        # Store raw feed update
        feed_update = await crud.create_feed_update(
            db,
            feed_id=feed_code,
            raw_data=data,
            num_trips=len(data.get("trips", [])),
            num_alerts=len(data.get("alerts", [])),
        )
        
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
        
        # Create stations if needed
        for pos in positions:
            station_id = pos.get("current_station")
            if station_id and station_id in self.station_cache:
                station_info = self.station_cache[station_id]
                await crud.get_or_create_station(
                    db,
                    station_id=station_id,
                    name=station_info["name"],
                    lat=station_info["lat"],
                    lon=station_info["lon"],
                    lines=station_info["lines"],
                )
        
        # Bulk insert positions
        if positions:
            await crud.bulk_create_train_positions(db, positions)
        
        # Calculate processing time
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        feed_update.processing_time_ms = processing_time
        await db.commit()
        
        logger.info(
            "Feed processed",
            feed_code=feed_code,
            trips=len(positions),
            time_ms=processing_time
        )
        
        return feed_update


# Global ingester instance
ingester = FeedIngester()


async def start_feed_ingestion():
    """Background task to continuously ingest feeds."""
    logger.info("Starting feed ingestion background task")
    
    while True:
        try:
            async with AsyncSessionLocal() as db:
                tasks = []
                
                for feed_code in FEED_CODES.keys():
                    # Check if enough time has passed since last fetch
                    last = ingester.last_fetch.get(feed_code, datetime.min)
                    if (datetime.utcnow() - last).total_seconds() >= settings.feed_update_interval:
                        task = asyncio.create_task(
                            process_single_feed(feed_code, db)
                        )
                        tasks.append(task)
                        ingester.last_fetch[feed_code] = datetime.utcnow()
                
                # Wait for all feeds to complete
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            
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