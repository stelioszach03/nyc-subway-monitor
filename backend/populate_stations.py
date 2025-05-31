#!/usr/bin/env python3
"""
Script to populate the database with GTFS station data.
"""

import asyncio
import csv
import json
from pathlib import Path

import structlog
from sqlalchemy import text
from app.db.database import AsyncSessionLocal

logger = structlog.get_logger()


async def load_stations_to_db():
    """Load stations from GTFS data into the database."""
    
    # Find stops.txt file
    stops_file = Path("data/stops.txt")
    if not stops_file.exists():
        logger.error("stops.txt file not found")
        return
    
    stations_loaded = 0
    
    async with AsyncSessionLocal() as db:
        try:
            with open(stops_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    stop_id = row.get('stop_id', '')
                    if not stop_id:
                        continue
                    
                    # Only process parent stations (location_type = 1) or platforms (location_type = 0 or empty)
                    location_type = row.get('location_type', '0')
                    if location_type not in ['0', '1', '']:
                        continue
                    
                    try:
                        name = row.get('stop_name', f'Station {stop_id}')
                        lat = float(row.get('stop_lat', 40.7484))
                        lon = float(row.get('stop_lon', -73.9857))
                        
                        # Extract line information - for now use empty list
                        # Lines will be populated when train data is processed
                        lines = []
                        
                        # Use direct SQL insert for simplicity
                        await db.execute(
                            text("""
                                INSERT INTO stations (id, name, lat, lon, lines, borough)
                                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                                ON CONFLICT (id) DO NOTHING
                            """),
                            (stop_id, name, lat, lon, json.dumps(lines), None)
                        )
                        stations_loaded += 1
                        
                        if stations_loaded % 100 == 0:
                            logger.info(f"Loaded {stations_loaded} stations...")
                            await db.commit()  # Commit in batches
                            
                    except Exception as e:
                        logger.warning(f"Failed to load station {stop_id}: {e}")
                        continue
            
            await db.commit()
            logger.info(f"Successfully loaded {stations_loaded} stations to database")
            
        except Exception as e:
            logger.error(f"Failed to load stations: {e}")
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(load_stations_to_db())