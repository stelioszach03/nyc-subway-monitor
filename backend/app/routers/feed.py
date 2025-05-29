"""
GTFS-RT feed ingestion router.
Handles async fetching from MTA endpoints using nyctrains package.
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
    logger.warning("nyct_gtfs not available, will use fallback")

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()

# Feed IDs for NYC subway lines
FEED_IDS = {
    1: ["1", "2", "3", "4", "5", "6", "S"],  # IRT lines
    26: ["A", "C", "E"],                     # IND 8th Ave
    21: ["B", "D", "F", "M"],                # IND 6th Ave
    2: ["L"],                                # Canarsie
    16: ["N", "Q", "R", "W"],                # BMT Broadway
    36: ["J", "Z"],                          # Nassau
    31: ["G"],                               # Crosstown
    51: ["7"],                               # Flushing
    11: ["SI"],                              # Staten Island
}

# Reverse mapping
LINE_TO_FEED_ID = {}
for feed_id, lines in FEED_IDS.items():
    for line in lines:
        LINE_TO_FEED_ID[line] = feed_id


class FeedIngester:
    """Manages GTFS-RT feed ingestion with retries and backpressure."""
    
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.feature_extractor = FeatureExtractor()
        self.last_fetch: Dict[int, datetime] = {}
        self.station_cache: Dict[str, Dict] = {}
    
    async def fetch_feed(self, feed_id: int) -> Dict:
        """Fetch and parse single feed with exponential backoff."""
        retries = 0
        backoff = 1
        
        while retries < settings.max_retries:
            try:
                if NYCTFeed:
                    # Use nyct_gtfs package to parse real data
                    feed = NYCTFeed(feed_id, fetch_immediately=True)
                    return self._parse_nyct_feed(feed, feed_id)
                else:
                    # Fallback to direct protobuf parsing
                    import httpx
                    from google.transit import gtfs_realtime_pb2
                    
                    url = f"https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"
                    if feed_id != 1:
                        # Map feed IDs to endpoints
                        feed_map = {
                            26: "ace", 21: "bdfm", 2: "l", 16: "nqrw",
                            36: "jz", 31: "g", 51: "7", 11: "si"
                        }
                        if feed_id in feed_map:
                            url = f"https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-{feed_map[feed_id]}"
                    
                    async with httpx.AsyncClient(timeout=settings.feed_timeout) as client:
                        response = await client.get(url)
                        response.raise_for_status()
                        
                        feed = gtfs_realtime_pb2.FeedMessage()
                        feed.ParseFromString(response.content)
                        return self._parse_gtfs_feed(feed, feed_id)
                        
            except Exception as e:
                retries += 1
                logger.warning(
                    f"Feed fetch failed",
                    feed_id=feed_id,
                    retry=retries,
                    error=str(e)
                )
                await asyncio.sleep(min(backoff, 30))
                backoff *= 2
        
        raise HTTPException(status_code=503, detail=f"Failed to fetch feed {feed_id}")
    
    def _parse_nyct_feed(self, feed, feed_id: int) -> Dict:
        """Parse nyct_gtfs Feed object into our format."""
        trips = []
        
        # Process each trip
        for trip in feed.trips:
            trip_id = trip.id
            route_id = trip.route_id
            
            # Process stop time updates
            for stop in trip.stop_time_updates:
                if stop.arrival:
                    trips.append({
                        "trip_id": trip_id,
                        "route_id": route_id,
                        "direction": 1 if trip.direction == "NORTH" else 0,
                        "stop_id": stop.stop_id,
                        "arrival_time": stop.arrival,
                        "departure_time": stop.departure,
                        "scheduled_arrival": None,  # Would need static GTFS for this
                    })
        
        # Process alerts
        alerts = []
        for alert in feed.alerts:
            alerts.append({
                "id": alert.id,
                "header": alert.header,
                "description": alert.description,
            })
        
        return {
            "trips": trips,
            "alerts": alerts,
            "timestamp": datetime.utcnow(),
            "feed_id": feed_id,
        }
    
    def _parse_gtfs_feed(self, feed, feed_id: int) -> Dict:
        """Parse raw GTFS protobuf into our format."""
        trips = []
        
        for entity in feed.entity:
            if entity.HasField('trip_update'):
                trip = entity.trip_update
                trip_id = trip.trip.trip_id
                route_id = trip.trip.route_id
                
                for stop_update in trip.stop_time_update:
                    arrival_time = None
                    departure_time = None
                    
                    if stop_update.HasField('arrival'):
                        arrival_time = datetime.fromtimestamp(stop_update.arrival.time)
                    if stop_update.HasField('departure'):
                        departure_time = datetime.fromtimestamp(stop_update.departure.time)
                    
                    trips.append({
                        "trip_id": trip_id,
                        "route_id": route_id,
                        "direction": trip.trip.direction_id if trip.trip.HasField('direction_id') else 0,
                        "stop_id": stop_update.stop_id,
                        "arrival_time": arrival_time,
                        "departure_time": departure_time,
                        "scheduled_arrival": None,
                    })
        
        return {
            "trips": trips,
            "alerts": [],
            "timestamp": datetime.utcnow(),
            "feed_id": feed_id,
        }
    
    async def load_station_data(self):
        """Load station data from static GTFS or use built-in data."""
        # In production, would load from static GTFS stops.txt
        # For now, use common stations
        self.station_cache = {
            "635": {"name": "Union Sq - 14 St", "lat": 40.734673, "lon": -73.989951, "lines": ["4", "5", "6", "L", "N", "Q", "R", "W"]},
            "635N": {"name": "Union Sq - 14 St", "lat": 40.734673, "lon": -73.989951, "lines": ["4", "5", "6", "L", "N", "Q", "R", "W"]},
            "635S": {"name": "Union Sq - 14 St", "lat": 40.734673, "lon": -73.989951, "lines": ["4", "5", "6", "L", "N", "Q", "R", "W"]},
            "631": {"name": "Grand Central - 42 St", "lat": 40.752199, "lon": -73.977599, "lines": ["4", "5", "6", "7", "S"]},
            "631N": {"name": "Grand Central - 42 St", "lat": 40.752199, "lon": -73.977599, "lines": ["4", "5", "6", "7", "S"]},
            "631S": {"name": "Grand Central - 42 St", "lat": 40.752199, "lon": -73.977599, "lines": ["4", "5", "6", "7", "S"]},
            "629": {"name": "59 St", "lat": 40.762526, "lon": -73.967967, "lines": ["4", "5", "6", "N", "Q", "R", "W"]},
            "A09": {"name": "14 St - Union Sq", "lat": 40.734673, "lon": -73.989951, "lines": ["L"]},
            "L01": {"name": "8 Av", "lat": 40.739777, "lon": -74.002578, "lines": ["L"]},
            "R14": {"name": "23 St", "lat": 40.741303, "lon": -73.989344, "lines": ["N", "Q", "R", "W", "6"]},
            "127": {"name": "Times Sq - 42 St", "lat": 40.755983, "lon": -73.986229, "lines": ["1", "2", "3", "7", "N", "Q", "R", "W", "S"]},
            "A27": {"name": "42 St - Port Authority", "lat": 40.757308, "lon": -73.989735, "lines": ["A", "C", "E"]},
        }
    
    async def process_feed_data(self, feed_id: int, data: Dict, db: AsyncSession):
        """Extract features and persist to database."""
        start_time = datetime.utcnow()
        
        # Store raw feed update
        feed_update = await crud.create_feed_update(
            db,
            feed_id=str(feed_id),
            raw_data=data,
            num_trips=len(data.get("trips", [])),
            num_alerts=len(data.get("alerts", [])),
        )
        
        # Extract features for each trip
        positions = []
        for trip_data in data.get("trips", []):
            position = self.feature_extractor.extract_trip_features(trip_data, str(feed_id))
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
            feed_id=feed_id,
            trips=len(positions),
            time_ms=processing_time
        )
        
        return feed_update


# Global ingester instance
ingester = FeedIngester()


async def start_feed_ingestion():
    """Background task to continuously ingest feeds."""
    logger.info("Starting feed ingestion background task")
    
    # Load station data once
    await ingester.load_station_data()
    
    while True:
        try:
            async with AsyncSessionLocal() as db:
                tasks = []
                
                for feed_id in FEED_IDS.keys():
                    # Check if enough time has passed since last fetch
                    last = ingester.last_fetch.get(feed_id, datetime.min)
                    if (datetime.utcnow() - last).total_seconds() >= settings.feed_update_interval:
                        task = asyncio.create_task(
                            process_single_feed(feed_id, db)
                        )
                        tasks.append(task)
                        ingester.last_fetch[feed_id] = datetime.utcnow()
                
                # Wait for all feeds to complete
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait before next cycle
            await asyncio.sleep(settings.feed_update_interval)
            
        except Exception as e:
            logger.error(f"Feed ingestion error: {e}")
            await asyncio.sleep(10)


async def process_single_feed(feed_id: int, db: AsyncSession):
    """Process a single feed with error handling."""
    try:
        data = await ingester.fetch_feed(feed_id)
        await ingester.process_feed_data(feed_id, data, db)
    except Exception as e:
        logger.error(f"Failed to process feed {feed_id}", error=str(e))


@router.get("/status")
async def get_feed_status(db: AsyncSession = Depends(get_db)) -> Dict:
    """Get current feed ingestion status."""
    recent_updates = await crud.get_recent_feed_updates(db, limit=20)
    
    return {
        "active_feeds": list(FEED_IDS.keys()),
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


@router.post("/refresh/{feed_id}")
async def refresh_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db)
) -> FeedUpdateResponse:
    """Manually trigger feed refresh."""
    if feed_id not in FEED_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown feed: {feed_id}")
    
    data = await ingester.fetch_feed(feed_id)
    feed_update = await ingester.process_feed_data(feed_id, data, db)
    
    return FeedUpdateResponse.from_orm(feed_update)