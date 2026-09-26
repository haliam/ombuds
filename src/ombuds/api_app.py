"""FastAPI app factory, mounts feature routes"""

from fastapi import FastAPI

from ombuds.features.claims_triage.api.routes import router as claims_triage_router


def create_app() -> FastAPI:
    """Build the FastAPI app. Currently mounts only the claims-triage feature's routes."""
    app = FastAPI(title="ombuds")
    app.include_router(claims_triage_router)
    return app


app = create_app()
