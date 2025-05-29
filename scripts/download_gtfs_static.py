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
