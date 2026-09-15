import os
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import model_router, predict_router, health_router
from app.services import ExperimentStore, ModelService, PredictionService, InfluxDBService
from app.models.experiment import ExperimentJSON


# Global services reference
_services: Optional[Dict[str, Any]] = None


def get_app_services() -> Optional[Dict[str, Any]]:
    """Get the global services' dictionary."""
    return _services


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    global _services
    print("Starting up backend services...")
    experiment_store = ExperimentStore()
    
    # Load initial experiment from comparison.json if no experiments exist
    if not experiment_store.get_all_experiments():
        import json
        from pathlib import Path
        
        comparison_path = Path("comparison.json")
        if comparison_path.exists():
            with open(comparison_path) as f:
                data = json.load(f)
            
            # Add experiment_id if missing
            if "experiment_id" not in data:
                data["experiment_id"] = "exp_001"
            
            # Add configuration if missing (extract from metrics or use defaults)
            if "configuration" not in data:
                # Default configuration based on typical parameters
                data["configuration"] = {
                    "param_a": 0.82,
                    "param_b": 0.47,
                    "param_c": 1.15
                }
            
            try:
                exp = ExperimentJSON.model_validate(data)
                experiment_store.save_experiment(exp)
                print(f"Loaded initial experiment: {exp.experiment_id}")
            except Exception as e:
                print(f"Warning: Could not load comparison.json: {e}")
    
    baseline_exp = experiment_store.get_baseline_experiment()
    
    if baseline_exp is None:
        print("Warning: No baseline experiment available")
        model_service = None
        prediction_service = None
    else:
        model_service = ModelService(experiment_store)
        prediction_service = PredictionService(baseline_exp)
    
    influx_service = InfluxDBService()
    
    _services = {
        "experiment_store": experiment_store,
        "model_service": model_service,
        "prediction_service": prediction_service,
        "influx_service": influx_service,
    }
    
    print("Backend services initialized successfully")
    
    yield
    
    # Shutdown
    print("Shutting down backend services...")
    if influx_service:
        influx_service.close()
    _services = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="Model Compression Demo Backend",
        description="Backend API for interactive model compression research",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # Configure CORS
    allowed_origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(model_router)
    app.include_router(predict_router)
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("BACKEND_PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
