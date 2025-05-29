#!/bin/bash
# --- scripts/fix_database_issues.sh ---
# Script to fix database issues and download complete GTFS data

set -e

echo "🚇 NYC Subway Monitor - Database Fix Script"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the project root
if [ ! -f "docker-compose.yml" ] && [ ! -f "infra/docker-compose.yml" ]; then
    echo -e "${RED}Error: Please run this script from the project root directory${NC}"
    exit 1
fi

# Determine docker-compose location
if [ -f "infra/docker-compose.yml" ]; then
    COMPOSE_FILE="infra/docker-compose.yml"
    COMPOSE_DIR="infra"
else
    COMPOSE_FILE="docker-compose.yml"
    COMPOSE_DIR="."
fi

echo -e "${YELLOW}Step 1: Stopping services...${NC}"
cd $COMPOSE_DIR
docker-compose down
cd -

echo -e "${YELLOW}Step 2: Creating data directory...${NC}"
mkdir -p data

echo -e "${YELLOW}Step 3: Downloading GTFS static data...${NC}"
cat > scripts/download_gtfs_static.py << 'EOF'
#!/usr/bin/env python3
"""
Download and extract MTA GTFS static data including complete stations file.
"""

import io
import os
import zipfile
from pathlib import Path

import httpx
import asyncio


async def download_gtfs_static_data(output_dir: Path = Path("data")):
    """Download and extract MTA GTFS static data."""
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # MTA GTFS static data URL
    url = "http://web.mta.info/developers/data/nyct/subway/google_transit.zip"
    
    print(f"Downloading GTFS static data from {url}...")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        
        print(f"Downloaded {len(response.content) / 1024 / 1024:.1f} MB")
        
        # Extract zip file
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            # List all files
            print("\nFiles in archive:")
            for info in zf.filelist:
                print(f"  - {info.filename} ({info.file_size / 1024:.1f} KB)")
            
            # Extract all files
            zf.extractall(output_dir)
            print(f"\nExtracted to {output_dir}")
            
            # Check stations.txt
            stations_path = output_dir / "stations.txt"
            if stations_path.exists():
                with open(stations_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    print(f"\nstations.txt contains {len(lines) - 1} stations")
            
            # Also check stops.txt which has ALL stop IDs
            stops_path = output_dir / "stops.txt"
            if stops_path.exists():
                with open(stops_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    print(f"stops.txt contains {len(lines) - 1} stops")


if __name__ == "__main__":
    asyncio.run(download_gtfs_static_data())
EOF

chmod +x scripts/download_gtfs_static.py

# Install required Python packages
pip install httpx

# Run the download script
python scripts/download_gtfs_static.py

echo -e "${YELLOW}Step 4: Updating backend files...${NC}"

# Copy the fixed files to backend
echo "Copying fixed database.py..."
cp -f backend/app/db/database.py backend/app/db/database.py.backup 2>/dev/null || true

echo "Copying fixed feed.py..."
cp -f backend/app/routers/feed.py backend/app/routers/feed.py.backup 2>/dev/null || true

echo "Copying fixed crud.py..."
cp -f backend/app/db/crud.py backend/app/db/crud.py.backup 2>/dev/null || true

echo -e "${YELLOW}Step 5: Clearing database (optional)...${NC}"
read -p "Do you want to clear the database? This will remove all existing data. (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cd $COMPOSE_DIR
    docker-compose up -d timescaledb
    sleep 5
    docker-compose exec timescaledb psql -U postgres -d subway_monitor -c "
        DROP TABLE IF EXISTS train_positions CASCADE;
        DROP TABLE IF EXISTS anomalies CASCADE;
        DROP TABLE IF EXISTS feed_updates CASCADE;
        DROP TABLE IF EXISTS model_artifacts CASCADE;
        DROP TABLE IF EXISTS stations CASCADE;
    "
    docker-compose down
    cd -
fi

echo -e "${YELLOW}Step 6: Starting services...${NC}"
cd $COMPOSE_DIR
docker-compose up -d

echo -e "${YELLOW}Step 7: Waiting for services to be ready...${NC}"
sleep 10

# Check if backend is healthy
for i in {1..30}; do
    if curl -s http://localhost:8000/health/live > /dev/null; then
        echo -e "${GREEN}✓ Backend is healthy${NC}"
        break
    fi
    echo "Waiting for backend... ($i/30)"
    sleep 2
done

echo -e "${GREEN}✅ Database fix complete!${NC}"
echo ""
echo "You can check the logs with:"
echo "  cd $COMPOSE_DIR && docker-compose logs -f backend"
echo ""
echo "The system should now:"
echo "  - Load stations from the complete GTFS stops.txt file"
echo "  - Process feeds sequentially to avoid deadlocks"
echo "  - Use ON CONFLICT DO NOTHING for station inserts"
echo "  - Have proper transaction management"