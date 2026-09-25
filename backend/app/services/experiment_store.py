from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models.experiment import Experiment, normalize_experiment_payload


class ExperimentStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.experiments_dir.mkdir(parents=True, exist_ok=True)

    def _comparison_candidates(self) -> list[Path]:
        configured = self.settings.comparison_path
        candidates = [configured]
        if configured == Path("comparison.json"):
            candidates.append(self.settings.data_dir / "comparison.json")
        elif configured == self.settings.data_dir / "comparison.json":
            candidates.append(Path("comparison.json"))
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"data file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"expected a JSON object in {path}")
        return value

    def _load_experiment_file(self, path: Path) -> tuple[Experiment, dict[str, Any]]:
        raw = self._read_json(path)
        source_payload = raw
        # After an interactive prediction, model.json is a user buffer rather
        # than a complete experiment. Keep a canonical source snapshot in that
        # buffer so the documented fallback chain remains usable if the source
        # file is temporarily unavailable.
        if "meta" not in source_payload or "metrics" not in source_payload:
            embedded = raw.get("source_experiment")
            if isinstance(embedded, dict):
                source_payload = embedded
        normalized = normalize_experiment_payload(source_payload, path.stem)
        return Experiment.model_validate(normalized), raw

    def load_source(self) -> tuple[Experiment, dict[str, Any], Path]:
        for candidate in self._comparison_candidates():
            if candidate.exists():
                experiment, raw = self._load_experiment_file(candidate)
                return experiment, raw, candidate

        if self.settings.model_path.exists():
            experiment, raw = self._load_experiment_file(self.settings.model_path)
            return experiment, raw, self.settings.model_path

        experiment_files = sorted(self.settings.experiments_dir.glob("*.json"))
        if experiment_files:
            candidate = experiment_files[-1]
            experiment, raw = self._load_experiment_file(candidate)
            return experiment, raw, candidate

        raise FileNotFoundError(
            "No comparison.json, data/model.json, or experiment snapshots were found"
        )

    def ensure_model_buffer(self, source_raw: dict[str, Any]) -> None:
        if self.settings.model_path.exists():
            return
        self.write_json(self.settings.model_path, source_raw)

    def load_buffer(self) -> dict[str, Any]:
        if not self.settings.model_path.exists():
            source_experiment, source_raw, _ = self.load_source()
            del source_experiment
            self.ensure_model_buffer(source_raw)
        return self._read_json(self.settings.model_path)

    @staticmethod
    def write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
        temporary.replace(path)

    def write_buffer(self, value: dict[str, Any]) -> None:
        self.write_json(self.settings.model_path, value)

    def reset_buffer(self, source_raw: dict[str, Any]) -> None:
        # Reset deliberately copies the immutable source, never the last buffer
        # and never the latest experiment snapshot.
        self.write_buffer(source_raw)

    def save_experiment(self, experiment: Experiment) -> Path:
        path = self.settings.experiments_dir / f"{experiment.experiment_id}.json"
        self.write_json(path, experiment.model_dump(mode="json", by_alias=True))
        return path

    def list_experiments(self) -> list[Experiment]:
        experiments: list[Experiment] = []
        for path in sorted(self.settings.experiments_dir.glob("*.json")):
            try:
                experiment, _ = self._load_experiment_file(path)
            except (ValueError, TypeError):
                continue
            experiments.append(experiment)
        return experiments

    def get_experiment(self, experiment_id: str) -> Experiment:
        path = self.settings.experiments_dir / f"{experiment_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"experiment not found: {experiment_id}")
        experiment, _ = self._load_experiment_file(path)
        return experiment

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()