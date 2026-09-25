from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.health import router as health_router
from .api.model import router as model_router
from .api.predict import router as predict_router
from .config import Settings
from .services.experiment_store import ExperimentStore
from .services.influx_service import InfluxService
from .services.model_service import ModelService
from .services.prediction_service import PredictionService

logging.basicConfig(level=logging.INFO)


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()
    store = ExperimentStore(configured)
    model_service = ModelService(store)
    influx_service = InfluxService(configured)
    prediction_service = PredictionService(store, model_service, influx_service)

    app = FastAPI(
        title="Interactive Model Compression Backend",
        version="1.0.0",
        description=(
            "Explainable sensitivity predictions for compression parameters. "
            "Actual black-box results and predicted results are stored separately."
        ),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.state.settings = configured
    app.state.store = store
    app.state.model_service = model_service
    app.state.influx_service = influx_service
    app.state.prediction_service = prediction_service
    app.include_router(health_router)
    app.include_router(model_router)
    app.include_router(predict_router)
    return app


app = create_app()