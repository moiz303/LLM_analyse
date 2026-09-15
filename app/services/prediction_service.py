from typing import Dict, Tuple, Optional
from app.models.experiment import ExperimentJSON
from app.models.prediction import PredictionResult
from app.predictors.sensitivity import SensitivityPredictor


class PredictionService:
    """Service for making predictions based on parameter configurations."""
    
    def __init__(self, baseline_experiment: ExperimentJSON):
        self.baseline_experiment = baseline_experiment
        self.predictor = SensitivityPredictor(baseline_experiment)
        self.baseline_metrics = {m.param: m.compressed for m in baseline_experiment.metrics}
        self.all_experiments = [baseline_experiment]
    
    def add_experiment(self, experiment: ExperimentJSON):
        """Add an experiment to the store for better predictions."""
        self.all_experiments.append(experiment)
    
    def calculate_support(self, configuration: Dict[str, float]) -> Tuple[float, str]:
        """
        Calculate prediction support score based on distance to known experiments.
        
        Returns:
            Tuple of (score, level) where level is "high", "medium", or "low"
        """
        if len(self.all_experiments) == 0:
            return (0.0, "low")

        min_distance = float('inf')
        
        for exp in self.all_experiments:
            exp_config = exp.configuration
            distance = 0.0
            
            # Calculate Euclidean distance in normalized parameter space
            all_params = set(configuration.keys()) | set(exp_config.keys())
            
            for param in all_params:
                config_val = configuration.get(param, 0)
                exp_val = exp_config.get(param, 0)
                
                # Normalize by baseline value
                baseline_val = self.baseline_experiment.configuration.get(param, 1)
                if baseline_val != 0:
                    norm_diff = (config_val - exp_val) / abs(baseline_val)
                else:
                    norm_diff = config_val - exp_val
                
                distance += norm_diff ** 2
            
            distance = distance ** 0.5
            min_distance = min(min_distance, distance)

        # Score of 1.0 means exact match, 0.0 means very far
        if min_distance == 0:
            score = 1.0
        else:
            # Exponential decay with distance
            score = max(0.0, min(1.0, 1.0 / (1.0 + min_distance)))
        
        # Determine level
        if score >= 0.7:
            level = "high"
        elif score >= 0.4:
            level = "medium"
        else:
            level = "low"
        
        return (round(score, 2), level)
    
    def predict(self, configuration: Dict[str, float]) -> PredictionResult:
        """
        Make a prediction for the given configuration.
            
        Returns:
            PredictionResult with predictions, baseline, and support info
        """
        # Get predictions from the predictor
        predictions = self.predictor.predict(configuration)
        
        # Calculate support
        support_score, support_level = self.calculate_support(configuration)
        
        return PredictionResult(
            prediction=predictions,
            baseline=self.baseline_metrics,
            support_score=support_score,
            support_level=support_level,
            prediction_mode="sensitivity_model"
        )
    
    def validate_configuration(self, configuration: Dict[str, float]) -> Tuple[bool, Optional[str]]:
        """
        Validate a configuration before prediction.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        baseline_config = self.baseline_experiment.configuration
        
        # Check for unknown parameters
        for param_name in configuration:
            if param_name not in baseline_config:
                return (False, f"Unknown parameter: {param_name}")
        
        # Check for missing required parameters
        for param_name in baseline_config:
            if param_name not in configuration:
                return (False, f"Missing required parameter: {param_name}")
        
        # Check parameter ranges
        for param_name, param_value in configuration.items():
            if not isinstance(param_value, (int, float)):
                return (False, f"Parameter {param_name} must be a number")
            
            # Check critical parameter constraints if available
            if self.baseline_experiment.critical_parameters:
                critical_info = self.baseline_experiment.critical_parameters.get(param_name)
                if critical_info:
                    if param_value < critical_info.min or param_value > critical_info.max:
                        return (False, 
                                f"Parameter {param_name} value {param_value} is outside "
                                f"valid range [{critical_info.min}, {critical_info.max}]")
        
        return (True, None)
