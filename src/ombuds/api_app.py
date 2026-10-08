"""FastAPI app factory, mounts feature routes"""

from fastapi import FastAPI

from ombuds.features.claims_triage.api.routes import router as claims_triage_router
from ombuds.platform.guardrails.api import router as approvals_router
from ombuds.platform.observability.logging import configure_logging


def create_app() -> FastAPI:
    """Build the FastAPI app: the claims-triage feature's routes plus the platform-level approvals routes."""
    configure_logging()
    app = FastAPI(title="ombuds")
    app.include_router(claims_triage_router)
    app.include_router(approvals_router)
    return app


app = create_app()
