#!/bin/bash

echo "Applying fixes to NYC Subway Monitor..."

# Backup original files
echo "Creating backups..."
cp backend/app/db/database.py backend/app/db/database.py.backup 2>/dev/null || true
cp backend/app/routers/feed.py backend/app/routers/feed.py.backup 2>/dev/null || true
cp backend/app/db/crud.py backend/app/db/crud.py.backup 2>/dev/null || true

# Check if we have the GTFS data
if [ ! -f "data/stops.txt" ]; then
    echo "Extracting GTFS data..."
    cd data
    unzip -o google_transit.zip
    cd ..
fi

echo "GTFS files:"
ls -la data/*.txt | head -5

echo "Done! Now restart the services:"
echo "cd infra && docker-compose restart backend"
