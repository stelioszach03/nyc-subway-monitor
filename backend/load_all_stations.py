#!/usr/bin/env python3
"""
Load all GTFS stations into the database using ORM.
"""

import asyncio
import csv
from pathlib import Path

import structlog
from sqlalchemy import text
from app.db.database import AsyncSessionLocal
from app.db.models import Station

logger = structlog.get_logger()


async def load_all_stations():
    """Load all stations from GTFS stops.txt into database."""
    
    stops_file = Path("data/stops.txt")
    if not stops_file.exists():
        logger.error(f"GTFS stops file not found: {stops_file}")
        return False
    
    async with AsyncSessionLocal() as db:
        try:
            # Clear existing stations first
            logger.info("Clearing existing stations...")
            await db.execute(text("DELETE FROM stations"))
            
            stations_loaded = 0
            
            with open(stops_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    try:
                        stop_id = row['stop_id'].strip()
                        name = row['stop_name'].strip()
                        lat = float(row['stop_lat'])
                        lon = float(row['stop_lon'])
                        
                        # Skip platform-specific stops (those with parent_station)
                        if row.get('parent_station', '').strip():
                            continue
                            
                        # Lines will be populated when train data is processed
                        lines = []
                        
                        # Create station using ORM
                        station = Station(
                            id=stop_id,
                            name=name,
                            lat=lat,
                            lon=lon,
                            lines=lines,
                            borough=None
                        )
                        db.add(station)
                        stations_loaded += 1
                        
                        if stations_loaded % 100 == 0:
                            logger.info(f"Loaded {stations_loaded} stations...")
                            await db.commit()  # Commit in batches
                            
                    except Exception as e:
                        logger.warning(f"Failed to load station {stop_id}: {e}")
                        continue
            
            await db.commit()
            logger.info(f"Successfully loaded {stations_loaded} stations to database")
            
            # Verify count
            result = await db.execute(text('SELECT COUNT(*) FROM stations'))
            count = result.scalar()
            logger.info(f"Total stations in database: {count}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load stations: {e}")
            await db.rollback()
            return False


if __name__ == "__main__":
    success = asyncio.run(load_all_stations())
    if not success:
        exit(1)