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
    await db.flush()  # Changed from db.flush() to await db.flush()
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