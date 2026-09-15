import json
from pathlib import Path
from typing import Dict, Optional

from app.models.experiment import ExperimentJSON
from app.models.model_config import ModelConfiguration, ParameterConfig, MetricConfig


class ModelService:
    """Service for model configuration and baseline data."""
    
    def __init__(self, experiment_store):
        self.experiment_store = experiment_store
        self._model_config: Optional[ModelConfiguration] = None
        self._baseline_metrics: Optional[Dict[str, float]] = None
    
    def get_model_configuration(self) -> Optional[ModelConfiguration]:
        """Get model configuration from stored experiments."""
        if self._model_config is not None:
            return self._model_config
        
        baseline_exp = self.experiment_store.get_baseline_experiment()
        if baseline_exp is None:
            return None

        parameters = {}
        
        # Extract parameters from configuration with default UI ranges
        for param_name, param_value in baseline_exp.configuration.items():
            critical_info = None
            if baseline_exp.critical_parameters:
                critical_info = baseline_exp.critical_parameters.get(param_name)
            
            if critical_info:
                ui_min = critical_info.min
                ui_max = critical_info.max
            else:
                # Default UI range: +/- 20% of baseline
                ui_min = param_value * 0.8
                ui_max = param_value * 1.2
            
            parameters[param_name] = ParameterConfig(
                baseline=param_value,
                ui_min=ui_min,
                ui_max=ui_max,
                sensitivity=None
            )
        
        # Define metric configurations
        metrics = {}
        for metric_data in baseline_exp.metrics:
            metric_name = metric_data.param
            # Determine direction based on metric type
            if 'accuracy' in metric_name or 'f1' in metric_name:
                direction = "higher_is_better"
            elif 'latency' in metric_name or 'memory' in metric_name or 'params' in metric_name:
                direction = "lower_is_better"
            else:
                direction = "higher_is_better"  # default
            
            metrics[metric_name] = MetricConfig(direction=direction)
        
        self._model_config = ModelConfiguration(
            model_id=f"{baseline_exp.meta.full_model}_vs_{baseline_exp.meta.compressed_model}",
            parameters=parameters,
            metrics=metrics
        )
        
        return self._model_config
    
    def get_baseline_metrics(self) -> Optional[Dict[str, float]]:
        """Get baseline (compressed) metrics from the baseline experiment."""
        if self._baseline_metrics is not None:
            return self._baseline_metrics
        
        baseline_exp = self.experiment_store.get_baseline_experiment()
        if baseline_exp is None:
            return None
        
        # Use compressed metrics as baseline
        self._baseline_metrics = {
            m.param: m.compressed for m in baseline_exp.metrics
        }
        
        return self._baseline_metrics
    
    def get_full_metrics(self) -> Optional[Dict[str, float]]:
        """Get full model metrics from the baseline experiment."""
        baseline_exp = self.experiment_store.get_baseline_experiment()
        if baseline_exp is None:
            return None
        
        return {m.param: m.full for m in baseline_exp.metrics}
