"""Integration tests for API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.db.database import get_db


@pytest.mark.asyncio
class TestFeedAPI:
    """Test feed ingestion endpoints."""

    async def test_get_feed_status(self, client: AsyncClient):
        """Test feed status endpoint."""
        response = await client.get("/api/v1/feeds/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "active_feeds" in data
        assert "update_interval" in data
        assert "recent_updates" in data

    async def test_refresh_feed(self, client: AsyncClient):
        """Test manual feed refresh."""
        response = await client.post("/api/v1/feeds/refresh/ace")
        
        # Might fail if no connection, but should return proper error
        assert response.status_code in [200, 503]
        if response.status_code == 503:
            assert "Failed to fetch feed" in response.json()["detail"]


@pytest.mark.asyncio
class TestAnomalyAPI:
    """Test anomaly detection endpoints."""

    async def test_list_anomalies(self, client: AsyncClient):
        """Test anomaly listing with pagination."""
        response = await client.get(
            "/api/v1/anomalies",
            params={"page": 1, "page_size": 10}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "anomalies" in data
        assert "total" in data
        assert "page" in data
        assert data["page"] == 1

    async def test_get_anomaly_stats(self, client: AsyncClient):
        """Test anomaly statistics endpoint."""
        response = await client.get("/api/v1/anomalies/stats?hours=24")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_today" in data
        assert "total_active" in data
        assert "by_type" in data
        assert "trend_24h" in data