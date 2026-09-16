from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import Settings
from app.models.experiment import Experiment, normalize_experiment_payload
from app.services.experiment_store import ExperimentStore
from app.services.influx_service import InfluxService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a canonical experiment JSON and ingest actual results into InfluxDB."
    )
    parser.add_argument("path", type=Path, help="path to comparison.json or another experiment")
    parser.add_argument("--url", default=None)
    parser.add_argument("--org", default=None)
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--token", default=None)
    args = parser.parse_args()

    with args.path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    experiment = Experiment.model_validate(
        normalize_experiment_payload(raw, args.path.stem)
    )

    settings = Settings.from_env()
    overrides = {
        "influx_url": args.url or settings.influx_url,
        "influx_org": args.org or settings.influx_org,
        "influx_bucket": args.bucket or settings.influx_bucket,
        "influx_token": args.token or settings.influx_token,
        "influx_required": True,
    }
    settings = Settings(
        data_dir=settings.data_dir,
        comparison_path=settings.comparison_path,
        model_path=settings.model_path,
        experiments_dir=settings.experiments_dir,
        cors_origins=settings.cors_origins,
        **overrides,
    )
    store = ExperimentStore(settings)
    store.save_experiment(experiment)
    InfluxService(settings).write_actual(experiment, required=True)
    print(f"Validated and ingested {experiment.experiment_id} ({len(experiment.metrics)} metrics)")
    return 0


if __name__ == "__main__":
    sys.exit(main())