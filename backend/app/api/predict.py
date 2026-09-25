from fastapi import APIRouter, HTTPException, Request

from ..models.experiment import Experiment, normalize_experiment_payload
from ..models.prediction import PredictionRequest, PredictionResponse
from ..predictors.sensitivity import PredictionInputError

router = APIRouter(prefix="/api", tags=["prediction", "experiments"])


@router.post("/predict", response_model=PredictionResponse)
def predict(request: Request, payload: PredictionRequest) -> PredictionResponse:
    try:
        return request.app.state.prediction_service.predict(payload.parameters)
    except PredictionInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/reset", response_model=PredictionResponse)
def reset(request: Request) -> PredictionResponse:
    try:
        return request.app.state.prediction_service.reset()
    except PredictionInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/experiments")
def list_experiments(request: Request) -> list[dict]:
    return [
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
    ]


@router.get("/experiments/{experiment_id}")
def get_experiment(request: Request, experiment_id: str) -> Experiment:
    try:
        return request.app.state.store.get_experiment(experiment_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/experiments", response_model=Experiment, status_code=201)
def save_experiment(request: Request, payload: dict) -> Experiment:
    try:
        normalized = normalize_experiment_payload(payload)
        experiment = Experiment.model_validate(normalized)
        request.app.state.store.save_experiment(experiment)
        request.app.state.influx_service.write_actual(experiment)
        return experiment
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc