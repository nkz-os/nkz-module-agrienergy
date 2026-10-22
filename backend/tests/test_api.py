"""
Tests for AgriEnergy Orchestrator Backend
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


class TestHealth:
    """Health endpoint tests."""
    
    def test_health_check(self, client):
        """Test health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
        assert "version" in data


class TestAPI:
    """API endpoint tests."""
    
    def test_docs_available(self, client):
        """Test OpenAPI docs are available."""
        response = client.get("/api/agrienergy/docs")
        # Should return HTML or redirect
        assert response.status_code in [200, 307]
    
    def test_openapi_schema(self, client):
        """Test OpenAPI schema is generated."""
        response = client.get("/api/agrienergy/openapi.json")
        assert response.status_code == 200
        
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema
    
    def test_list_data_requires_auth_or_404(self, client):
        """List/data endpoint either requires auth (401/403) or is not implemented (404)."""
        response = client.get("/api/agrienergy/data")
        assert response.status_code in [401, 403, 404]

    def test_simulate_returns_expected_shape(self, client):
        """POST /simulate returns 200 and SimulationResponse shape."""
        payload = {
            "tracker": {
                "id": "tracker-01",
                "panel_width": 2.0,
                "panel_length": 4.0,
                "capacity_w": 1000,
                "min_tilt": -60,
                "max_tilt": 60,
                "lat": 43.3,
                "lon": -2.0,
                "parent_parcel_id": "parcel-01",
            },
            "parcel": {"id": "parcel-01", "slope": 5.0, "aspect": 180.0},
            "telemetry": {
                "timestamp": "2025-06-15T12:00:00Z",
                "ghi": 800,
                "dni": 600,
                "dhi": 200,
                "actual_tilt": 0,
                "actual_azimuth": 180,
            },
            "target_tilt": 30,
        }
        response = client.post("/api/agrienergy/simulate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "expected_power_w" in data
        assert "shadow_area_m2" in data
        assert "shadow_polygon_2d" in data
        assert isinstance(data["expected_power_w"], (int, float))
        assert isinstance(data["shadow_area_m2"], (int, float))
        assert isinstance(data["shadow_polygon_2d"], list)

    def test_admin_stats_requires_auth(self, client):
        """GET /admin/stats returns 401 without token."""
        response = client.get("/api/agrienergy/admin/stats")
        assert response.status_code == 401
