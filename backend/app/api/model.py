from fastapi import APIRouter, Request
from ..json_util import nan_to_none

router = APIRouter(prefix="/api", tags=["model"])


@router.get("/model")
def get_model(request: Request) -> dict:
    return nan_to_none(request.app.state.model_service.public_model())