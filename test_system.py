#!/usr/bin/env python3
"""Test script to verify NYC Subway Monitor is working correctly"""

import httpx
import asyncio
import json
from datetime import datetime

async def test_system():
    print("🚇 NYC Subway Monitor System Test")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    
    # Test 1: API Health
    print("\n1. Testing API Health...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/")
            if response.status_code == 200:
                print("✅ API is running")
                print(f"   Response: {response.json()}")
            else:
                print(f"❌ API returned status {response.status_code}")
    except Exception as e:
        print(f"❌ API connection failed: {e}")
        return
    
    # Test 2: Feed Status
    print("\n2. Testing Feed Status...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/api/v1/feeds/status")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Feed status endpoint working")
                print(f"   Active feeds: {', '.join(data['active_feeds'])}")
                print(f"   Loaded stations: {data['loaded_stations']}")
                print(f"   Recent updates: {len(data['recent_updates'])}")
            else:
                print(f"❌ Feed status returned {response.status_code}")
    except Exception as e:
        print(f"❌ Feed status failed: {e}")
    
    # Test 3: Train Positions
    print("\n3. Testing Train Positions...")
    try:
        async with httpx.AsyncClient() as client:
            # Test line 1
            response = await client.get(f"{base_url}/api/v1/feeds/positions/1")
            if response.status_code == 200:
                positions = response.json()
                print(f"✅ Train positions endpoint working")
                print(f"   Line 1 trains: {len(positions)}")
                if positions:
                    print(f"   Sample train: {positions[0]['train_id']} at {positions[0]['current_station']}")
            else:
                print(f"❌ Train positions returned {response.status_code}")
    except Exception as e:
        print(f"❌ Train positions failed: {e}")
    
    # Test 4: Anomalies
    print("\n4. Testing Anomalies Endpoint...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/api/v1/anomalies/")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Anomalies endpoint working")
                print(f"   Total anomalies: {data['total']}")
                print(f"   Active anomalies: {len(data['anomalies'])}")
            else:
                print(f"❌ Anomalies returned {response.status_code}")
    except Exception as e:
        print(f"❌ Anomalies failed: {e}")
    
    # Test 5: Frontend
    print("\n5. Testing Frontend...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:54149/")
            if response.status_code == 200:
                print("✅ Frontend is accessible")
                if "NYC Subway Monitor" in response.text:
                    print("   Page title verified")
            else:
                print(f"❌ Frontend returned {response.status_code}")
    except Exception as e:
        print(f"❌ Frontend connection failed: {e}")
    
    # Test 6: WebSocket
    print("\n6. Testing WebSocket...")
    print("   WebSocket endpoint: ws://localhost:8000/api/v1/ws/anomalies")
    print("   (WebSocket testing requires manual verification in browser)")
    
    print("\n" + "=" * 50)
    print("✅ System test complete!")
    print(f"   Timestamp: {datetime.now().isoformat()}")
    print("\nNOTE: The system needs to run for 5-10 minutes to start detecting anomalies.")

if __name__ == "__main__":
    asyncio.run(test_system())