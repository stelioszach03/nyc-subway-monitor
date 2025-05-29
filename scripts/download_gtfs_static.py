#!/usr/bin/env python3
"""
Download MTA GTFS static data including stops.txt
"""

import io
import os
import zipfile
from pathlib import Path
import requests


def download_gtfs_static_data(output_dir: Path = Path("data")):
    """Download and extract MTA GTFS static data."""
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # MTA GTFS static data URL
    url = "http://web.mta.info/developers/data/nyct/subway/google_transit.zip"
    
    print(f"Downloading GTFS static data from {url}...")
    
    try:
        response = requests.get(url, timeout=60)
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
            
            # Check stops.txt
            stops_path = output_dir / "stops.txt"
            if stops_path.exists():
                with open(stops_path, 'r', encoding='utf-8-sig') as f:
                    lines = f.readlines()
                    print(f"\nstops.txt contains {len(lines) - 1} stops")
                    
    except Exception as e:
        print(f"Error downloading GTFS data: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = download_gtfs_static_data()
    if not success:
        exit(1)