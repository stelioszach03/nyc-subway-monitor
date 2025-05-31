#!/bin/bash

echo "🚇 NYC Subway Monitor Status"
echo "============================"

# API Health
echo -n "Backend API: "
if curl -s http://localhost:8000/ > /dev/null; then
    echo "✅ Running"
else
    echo "❌ Down"
fi

# Frontend
echo -n "Frontend: "
if curl -s http://localhost:3001/ > /dev/null; then
    echo "✅ Running"
else
    echo "❌ Down"
fi

# Database
echo -n "PostgreSQL: "
STATION_COUNT=$(sudo -u postgres psql -t -c "SELECT COUNT(*) FROM stations;" subway_monitor 2>/dev/null | xargs)
if [ "$STATION_COUNT" -gt 400 ]; then
    echo "✅ $STATION_COUNT stations"
else
    echo "⚠️  Only $STATION_COUNT stations (check database)"
fi

# Feed Updates
echo -n "Feed Updates: "
UPDATES=$(sudo -u postgres psql -t -c "SELECT COUNT(*) FROM feed_updates WHERE timestamp > NOW() - INTERVAL '5 minutes';" subway_monitor 2>/dev/null | xargs)
echo "$UPDATES in last 5 min"

# Train Positions
echo -n "Train Positions: "
TRAINS=$(sudo -u postgres psql -t -c "SELECT COUNT(DISTINCT trip_id) FROM train_positions WHERE timestamp > NOW() - INTERVAL '1 minute';" subway_monitor 2>/dev/null | xargs)
echo "$TRAINS active trains"

# Anomalies
echo -n "Anomalies Today: "
ANOMALIES=$(sudo -u postgres psql -t -c "SELECT COUNT(*) FROM anomalies WHERE detected_at > CURRENT_DATE;" subway_monitor 2>/dev/null | xargs)
echo "$ANOMALIES detected"

# WebSocket Connections
echo -n "WebSocket Connections: "
WS_CONNECTIONS=$(curl -s http://localhost:8000/api/v1/ws/connections | jq -r '.active_connections' 2>/dev/null)
echo "${WS_CONNECTIONS:-0} active"

# Feed Status
echo -n "Feed Ingestion: "
FEED_STATUS=$(curl -s http://localhost:8000/api/v1/feeds/status | jq -r '.status' 2>/dev/null)
echo "${FEED_STATUS:-unknown}"

echo ""
echo "📊 Quick Stats:"
echo "==============="

# Recent train positions by line
echo "Recent train positions by line:"
sudo -u postgres psql -t -c "
SELECT 
    line, 
    COUNT(DISTINCT trip_id) as active_trains,
    COUNT(*) as total_positions
FROM train_positions 
WHERE timestamp > NOW() - INTERVAL '5 minutes'
GROUP BY line 
ORDER BY active_trains DESC;
" subway_monitor 2>/dev/null | head -10

echo ""
echo "🔄 System URLs:"
echo "==============="
echo "Frontend:     http://localhost:3001"
echo "Backend API:  http://localhost:8000"
echo "API Docs:     http://localhost:8000/api/v1/docs"
echo "WebSocket:    ws://localhost:8000/api/v1/ws/anomalies"