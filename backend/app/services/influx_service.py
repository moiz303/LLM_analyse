from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..config import Settings
from ..models.experiment import Experiment

logger = logging.getLogger(__name__)


class InfluxService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.influx_url
            and self.settings.influx_org
            and self.settings.influx_bucket
            and self.settings.influx_token
        )

    def _client(self):
        if not self.configured:
            return None
        try:
            from influxdb_client import InfluxDBClient
        except ImportError as exc:
            raise RuntimeError(
                "influxdb-client is not installed; install requirements.txt"
            ) from exc
        return InfluxDBClient(
            url=self.settings.influx_url,
            token=self.settings.influx_token,
            org=self.settings.influx_org,
        )

    @staticmethod
    def _write_points(client: Any, points: list[Any], bucket: str, org: str) -> None:
        write_api = client.write_api()
        write_api.write(bucket=bucket, org=org, record=points)
        write_api.close()

    def _write(self, points: list[Any], required: bool = False) -> bool:
        if not self.configured:
            message = "InfluxDB is not configured; datapoint was not written"
            if required or self.settings.influx_required:
                raise RuntimeError(message)
            logger.warning(message)
            return False
        try:
            client = self._client()
            assert client is not None
            self._write_points(
                client,
                points,
                self.settings.influx_bucket,
                self.settings.influx_org,
            )
            client.close()
            return True
        except Exception:
            if required or self.settings.influx_required:
                raise
            logger.exception("InfluxDB write failed; returning API response without persistence")
            return False

    @staticmethod
    def _metric_point(point_cls: Any, metric: str, value: float, timestamp: datetime, tags: dict[str, str]):
        point = point_cls("metric_results")
        for name, tag_value in tags.items():
            point = point.tag(name, tag_value)
        return point.time(timestamp).field(metric, float(value))

    def write_actual(self, experiment: Experiment, required: bool = False) -> bool:
        try:
            from influxdb_client import Point
        except ImportError as exc:
            if required or self.settings.influx_required:
                raise RuntimeError("influxdb-client is not installed") from exc
            logger.warning("influxdb-client is not installed; skipping actual ingestion")
            return False

        model_id = experiment.meta.model_id or "demo_model_v1"
        points: list[Any] = []

        # Записываем Full модель - одна точка со всеми метриками
        full_tags = {
            "model_id": model_id,
            "experiment_id": experiment.experiment_id,
            "result_type": "actual",
            "prediction_mode": "black_box",
            "model_type": "full",
        }
        full_point = Point("metric_results").time(experiment.meta.timestamp)
        for name, tag_value in full_tags.items():
            full_point = full_point.tag(name, tag_value)
        # Динамически записываем все метрики из experiment.metrics
        for metric in experiment.metrics:
            if metric.full is not None:
                full_point = full_point.field(metric.param, float(metric.full))
        points.append(full_point)

        # Записываем Compressed модель - одна точка со всеми метриками
        compressed_tags = {
            "model_id": model_id,
            "experiment_id": experiment.experiment_id,
            "result_type": "actual",
            "prediction_mode": "black_box",
            "model_type": "compressed",
        }
        compressed_point = Point("metric_results").time(experiment.meta.timestamp)
        for name, tag_value in compressed_tags.items():
            compressed_point = compressed_point.tag(name, tag_value)
        # Динамически записываем все метрики из experiment.metrics
        for metric in experiment.metrics:
            if metric.compressed is not None:
                compressed_point = compressed_point.field(metric.param, float(metric.compressed))
        points.append(compressed_point)

        return self._write(points, required=required)

    def write_prediction(
        self,
        model_id: str,
        configuration: dict[str, float],
        prediction: dict[str, float],
        support: dict[str, Any],
        prediction_mode: str = "sensitivity_model",
        required: bool = False,
    ) -> bool:
        try:
            from influxdb_client import Point
        except ImportError as exc:
            if required or self.settings.influx_required:
                raise RuntimeError("influxdb-client is not installed") from exc
            logger.warning("influxdb-client is not installed; skipping prediction persistence")
            return False

        timestamp = datetime.now(timezone.utc)
        common_tags = {
            "model_id": model_id,
            "experiment_id": "interactive",
            "result_type": "predicted",
            "prediction_mode": prediction_mode,
            "model_type": "predicted",
            "support_level": str(support["level"]),
        }
        point = Point("metric_results").time(timestamp)
        for name, tag_value in common_tags.items():
            point = point.tag(name, tag_value)
        for metric, value in prediction.items():
            point = point.field(metric, float(value))
        points = [point]

        return self._write(points, required=required)