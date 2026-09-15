"""
Unit tests for experiment validation.
"""
import pytest
from app.models.experiment import ExperimentJSON, ExperimentMeta, MetricData


class TestExperimentValidation:
    """Test experiment JSON validation."""
    
    def test_valid_experiment(self):
        """Test that a valid experiment is accepted."""
        data = {
            "experiment_id": "exp_001",
            "meta": {
                "full_model": "model_fp16",
                "compressed_model": "model_nf4",
                "timestamp": "2026-09-15T10:00:00Z"
            },
            "configuration": {
                "param_a": 0.82,
                "param_b": 0.47
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
                {"param": "accuracy_top1", "full": 0.7613, "compressed": 0.7589}
            ],
            "per_class": []
        }
        
        exp = ExperimentJSON.model_validate(data)
        assert exp.experiment_id == "exp_001"
        assert len(exp.metrics) == 1
    
    def test_missing_experiment_id(self):
        """Test that missing experiment_id is rejected."""
        data = {
            "meta": {
                "full_model": "model_fp16",
                "compressed_model": "model_nf4",
                "timestamp": "2026-09-15T10:00:00Z"
            },
            "configuration": {"param_a": 0.82},
            "metrics": [{"param": "accuracy_top1", "full": 0.76, "compressed": 0.75}],
            "per_class": []
        }
        
        with pytest.raises(Exception):
            ExperimentJSON.model_validate(data)
    
    def test_invalid_accuracy_range(self):
        """Test that accuracy outside [0, 1] is rejected."""
        data = {
            "experiment_id": "exp_001",
            "meta": {
                "full_model": "model_fp16",
                "compressed_model": "model_nf4",
                "timestamp": "2026-09-15T10:00:00Z"
            },
            "configuration": {"param_a": 0.82},
            "metrics": [{"param": "accuracy_top1", "full": 1.5, "compressed": 0.75}],
            "per_class": []
        }
        
        with pytest.raises(Exception):
            ExperimentJSON.model_validate(data)
    
    def test_negative_latency(self):
        """Test that negative latency is rejected."""
        data = {
            "experiment_id": "exp_001",
            "meta": {
                "full_model": "model_fp16",
                "compressed_model": "model_nf4",
                "timestamp": "2026-09-15T10:00:00Z"
            },
            "configuration": {"param_a": 0.82},
            "metrics": [{"param": "latency_ms", "full": -10, "compressed": 5}],
            "per_class": []
        }
        
        with pytest.raises(Exception):
            ExperimentJSON.model_validate(data)
