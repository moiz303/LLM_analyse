from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    comparison_path: Path
    model_path: Path
    experiments_dir: Path
    influx_url: str
    influx_org: str
    influx_bucket: str
    influx_token: str
    influx_required: bool
    cors_origins: list[str]

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("DATA_DIR", "data"))
        configured_comparison = Path(os.getenv("COMPARISON_PATH", "comparison.json"))
        model_path = Path(os.getenv("MODEL_PATH", str(data_dir / "model.json")))
        experiments_dir = Path(
            os.getenv("EXPERIMENTS_DIR", str(data_dir / "experiments"))
        )
        return cls(
            data_dir=data_dir,
            comparison_path=configured_comparison,
            model_path=model_path,
            experiments_dir=experiments_dir,
            influx_url=os.getenv("INFLUXDB_URL", ""),
            influx_org=os.getenv("INFLUXDB_ORG", "mlops"),
            influx_bucket=os.getenv("INFLUXDB_BUCKET", "model_comparison"),
            influx_token=os.getenv("INFLUXDB_TOKEN", ""),
            influx_required=os.getenv("INFLUXDB_REQUIRED", "false").lower()
            in {"1", "true", "yes"},
            cors_origins=_csv(
                os.getenv(
                    "FRONTEND_ORIGINS",
                    "http://localhost:5173,http://127.0.0.1:5173",
                )
            ),
        )