"""
Sensitivity-based predictor for model metrics.
"""
from typing import Dict, Optional
from app.models.experiment import ExperimentJSON


class SensitivityPredictor:
    """
    Predictor that estimates metric changes based on parameter sensitivity.
    
    Uses a penalty/sensitivity model where:
    - For each parameter, calculate normalized deviation from baseline
    - Apply sensitivity weights to estimate metric impact
    - Combine impacts across all parameters
    """
    
    def __init__(self, baseline_experiment: ExperimentJSON):
        self.baseline = baseline_experiment
        self.baseline_config = baseline_experiment.configuration
        self.baseline_metrics = {m.param: m.compressed for m in baseline_experiment.metrics}
        self.full_metrics = {m.param: m.full for m in baseline_experiment.metrics}
        
        # Build UI ranges and sensitivities
        self.param_ranges = {}
        for param_name, param_value in self.baseline_config.items():
            critical_info = None
            if baseline_experiment.critical_parameters:
                critical_info = baseline_experiment.critical_parameters.get(param_name)
            
            if critical_info:
                ui_min = critical_info.min
                ui_max = critical_info.max
            else:
                # Default UI range: +/- 20% of baseline
                ui_min = param_value * 0.8
                ui_max = param_value * 1.2
            
            # Calculate max deviation for normalization
            max_deviation = max(
                param_value - ui_min,
                ui_max - param_value
            )
            self.param_ranges[param_name] = {
                'baseline': param_value,
                'ui_min': ui_min,
                'ui_max': ui_max,
                'max_deviation': max_deviation if max_deviation > 0 else 1.0
            }
    
    def _calculate_normalized_deviation(self, param_name: str, new_value: float) -> float:
        """Calculate normalized deviation for a parameter."""
        if param_name not in self.param_ranges:
            return 0.0
        
        range_info = self.param_ranges[param_name]
        baseline = range_info['baseline']
        max_dev = range_info['max_deviation']
        
        # Normalized deviation
        deviation = (new_value - baseline) / max_dev
        return deviation
    
    def _calculate_penalty(self, deviation: float, param_name: str, metric_name: str) -> float:
        """
        Calculate penalty for a given deviation.
        
        Uses different sensitivity for positive/negative deviations.
        For MVP, uses linear model with optional sensitivity weights.
        """
        # Default sensitivity (can be enhanced with actual sensitivity data)
        # For now, assume uniform sensitivity of 0.5 for quality metrics
        if 'accuracy' in metric_name or 'f1' in metric_name:
            sensitivity = 0.5  # Quality metrics are sensitive
            k = 1.5  # Exponent for non-linearity
        elif 'latency' in metric_name:
            sensitivity = 0.3  # Latency less sensitive to param changes
            k = 1.2
        elif 'memory' in metric_name or 'params' in metric_name:
            # Memory/params typically don't change with param tuning
            # unless the parameter directly affects model structure
            return 0.0
        else:
            sensitivity = 0.3
            k = 1.2
        
        # Penalty calculation with asymmetry
        abs_dev = abs(deviation)
        if deviation < 0:
            penalty = sensitivity * (abs_dev ** k)
        else:
            penalty = sensitivity * (abs_dev ** k)
        
        return penalty
    
    def predict(self, configuration: Dict[str, float]) -> Dict[str, float]:
        """
        Predict metrics for a given configuration.
        
        Args:
            configuration: Dictionary of parameter values
            
        Returns:
            Dictionary of predicted metric values
        """
        predictions = {}
        
        for metric in self.baseline.metrics:
            metric_name = metric.param
            baseline_value = self.baseline_metrics[metric_name]
            
            # Calculate total penalty for this metric
            total_penalty = 0.0
            
            for param_name, param_value in configuration.items():
                if param_name not in self.param_ranges:
                    continue
                
                deviation = self._calculate_normalized_deviation(param_name, param_value)
                penalty = self._calculate_penalty(deviation, param_name, metric_name)
                total_penalty += penalty
            
            # Apply penalty based on metric direction
            if 'accuracy' in metric_name or 'f1' in metric_name:
                # Higher is better - penalty reduces the value
                predicted = baseline_value - total_penalty
                predicted = max(0.0, min(1.0, predicted))  # Clamp to [0, 1]
            elif 'latency' in metric_name or 'memory' in metric_name or 'params' in metric_name:
                # Lower is better - penalty increases the value
                predicted = baseline_value + total_penalty * baseline_value
                predicted = max(0.0, predicted)  # Clamp to >= 0
            else:
                # Default: higher is better
                predicted = baseline_value - total_penalty
            
            predictions[metric_name] = round(predicted, 6)
        
        return predictions
