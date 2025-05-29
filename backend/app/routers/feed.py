"""
Fixed GTFS-RT feed ingestion with proper station handling.
"""

import asyncio
import csv
import json
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

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()

try:
    from nyctrains import NYCTFeed
except ImportError:
    NYCTFeed = None
    logger.warning("nyctrains not available, using direct protobuf parsing")

# Feed endpoints
FEED_ENDPOINTS = {
    "1": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs",
    "A": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
    "B": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
    "G": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
    "J": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
    "L": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
    "N": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
    "SI": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-si",
}

# Global locks
station_creation_lock = asyncio.Lock()
feed_processing_lock = asyncio.Lock()


def load_stations_from_gtfs() -> Dict[str, Dict]:
    """Load station data from GTFS stops.txt file."""
    stations = {}
    
    # Search paths
    search_paths = [
        Path("/app/data/stops.txt"),
        Path("data/stops.txt"),
        Path("backend/data/stops.txt"),
        Path("/home/stelios/nyc-subway-monitor/data/stops.txt"),
        Path("/home/stelios/nyc-subway-monitor/backend/data/stops.txt"),
    ]
    
    stops_file = None
    for path in search_paths:
        if path.exists():
            stops_file = path
            logger.info(f"Found stops file at: {path}")
            break
    
    if not stops_file:
        logger.warning("No stops.txt file found")
        return stations
    
    try:
        with open(stops_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                stop_id = row.get('stop_id', '')
                if stop_id:
                    stations[stop_id] = {
                        "id": stop_id,
                        "name": row.get('stop_name', f'Station {stop_id}'),
                        "lat": float(row.get('stop_lat', 40.7484)),
                        "lon": float(row.get('stop_lon', -73.9857)),
                        "parent_station": row.get('parent_station', ''),
                        "location_type": row.get('location_type', '0'),
                    }
        
        logger.info(f"Loaded {len(stations)} stations from GTFS")
        
    except Exception as e:
        logger.error(f"Failed to load stations: {e}")
    
    return stations


class FeedIngester:
    """GTFS-RT feed ingestion with proper error handling."""
    
    def __init__(self):
        self.feature_extractor = FeatureExtractor()
        self.last_fetch: Dict[str, datetime] = {}
        self.station_cache = load_stations_from_gtfs()
    
    async def fetch_feed(self, feed_code: str) -> Dict:
        """Fetch and parse feed with retry logic."""
        import httpx
        from google.transit import gtfs_realtime_pb2
        
        url = FEED_ENDPOINTS.get(feed_code)
        if not url:
            raise ValueError(f"Unknown feed code: {feed_code}")
        
        retries = 0
        while retries < settings.max_retries:
            try:
                async with httpx.AsyncClient(timeout=settings.feed_timeout) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    
                    feed = gtfs_realtime_pb2.FeedMessage()
                    feed.ParseFromString(response.content)
                    
                    return self._parse_gtfs_feed(feed, feed_code)
                    
            except Exception as e:
                retries += 1
                logger.warning(f"Feed fetch failed (attempt {retries}): {e}")
                if retries < settings.max_retries:
                    await asyncio.sleep(min(2 ** retries, 30))
                else:
                    raise
    
    def _parse_gtfs_feed(self, feed, feed_code: str) -> Dict:
        """Parse GTFS protobuf to our format."""
        trips = []
        alerts = []
        
        for entity in feed.entity:
            if entity.HasField('trip_update'):
                trip = entity.trip_update
                trip_id = trip.trip.trip_id
                route_id = trip.trip.route_id
                
                for stop_update in trip.stop_time_update:
                    stop_dict = {
                        "trip_id": trip_id,
                        "route_id": route_id,
                        "direction": getattr(trip.trip, 'direction_id', 0),
                        "stop_id": stop_update.stop_id,
                        "arrival_time": None,
                        "departure_time": None,
                        "delay": 0,
                    }
                    
                    if stop_update.HasField('arrival'):
                        stop_dict["arrival_time"] = datetime.fromtimestamp(stop_update.arrival.time)
                        if stop_update.arrival.HasField('delay'):
                            stop_dict["delay"] = stop_update.arrival.delay
                    
                    if stop_update.HasField('departure'):
                        stop_dict["departure_time"] = datetime.fromtimestamp(stop_update.departure.time)
                    
                    trips.append(stop_dict)
            
            elif entity.HasField('alert'):
                alert = entity.alert
                alerts.append({
                    "alert_id": entity.id,
                    "header": alert.header_text.translation[0].text if alert.header_text.translation else "",
                })
        
        return {
            "trips": trips,
            "alerts": alerts,
            "timestamp": datetime.fromtimestamp(feed.header.timestamp),
            "feed_code": feed_code,
        }
    
    async def ensure_stations_exist(self, positions: List[Dict], db: AsyncSession):
        """Create stations with proper JSONB handling."""
        station_ids = set()
        for pos in positions:
            if pos.get("current_station"):
                station_ids.add(pos["current_station"])
            if pos.get("next_station"):
                station_ids.add(pos["next_station"])
        
        async with station_creation_lock:
            for station_id in station_ids:
                if not station_id:
                    continue
                
                try:
                    # Get station info
                    station_info = self.station_cache.get(station_id, {
                        "id": station_id,
                        "name": f"Station {station_id}",
                        "lat": 40.7484,
                        "lon": -73.9857,
                    })
                    
                    # Extract lines from positions
                    lines = []
                    for pos in positions:
                        if (pos.get("current_station") == station_id or 
                            pos.get("next_station") == station_id):
                            route = pos.get("route_id", "").upper()
                            if route and route not in lines:
                                lines.append(route)
                    
                    # Use raw SQL with JSON encoding for JSONB
                    await db.execute(
                        text("""
                            INSERT INTO stations (id, name, lat, lon, lines, borough)
                            VALUES (:id, :name, :lat, :lon, :lines::jsonb, :borough)
                            ON CONFLICT (id) DO UPDATE SET
                                lines = CASE
                                    WHEN stations.lines IS NULL THEN EXCLUDED.lines
                                    ELSE stations.lines || EXCLUDED.lines
                                END
                        """),
                        {
                            "id": station_id,
                            "name": station_info.get("name", f"Station {station_id}"),
                            "lat": station_info.get("lat", 40.7484),
                            "lon": station_info.get("lon", -73.9857),
                            "lines": json.dumps(lines),  # CRITICAL: JSON encode the list
                            "borough": None
                        }
                    )
                    
                except Exception as e:
                    logger.error(f"Failed to create station {station_id}: {e}")
            
            await db.commit()
    
    async def process_feed_data(self, feed_code: str, data: Dict, db: AsyncSession):
        """Process feed with proper transaction management."""
        start_time = datetime.utcnow()
        
        try:
            # Create feed update record
            feed_update = await crud.create_feed_update(
                db,
                feed_id=feed_code,
                raw_data=data,
                num_trips=len(data.get("trips", [])),
                num_alerts=len(data.get("alerts", [])),
            )
            
            # Extract positions
            positions = []
            for trip_data in data.get("trips", []):
                if "delay" in trip_data:
                    trip_data["delay_seconds"] = trip_data["delay"]
                
                position = self.feature_extractor.extract_trip_features(trip_data, feed_code)
                if position:
                    positions.append(position)
            
            # Ensure stations exist
            if positions:
                await self.ensure_stations_exist(positions, db)
                await crud.bulk_create_train_positions(db, positions)
            
            # Update processing time
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            feed_update.processing_time_ms = processing_time
            
            await db.commit()
            
            logger.info(f"Processed feed {feed_code}: {len(positions)} positions in {processing_time:.0f}ms")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to process feed {feed_code}: {e}")
            raise
        
        return feed_update


# Global ingester
ingester = FeedIngester()


async def start_feed_ingestion():
    """Background task for continuous feed ingestion."""
    logger.info("Starting feed ingestion")
    
    while True:
        try:
            async with feed_processing_lock:
                for feed_code in FEED_ENDPOINTS.keys():
                    last = ingester.last_fetch.get(feed_code, datetime.min)
                    if (datetime.utcnow() - last).total_seconds() >= settings.feed_update_interval:
                        try:
                            async with AsyncSessionLocal() as db:
                                data = await ingester.fetch_feed(feed_code)
                                await ingester.process_feed_data(feed_code, data, db)
                            ingester.last_fetch[feed_code] = datetime.utcnow()
                        except Exception as e:
                            logger.error(f"Feed {feed_code} error: {e}")
            
            await asyncio.sleep(settings.feed_update_interval)
            
        except Exception as e:
            logger.error(f"Feed ingestion error: {e}")
            await asyncio.sleep(10)


@router.get("/status")
async def get_feed_status(db: AsyncSession = Depends(get_db)) -> Dict:
    """Get feed ingestion status."""
    recent_updates = await crud.get_recent_feed_updates(db, limit=20)
    
    return {
        "active_feeds": list(FEED_ENDPOINTS.keys()),
        "update_interval": settings.feed_update_interval,
        "recent_updates": [
            FeedUpdateResponse.from_orm(update) for update in recent_updates
        ],
        "loaded_stations": len(ingester.station_cache),
        "status": "operational"
    }


@router.get("/positions/{line}")
async def get_train_positions(
    line: str,
    db: AsyncSession = Depends(get_db)
) -> List[TrainPositionResponse]:
    """Get current train positions for a line."""
    positions = await crud.get_train_positions_by_line(db, line.upper(), limit=50)
    return [TrainPositionResponse.from_orm(pos) for pos in positions]


@router.post("/refresh/{feed_code}")
async def refresh_feed(
    feed_code: str,
    db: AsyncSession = Depends(get_db)
) -> FeedUpdateResponse:
    """Manually trigger feed refresh."""
    if feed_code not in FEED_ENDPOINTS:
        raise HTTPException(status_code=404, detail=f"Unknown feed: {feed_code}")
    
    data = await ingester.fetch_feed(feed_code)
    feed_update = await ingester.process_feed_data(feed_code, data, db)
    
    return FeedUpdateResponse.from_orm(feed_update)