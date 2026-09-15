"""
Experiment Store - stores and retrieves experiment JSONs.
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from app.models.experiment import ExperimentJSON


class ExperimentStore:
    """Local file-based experiment store."""
    
    def __init__(self, data_dir: str = "data/experiments"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._experiments: Dict[str, ExperimentJSON] = {}
        self._load_experiments()
    
    def _load_experiments(self):
        """Load all experiments from disk."""
        for exp_file in self.data_dir.glob("*.json"):
            try:
                with open(exp_file) as f:
                    data = json.load(f)
                exp = ExperimentJSON.model_validate(data)
                self._experiments[exp.experiment_id] = exp
            except Exception as e:
                print(f"Warning: Could not load {exp_file}: {e}")
    
    def save_experiment(self, experiment: ExperimentJSON) -> None:
        """Save an experiment to disk."""
        exp_path = self.data_dir / f"{experiment.experiment_id}.json"
        with open(exp_path, 'w') as f:
            json.dump(experiment.model_dump(mode='json'), f, indent=2)
        self._experiments[experiment.experiment_id] = experiment
    
    def get_experiment(self, experiment_id: str) -> Optional[ExperimentJSON]:
        """Get an experiment by ID."""
        return self._experiments.get(experiment_id)
    
    def get_all_experiments(self) -> List[ExperimentJSON]:
        """Get all experiments."""
        return list(self._experiments.values())
    
    def get_baseline_experiment(self) -> Optional[ExperimentJSON]:
        """Get the baseline experiment (first one or most recent)."""
        if not self._experiments:
            return None
        # Return the first experiment as baseline for MVP
        return next(iter(self._experiments.values()))
