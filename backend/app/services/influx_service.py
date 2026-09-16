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
        return point.time(timestamp).field("value", float(value)).field("metric_name", metric)

    def write_actual(self, experiment: Experiment, required: bool = False) -> bool:
        try:
            from influxdb_client import Point
        except ImportError as exc:
            if required or self.settings.influx_required:
                raise RuntimeError("influxdb-client is not installed") from exc
            logger.warning("influxdb-client is not installed; skipping actual ingestion")
            return False

        model_id = experiment.meta.model_id or "demo_model_v1"
        tags = {
            "model_id": model_id,
            "experiment_id": experiment.experiment_id,
            "result_type": "actual",
            "prediction_mode": "black_box",
        }
        points: list[Any] = []
        for metric in experiment.metrics:
            point = self._metric_point(
                Point,
                metric.param,
                metric.compressed,
                experiment.meta.timestamp,
                {**tags, "metric": metric.param},
            )
            point = (
                point.field("full_value", float(metric.full))
                .field("compressed_value", float(metric.compressed))
                .field("absolute_delta", float(metric.compressed - metric.full))
            )
            points.append(point)
        summary = Point("model_results")
        for name, tag_value in tags.items():
            summary = summary.tag(name, tag_value)
        summary = summary.time(experiment.meta.timestamp)
        for metric in experiment.metrics:
            summary = summary.field(metric.param, float(metric.compressed))
        points.append(summary)
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
            "support_level": str(support["level"]),
        }
        points: list[Any] = []
        for metric, value in prediction.items():
            point = self._metric_point(
                Point,
                metric,
                value,
                timestamp,
                {**common_tags, "metric": metric},
            ).field("support_score", float(support["score"]))
            points.append(point)

        summary = Point("model_results")
        for name, tag_value in common_tags.items():
            summary = summary.tag(name, tag_value)
        summary = (
            summary.time(timestamp)
            .field("support_score", float(support["score"]))
            .field("support_distance", float(support["distance"]))
        )
        for name, value in configuration.items():
            summary = summary.field(f"config_{name}", float(value))
        for name, value in prediction.items():
            summary = summary.field(name, float(value))
        points.append(summary)
        return self._write(points, required=required)