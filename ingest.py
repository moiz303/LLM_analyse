"""
Инжест comparison.json в InfluxDB. Читает конфиг из .env
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import os
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)

DEFAULTS = dict(
    url    = f"http://localhost:{os.getenv('INFLUXDB_PORT', '8086')}",
    token  = os.getenv("INFLUXDB_TOKEN", ""),
    org    = os.getenv("INFLUXDB_ORG", "mlops"),
    bucket = os.getenv("INFLUXDB_BUCKET", "model_comparison"),
)


def parse_timestamp(raw: str) -> datetime:
    """Строго парсим timestamp. Любая проблема — падаем сразу."""
    if not raw:
        raise ValueError("meta.timestamp отсутствует в JSON")
    ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if ts > datetime.now(timezone.utc):
        raise ValueError(
            f"timestamp {ts.isoformat()} в будущем — проверьте формат даты "
            f"(YYYY-MM-DD, а не DD-MM-YYYY)"
        )
    return ts


def ingest(json_path: str, **cfg):
    with open(json_path) as f:
        data = json.load(f)

    meta = data.get("meta", {})
    try:
        ts = parse_timestamp(meta.get("timestamp", ""))
    except ValueError as e:
        print(f"Недопустимый timestamp: {e}")
        sys.exit(1)

    full_name = meta.get("full_model", "full_model")
    comp_name = meta.get("compressed_model", "compressed_model")

    client = InfluxDBClient(url=cfg["url"], token=cfg["token"], org=cfg["org"])
    write_api = client.write_api(write_options=SYNCHRONOUS)

    points = []

    for m in data.get("metrics", []):
        full_v = float(m["full"])
        comp_v = float(m["compressed"])
        delta = comp_v - full_v
        points.append(
            Point("model_metric")
            .tag("param", m["param"])
            .tag("full_model", full_name)
            .tag("compressed_model", comp_name)
            .field("full", (full_v / full_v * 100) if full_v else 0.0)
            .field("compressed", (comp_v / full_v * 100) if full_v else 0.0)
            .field("delta", delta)
            .field("delta_pct", (delta / full_v * 100) if full_v else 0.0)
            .time(ts)
        )

    for c in data.get("per_class", []):
        full_v = float(c["full"])
        comp_v = float(c["compressed"])
        points.append(
            Point("per_class_metric")
            .tag("class", c["class"])
            .tag("full_model", full_name)
            .tag("compressed_model", comp_name)
            .field("full", full_v)
            .field("compressed", comp_v)
            .field("delta", full_v - comp_v)
            .time(ts)
        )

    if not points:
        print("В JSON не нашлось ни одной метрики")
        sys.exit(1)

    write_api.write(bucket=cfg["bucket"], record=points)
    print(f"Записано {len(points)} точек в InfluxDB ({cfg['url']}), time={ts.isoformat()}")
    client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Ingest comparison JSON into InfluxDB")
    p.add_argument("json_path", help="Путь к comparison.json")
    p.add_argument("--url", default=DEFAULTS["url"])
    p.add_argument("--token", default=DEFAULTS["token"])
    p.add_argument("--org", default=DEFAULTS["org"])
    p.add_argument("--bucket", default=DEFAULTS["bucket"])
    args = p.parse_args()

    if not args.token:
        print("Токен не задан. Заполните INFLUXDB_TOKEN в .env")
        sys.exit(1)

    ingest(args.json_path, url=args.url, token=args.token,
           org=args.org, bucket=args.bucket)