from fastapi import APIRouter, HTTPException, Request

from ..json_util import nan_to_none
from ..models.experiment import Experiment, normalize_experiment_payload
from ..models.prediction import PredictionRequest, PredictionResponse
from ..predictors.sensitivity import PredictionInputError

router = APIRouter(prefix="/api", tags=["prediction", "experiments"])


@router.post("/predict")
def predict(request: Request, payload: PredictionRequest) -> dict:
    try:
        response = request.app.state.prediction_service.predict(payload.parameters)
    except PredictionInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return nan_to_none(response.model_dump(mode="python"))


@router.post("/reset")
def reset(request: Request) -> dict:
    try:
        response = request.app.state.prediction_service.reset()
    except PredictionInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return nan_to_none(response.model_dump(mode="python"))


@router.get("/experiments")
def list_experiments(request: Request) -> list[dict]:
    return nan_to_none([
        {
            "experiment_id": experiment.experiment_id,
            "timestamp": experiment.meta.timestamp,
            "configuration": experiment.configuration,
            "metrics": {
                metric.param: metric.compressed for metric in experiment.metrics
            },
            "model_id": experiment.meta.model_id,
        }
        for experiment in request.app.state.store.list_experiments()
    ])


@router.get("/experiments/{experiment_id}")
def get_experiment(request: Request, experiment_id: str) -> dict:
    try:
        experiment = request.app.state.store.get_experiment(experiment_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return nan_to_none(experiment.model_dump(mode="python", by_alias=True))


@router.post("/experiments", status_code=201)
def save_experiment(request: Request, payload: dict) -> dict:
    try:
        normalized = normalize_experiment_payload(payload)
        experiment = Experiment.model_validate(normalized)
        request.app.state.store.save_experiment(experiment)
        request.app.state.influx_service.write_actual(experiment)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return nan_to_none(experiment.model_dump(mode="python", by_alias=True))