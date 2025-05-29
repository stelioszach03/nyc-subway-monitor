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
    """Load station data from CSV file."""
    stations = {}
    stations_file = Path("data/stations.txt")
    
    if not stations_file.exists():
        logger.warning(f"Stations file not found at {stations_file}")
        return stations
    
    try:
        with open(stations_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Skip parent stations (location_type=1)
                if row.get('location_type') == '1':
                    continue
                    
                stop_id = row['stop_id']
                stations[stop_id] = {
                    "name": row['stop_name'],
                    "lat": float(row['stop_lat']),
                    "lon": float(row['stop_lon']),
                    "lines": [],  # Will be populated from feed data
                }
        
        logger.info(f"Loaded {len(stations)} stations from file")
    except Exception as e:
        logger.error(f"Failed to load stations file: {e}")
    
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
    
    async def process_feed_data(self, feed_code: str, data: Dict, db: AsyncSession):
        """Extract features and persist to database."""
        start_time = datetime.utcnow()
        
        try:
            # Serialize datetime objects in the data for JSON storage
            serialized_data = serialize_datetime(data)
            
            # Store raw feed update
            feed_update = await crud.create_feed_update(
                db,
                feed_id=feed_code,
                raw_data=serialized_data,
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
                if station_id:
                    if station_id in self.station_cache:
                        # Station exists in our file
                        station_info = self.station_cache[station_id]
                        
                        # Update lines info based on route
                        route_id = pos.get("route_id", "").upper()
                        if route_id and route_id not in station_info["lines"]:
                            station_info["lines"].append(route_id)
                        
                        await crud.get_or_create_station(
                            db,
                            station_id=station_id,
                            name=station_info["name"],
                            lat=station_info["lat"],
                            lon=station_info["lon"],
                            lines=station_info["lines"],
                        )
                    else:
                        # Unknown station - create with placeholder data
                        if station_id not in self.unknown_stations:
                            self.unknown_stations.add(station_id)
                            logger.warning(f"Unknown station: {station_id}")
                        
                        # Create placeholder station
                        await crud.get_or_create_station(
                            db,
                            station_id=station_id,
                            name=f"Station {station_id}",
                            lat=40.7484,  # NYC center
                            lon=-73.9857,
                            lines=[pos.get("route_id", "").upper()],
                        )
            
            # Commit station creations
            await db.commit()
            
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
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to process feed: {e}")
            raise
        
        return feed_update


# Global ingester instance
ingester = FeedIngester()


async def start_feed_ingestion():
    """Background task to continuously ingest feeds."""
    logger.info("Starting feed ingestion background task")
    
    while True:
        try:
            tasks = []
            
            for feed_code in FEED_CODES.keys():
                # Check if enough time has passed since last fetch
                last = ingester.last_fetch.get(feed_code, datetime.min)
                if (datetime.utcnow() - last).total_seconds() >= settings.feed_update_interval:
                    # Create separate session for each feed
                    async with AsyncSessionLocal() as db:
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

# --- backend/app/db/crud.py ---
"""
Database CRUD operations for async SQLAlchemy.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Anomaly, FeedUpdate, ModelArtifact, Station, TrainPosition


# Feed operations
async def create_feed_update(
    db: AsyncSession,
    feed_id: str,
    raw_data: Dict,
    num_trips: int,
    num_alerts: int,
) -> FeedUpdate:
    """Create new feed update record."""
    feed_update = FeedUpdate(
        timestamp=datetime.utcnow(),
        feed_id=feed_id,
        raw_data=raw_data,
        num_trips=num_trips,
        num_alerts=num_alerts,
    )
    db.add(feed_update)
    await db.flush()
    return feed_update


async def get_recent_feed_updates(
    db: AsyncSession,
    limit: int = 20
) -> List[FeedUpdate]:
    """Get recent feed updates."""
    query = select(FeedUpdate).order_by(FeedUpdate.timestamp.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


# Train position operations
async def bulk_create_train_positions(
    db: AsyncSession,
    positions: List[Dict]
) -> List[TrainPosition]:
    """Bulk insert train positions."""
    objects = [TrainPosition(**pos) for pos in positions]
    db.add_all(objects)
    await db.flush()
    return objects


async def get_train_positions_by_line(
    db: AsyncSession,
    line: str,
    limit: int = 50
) -> List[TrainPosition]:
    """Get recent train positions for a line."""
    query = (
        select(TrainPosition)
        .where(TrainPosition.line == line)
        .order_by(TrainPosition.timestamp.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


async def get_train_positions_since(
    db: AsyncSession,
    since: datetime,
    line: Optional[str] = None
) -> List[TrainPosition]:
    """Get train positions since timestamp."""
    query = select(TrainPosition).where(TrainPosition.timestamp >= since)
    
    if line:
        query = query.where(TrainPosition.line == line)
    
    query = query.order_by(TrainPosition.timestamp)
    result = await db.execute(query)
    return result.scalars().all()


async def get_train_positions_for_training(
    db: AsyncSession,
    start_time: datetime,
    end_time: datetime
) -> List[TrainPosition]:
    """Get train positions for model training."""
    query = (
        select(TrainPosition)
        .where(
            and_(
                TrainPosition.timestamp >= start_time,
                TrainPosition.timestamp <= end_time,
                TrainPosition.headway_seconds.isnot(None),
            )
        )
        .order_by(TrainPosition.timestamp)
    )
    result = await db.execute(query)
    return result.scalars().all()


# Anomaly operations
async def create_anomaly(db: AsyncSession, anomaly_data: Dict) -> Anomaly:
    """Create new anomaly record."""
    anomaly = Anomaly(**anomaly_data)
    db.add(anomaly)
    await db.flush()
    return anomaly


async def get_anomalies(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    line: Optional[str] = None,
    station_id: Optional[str] = None,
    resolved: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Tuple[List[Anomaly], int]:
    """Get paginated anomalies with filters."""
    
    # Base query
    query = select(Anomaly)
    
    # Apply filters
    conditions = []
    if line:
        conditions.append(Anomaly.line == line)
    if station_id:
        conditions.append(Anomaly.station_id == station_id)
    if resolved is not None:
        conditions.append(Anomaly.resolved == resolved)
    if start_date:
        conditions.append(Anomaly.detected_at >= start_date)
    if end_date:
        conditions.append(Anomaly.detected_at <= end_date)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(Anomaly.detected_at.desc()).offset(offset).limit(page_size)
    
    result = await db.execute(query)
    anomalies = result.scalars().all()
    
    return anomalies, total or 0


async def get_anomaly_by_id(db: AsyncSession, anomaly_id: int) -> Optional[Anomaly]:
    """Get single anomaly by ID."""
    query = select(Anomaly).where(Anomaly.id == anomaly_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def resolve_anomaly(db: AsyncSession, anomaly_id: int) -> Optional[Anomaly]:
    """Mark anomaly as resolved."""
    anomaly = await get_anomaly_by_id(db, anomaly_id)
    if anomaly:
        anomaly.resolved = True
        anomaly.resolved_at = datetime.utcnow()
        await db.flush()
    return anomaly


async def get_anomaly_stats(
    db: AsyncSession,
    start_time: datetime,
    end_time: datetime
) -> Dict:
    """Get anomaly statistics."""
    
    # Total today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = await db.scalar(
        select(func.count()).select_from(Anomaly).where(
            Anomaly.detected_at >= today_start
        )
    )
    
    # Active anomalies
    active_count = await db.scalar(
        select(func.count()).select_from(Anomaly).where(
            Anomaly.resolved == False
        )
    )
    
    # By type
    type_query = (
        select(Anomaly.anomaly_type, func.count())
        .where(
            and_(
                Anomaly.detected_at >= start_time,
                Anomaly.detected_at <= end_time
            )
        )
        .group_by(Anomaly.anomaly_type)
    )
    type_result = await db.execute(type_query)
    by_type = dict(type_result.all())
    
    # By line
    line_query = (
        select(Anomaly.line, func.count())
        .where(
            and_(
                Anomaly.detected_at >= start_time,
                Anomaly.detected_at <= end_time,
                Anomaly.line.isnot(None)
            )
        )
        .group_by(Anomaly.line)
    )
    line_result = await db.execute(line_query)
    by_line = dict(line_result.all())
    
    # Severity distribution
    severity_dist = {
        "low": 0,
        "medium": 0,
        "high": 0,
    }
    
    severity_query = select(Anomaly.severity).where(
        and_(
            Anomaly.detected_at >= start_time,
            Anomaly.detected_at <= end_time
        )
    )
    severity_result = await db.execute(severity_query)
    
    for (severity,) in severity_result:
        if severity < 0.33:
            severity_dist["low"] += 1
        elif severity < 0.67:
            severity_dist["medium"] += 1
        else:
            severity_dist["high"] += 1
    
    return {
        "total_today": today_count or 0,
        "total_active": active_count or 0,
        "by_type": by_type,
        "by_line": by_line,
        "severity_distribution": severity_dist,
    }


async def get_anomaly_trend(
    db: AsyncSession,
    start_time: datetime,
    end_time: datetime
) -> List[Dict]:
    """Get hourly anomaly trend."""
    
    # Fixed: wrap SQL in text()
    query = text("""
        SELECT 
            date_trunc('hour', detected_at) as hour,
            COUNT(*) as count,
            AVG(severity) as avg_severity
        FROM anomalies
        WHERE detected_at >= :start_time AND detected_at <= :end_time
        GROUP BY hour
        ORDER BY hour
    """)
    
    result = await db.execute(
        query,
        {"start_time": start_time, "end_time": end_time}
    )
    
    trend = [
        {
            "hour": row[0].isoformat() if row[0] else None,
            "count": row[1],
            "avg_severity": float(row[2]) if row[2] else 0,
        }
        for row in result
    ]
    
    return trend


# Model operations
async def create_model_artifact(
    db: AsyncSession,
    model_type: str,
    version: str,
    git_sha: Optional[str],
    metrics: Dict,
    artifact_path: str,
    training_samples: int,
) -> ModelArtifact:
    """Create model artifact record."""
    artifact = ModelArtifact(
        model_type=model_type,
        version=version,
        git_sha=git_sha,
        metrics=metrics,
        artifact_path=artifact_path,
        training_samples=training_samples,
        hyperparameters={},  # Could be extended
    )
    db.add(artifact)
    await db.flush()
    return artifact


async def get_active_models(db: AsyncSession) -> List[ModelArtifact]:
    """Get currently active models."""
    query = select(ModelArtifact).where(ModelArtifact.is_active == True)
    result = await db.execute(query)
    return result.scalars().all()


async def set_active_model(
    db: AsyncSession,
    model_type: str,
    version: str
) -> None:
    """Set a model version as active."""
    
    # Deactivate current active model
    await db.execute(
        update(ModelArtifact)
        .where(
            and_(
                ModelArtifact.model_type == model_type,
                ModelArtifact.is_active == True
            )
        )
        .values(is_active=False)
    )
    
    # Activate new model
    await db.execute(
        update(ModelArtifact)
        .where(
            and_(
                ModelArtifact.model_type == model_type,
                ModelArtifact.version == version
            )
        )
        .values(is_active=True)
    )
    
    await db.flush()


# Station operations
async def get_or_create_station(
    db: AsyncSession,
    station_id: str,
    name: str,
    lat: float,
    lon: float,
    lines: List[str],
) -> Station:
    """Get or create station record."""
    query = select(Station).where(Station.id == station_id)
    result = await db.execute(query)
    station = result.scalar_one_or_none()
    
    if not station:
        station = Station(
            id=station_id,
            name=name,
            lat=lat,
            lon=lon,
            lines=lines,
        )
        db.add(station)
        await db.flush()
    
    return station