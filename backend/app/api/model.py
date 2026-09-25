from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["model"])


@router.get("/model")
def get_model(request: Request) -> dict:
    return request.app.state.model_service.public_model()