from __future__ import annotations

from typing import Any

from ..models.prediction import PredictionResponse
from ..predictors.sensitivity import SensitivityPredictor
from .experiment_store import ExperimentStore
from .influx_service import InfluxService
from .model_service import ModelService


class PredictionService:
    def __init__(
        self,
        store: ExperimentStore,
        model_service: ModelService,
        influx_service: InfluxService,
    ):
        self.store = store
        self.model_service = model_service
        self.influx_service = influx_service

    def _predictor(self) -> SensitivityPredictor:
        source, _, = self.model_service.source()
        model = self.model_service.configuration()
        return SensitivityPredictor(model, source, self.store.list_experiments())

    def predict(
        self,
        configuration: dict[str, float],
        persist: bool = True,
        update_buffer: bool = True,
    ) -> PredictionResponse:
        predictor = self._predictor()
        predictor.validate_configuration(configuration)
        prediction = predictor.predict(configuration)
        support = predictor.support(configuration)
        model = predictor.model
        baseline = {
            metric.name: metric.baseline_compressed for metric in model.metrics
        }

        persisted = False
        if persist:
            source_experiment = predictor.source_experiment.model_dump(
                mode="json", by_alias=True
            )
            self.influx_service.write_prediction(
                model_id=model.model_id,
                configuration=configuration,
                prediction=prediction,
                support=support,
                prediction_mode=predictor.mode,
            )
            if update_buffer:
                self.store.write_buffer(
                    {
                        "model_id": model.model_id,
                        "configuration": configuration,
                        "prediction": prediction,
                        "support": support,
                        "prediction_mode": predictor.mode,
                        "updated_at": self.store.now_iso(),
                        "source_experiment": source_experiment,
                    }
                )
            persisted = True
        return PredictionResponse(
            prediction_mode=predictor.mode,
            model_id=model.model_id,
            prediction=prediction,
            baseline=baseline,
            configuration=configuration,
            support=support,
            metrics=self.model_service.public_model()["metrics"],
            persisted=persisted,
        )

    def reset(self) -> PredictionResponse:
        _, source_raw = self.model_service.source()
        source, _, _ = self.store.load_source()
        self.store.reset_buffer(source_raw)
        configuration = {
            name: float(value) for name, value in source.configuration.items()
        }
        return self.predict(configuration, persist=True, update_buffer=False)