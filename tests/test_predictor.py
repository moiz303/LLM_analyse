"""
Unit tests for the sensitivity predictor.
"""
import pytest
from app.models.experiment import ExperimentJSON
from app.predictors.sensitivity import SensitivityPredictor


@pytest.fixture
def baseline_experiment():
    """Create a baseline experiment for testing."""
    data = {
        "experiment_id": "exp_001",
        "meta": {
            "full_model": "model_fp16",
            "compressed_model": "model_nf4",
            "timestamp": "2026-09-15T10:00:00Z"
        },
        "configuration": {
            "param_a": 0.82,
            "param_b": 0.47,
            "param_c": 1.15
        },
        "critical_parameters": {
            "param_a": {
                "critical": True,
                "baseline": 0.82,
                "min": 0.70,
                "max": 0.90
            }
        },
        "metrics": [
            {"param": "accuracy_top1", "full": 0.7613, "compressed": 0.7589},
            {"param": "f1_macro", "full": 0.7542, "compressed": 0.7498},
            {"param": "latency_ms", "full": 45.2, "compressed": 12.8},
            {"param": "memory_mb", "full": 512.0, "compressed": 128.0}
        ],
        "per_class": []
    }
    return ExperimentJSON.model_validate(data)


class TestSensitivityPredictor:
    """Test the sensitivity predictor."""
    
    def test_baseline_prediction(self, baseline_experiment):
        """Test that predicting baseline returns baseline metrics (BE-009)."""
        predictor = SensitivityPredictor(baseline_experiment)
        
        # Predict with baseline configuration
        result = predictor.predict(baseline_experiment.configuration)
        
        # Check that predictions match baseline compressed metrics
        assert abs(result["accuracy_top1"] - 0.7589) < 0.01
        assert abs(result["f1_macro"] - 0.7498) < 0.01
        assert abs(result["latency_ms"] - 12.8) < 0.1
        assert abs(result["memory_mb"] - 128.0) < 0.1
    
    def test_parameter_change_affects_accuracy(self, baseline_experiment):
        """Test that changing a parameter affects quality metrics."""
        predictor = SensitivityPredictor(baseline_experiment)
        
        # Change param_a significantly
        new_config = {
            "param_a": 0.75,  # Changed from 0.82
            "param_b": 0.47,
            "param_c": 1.15
        }
        
        result = predictor.predict(new_config)
        
        # Accuracy should be lower than baseline due to penalty
        assert result["accuracy_top1"] < 0.7589
    
    def test_multiple_parameter_changes(self, baseline_experiment):
        """Test that multiple parameter changes combine correctly."""
        predictor = SensitivityPredictor(baseline_experiment)
        
        # Change multiple parameters
        new_config = {
            "param_a": 0.75,
            "param_b": 0.40,
            "param_c": 1.20
        }
        
        result = predictor.predict(new_config)
        
        # Should still produce valid predictions
        assert 0 <= result["accuracy_top1"] <= 1
        assert 0 <= result["f1_macro"] <= 1
        assert result["latency_ms"] >= 0
        assert result["memory_mb"] >= 0
    
    def test_predictions_are_physically_valid(self, baseline_experiment):
        """Test that predictions respect physical constraints (BE-011)."""
        predictor = SensitivityPredictor(baseline_experiment)
        
        # Try extreme parameter values
        extreme_config = {
            "param_a": 0.70,  # At minimum
            "param_b": 0.35,
            "param_c": 0.95
        }
        
        result = predictor.predict(extreme_config)
        
        # Check constraints
        assert 0 <= result["accuracy_top1"] <= 1
        assert 0 <= result["f1_macro"] <= 1
        assert result["latency_ms"] >= 0
        assert result["memory_mb"] >= 0
