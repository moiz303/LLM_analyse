"""
Integration tests for the API.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestAPIEndpoints:
    """Test API endpoints."""
    
    def test_health_check(self, client):
        """Test health endpoint (BE-031)."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    def test_get_model(self, client):
        """Test GET /api/model endpoint (BE-006)."""
        response = client.get("/api/model")
        
        # Should return model configuration or 404 if no data
        assert response.status_code in [200, 404, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "model_id" in data
            assert "parameters" in data
            assert "metrics" in data
    
    def test_predict_endpoint(self, client):
        """Test POST /api/predict endpoint (BE-013)."""
        request_data = {
            "parameters": {
                "param_a": 0.76,
                "param_b": 0.47,
                "param_c": 1.15
            }
        }
        
        response = client.post("/api/predict", json=request_data)
        
        # Should return prediction or error if no baseline
        assert response.status_code in [200, 400, 404, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "prediction" in data
            assert "baseline" in data
            assert "support_score" in data
            assert "support_level" in data
            assert "prediction_mode" in data
            
            # Check support level is valid
            assert data["support_level"] in ["high", "medium", "low"]
