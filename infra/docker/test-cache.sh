#!/bin/bash

echo "🔍 Testing MTA Cache Proxy"
echo "========================="

# Check if cache service is running
docker compose ps cache | grep -q "Up" || {
    echo "❌ Cache service is not running!"
    echo "Start it first with: docker compose up -d cache"
    exit 1
}

# Test each feed endpoint
test_endpoint() {
    local endpoint=$1
    local name=$2
    
    echo -n "Testing $name ($endpoint): "
    response=$(curl -s -I "http://localhost:8080/$endpoint" | head -1)
    status=$(echo "$response" | awk '{print $2}')
    
    if [[ "$status" == "200" ]]; then
        echo "✅ OK - $response"
        
        # Get cache status
        cache_status=$(curl -s -I "http://localhost:8080/$endpoint" | grep -i "X-Cache-Status" | awk '{print $2}')
        echo "  Cache status: $cache_status"
        
        # Verify content type
        content_type=$(curl -s -I "http://localhost:8080/$endpoint" | grep -i "Content-Type" | awk '{print $2}')
        echo "  Content-Type: $content_type"
        
        # Get content length
        content_length=$(curl -s -I "http://localhost:8080/$endpoint" | grep -i "Content-Length" | awk '{print $2}')
        echo "  Content-Length: $content_length bytes"
        
        # Get first few bytes to verify it's binary
        first_bytes=$(curl -s "http://localhost:8080/$endpoint" | head -c 20 | xxd -p | tr -d '\n')
        echo "  First bytes: $first_bytes"
    else
        echo "❌ Failed - $response"
    fi
    
    echo ""
}

# Test each feed
test_endpoint "gtfs-ace" "ACE Lines"
test_endpoint "gtfs-bdfm" "BDFM Lines"
test_endpoint "gtfs-g" "G Line"
test_endpoint "gtfs-jz" "JZ Lines"
test_endpoint "gtfs-l" "L Line"
test_endpoint "gtfs-nqrw" "NQRW Lines"
test_endpoint "gtfs-123456" "1-7 Lines"
test_endpoint "gtfs-si" "Staten Island Railway"

echo "==================================================="
echo "🔄 Running 10 requests to test caching performance:"

for i in {1..10}; do
    echo -n "Request $i: "
    time curl -s -o /dev/null "http://localhost:8080/gtfs-ace"
    echo ""
done

echo ""
echo "✅ Cache testing complete."
echo "If you see MISS followed by HIT in the cache status, and the timing improves"
echo "on subsequent requests, caching is working correctly."