"""
InfluxDB Service - handles writing data to InfluxDB.
"""
import os
from datetime import datetime, timezone
from typing import Dict, Optional

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Load environment variables
load_dotenv()


class InfluxDBService:
    """Service for writing prediction and experiment data to InfluxDB."""
    
    def __init__(self):
        self.url = os.getenv("INFLUXDB_URL", f"http://influxdb:{os.getenv('INFLUXDB_PORT', '8086')}")
        self.token = os.getenv("INFLUXDB_TOKEN", "")
        self.org = os.getenv("INFLUXDB_ORG", "mlops")
        self.bucket = os.getenv("INFLUXDB_BUCKET", "model_comparison")
        
        self._client: Optional[InfluxDBClient] = None
        self._write_api = None
    
    @property
    def client(self) -> InfluxDBClient:
        """Lazy initialization of InfluxDB client."""
        if self._client is None:
            self._client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        return self._client
    
    @property
    def write_api(self):
        """Get write API instance."""
        if self._write_api is None:
            _ = self.client
        return self._write_api
    
    def close(self):
        """Close the InfluxDB client."""
        if self._client:
            self._client.close()
            self._client = None
            self._write_api = None
    
    def write_prediction(
        self,
        model_id: str,
        configuration: Dict[str, float],
        predictions: Dict[str, float],
        support_score: float,
        support_level: str,
        prediction_mode: str,
        timestamp: Optional[datetime] = None
    ):
        """Write a prediction to InfluxDB."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        points = []
        
        # Create a point for each metric
        for metric_name, value in predictions.items():
            point = (
                Point("model_metric")
                .tag("param", metric_name)
                .tag("result_type", "predicted")
                .tag("prediction_mode", prediction_mode)
                .tag("model_id", model_id)
                .tag("support_level", support_level)
                .field("value", value)
                .field("support_score", support_score)
                .time(timestamp)
            )
            
            # Add configuration as tags
            for param_name, param_value in configuration.items():
                point = point.tag(f"config_{param_name}", str(param_value))
            
            points.append(point)
        
        if points:
            self.write_api.write(bucket=self.bucket, record=points)
    
    def write_actual_experiment(
        self,
        experiment_id: str,
        full_model: str,
        compressed_model: str,
        metrics: list,
        timestamp: datetime
    ):
        """Write actual experiment data to InfluxDB."""
        points = []
        
        for m in metrics:
            full_v = float(m["full"])
            comp_v = float(m["compressed"])
            delta = comp_v - full_v
            
            point = (
                Point("model_metric")
                .tag("param", m["param"])
                .tag("result_type", "actual")
                .tag("full_model", full_model)
                .tag("compressed_model", compressed_model)
                .tag("experiment_id", experiment_id)
                .field("full", full_v)
                .field("compressed", comp_v)
                .field("delta", delta)
                .field("delta_pct", (delta / full_v * 100) if full_v else 0.0)
                .time(timestamp)
            )
            points.append(point)
        
        if points:
            self.write_api.write(bucket=self.bucket, record=points)
