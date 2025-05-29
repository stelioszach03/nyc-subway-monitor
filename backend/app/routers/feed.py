"""
GTFS-RT feed ingestion router.
Handles async fetching from MTA endpoints using nyctrains package.
"""

import asyncio
from datetime import datetime
from typing import Dict, List

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import crud
from app.db.database import get_db
from app.ml.features import FeatureExtractor
from app.schemas.feed import FeedUpdateResponse, TrainPositionResponse

try:
    from nyctrains import SubwayFeed
except ImportError:
    # Fallback for development if nyctrains not available
    SubwayFeed = None

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()

# Feed endpoints mapping
FEED_ENDPOINTS = {
    "ace": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
    "bdfm": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
    "g": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
    "jz": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
    "nqrw": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
    "l": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
    "123456": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs",
    "7": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-7",
    "si": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-si",
}


class FeedIngester:
    """Manages GTFS-RT feed ingestion with retries and backpressure."""
    
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.feature_extractor = FeatureExtractor()
        self.last_fetch: Dict[str, datetime] = {}
    
    async def fetch_feed(self, feed_id: str) -> Dict:
        """Fetch and parse single feed with exponential backoff."""
        retries = 0
        backoff = 1
        
        while retries < settings.max_retries:
            try:
                if SubwayFeed:
                    # Use nyctrains package
                    feed = SubwayFeed(feed_id)
                    return self._parse_nyctrains_feed(feed)
                else:
                    # Fallback: direct HTTP fetch
                    import httpx
                    async with httpx.AsyncClient(timeout=settings.feed_timeout) as client:
                        response = await client.get(FEED_ENDPOINTS[feed_id])
                        response.raise_for_status()
                        # Would need protobuf parsing here
                        return {"trips": [], "alerts": []}
                        
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
    
    def _parse_nyctrains_feed(self, feed) -> Dict:
        """Parse nyctrains SubwayFeed object into our format."""
        trips = []
        
        for train in feed.trains:
            for stop in train.stop_time_updates:
                trips.append({
                    "trip_id": train.trip_id,
                    "route_id": train.route_id,
                    "direction": train.direction,
                    "stop_id": stop.stop_id,
                    "arrival_time": stop.arrival,
                    "departure_time": stop.departure,
                })
        
        return {
            "trips": trips,
            "alerts": feed.alerts if hasattr(feed, 'alerts') else [],
            "timestamp": datetime.utcnow(),
        }
    
    async def process_feed_data(self, feed_id: str, data: Dict, db: AsyncSession):
        """Extract features and persist to database."""
        start_time = datetime.utcnow()
        
        # Store raw feed update
        feed_update = await crud.create_feed_update(
            db,
            feed_id=feed_id,
            raw_data=data,
            num_trips=len(data.get("trips", [])),
            num_alerts=len(data.get("alerts", [])),
        )
        
        # Extract features for each trip
        positions = []
        for trip_data in data.get("trips", []):
            position = self.feature_extractor.extract_trip_features(trip_data, feed_id)
            if position:
                positions.append(position)
        
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
    
    while True:
        async with AsyncSessionLocal() as db:
            tasks = []
            
            for feed_id in FEED_ENDPOINTS.keys():
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


async def process_single_feed(feed_id: str, db: AsyncSession):
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
        "active_feeds": list(FEED_ENDPOINTS.keys()),
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
    positions = await crud.get_train_positions_by_line(db, line, limit=50)
    return [TrainPositionResponse.from_orm(pos) for pos in positions]


@router.post("/refresh/{feed_id}")
async def refresh_feed(
    feed_id: str,
    db: AsyncSession = Depends(get_db)
) -> FeedUpdateResponse:
    """Manually trigger feed refresh."""
    if feed_id not in FEED_ENDPOINTS:
        raise HTTPException(status_code=404, detail=f"Unknown feed: {feed_id}")
    
    data = await ingester.fetch_feed(feed_id)
    feed_update = await ingester.process_feed_data(feed_id, data, db)
    
    return FeedUpdateResponse.from_orm(feed_update)