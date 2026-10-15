"""FastAPI app factory, mounts feature routes"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ombuds import config
from ombuds.features.claims_triage.api.routes import router as claims_triage_router
from ombuds.platform.guardrails.api import router as approvals_router
from ombuds.platform.guardrails.approval_gate import ApprovalStore
from ombuds.platform.infrastructure.postgres import create_pool
from ombuds.platform.infrastructure.repositories import PostgresApprovalStore
from ombuds.platform.observability.logging import configure_logging


@asynccontextmanager
async def _postgres_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the Postgres pool for the life of the app: open it, back the approval store with it, close it on shutdown."""
    pool = create_pool(config.DATABASE_URL, config.DATABASE_POOL_MAX_SIZE)
    app.state.approvals = PostgresApprovalStore(pool)
    try:
        yield
    finally:
        pool.close()


def create_app(approvals: ApprovalStore | None = None) -> FastAPI:
    """Build the FastAPI app: the claims-triage feature's routes plus the platform-level approvals routes.

    The approval store is chosen here, the composition root, and reached by routes through `Depends`. By
    default it is the Postgres store, opened at startup and closed at shutdown; tests pass `approvals` (e.g. an
    in-memory `ApprovalGate`) to skip the database.
    """
    configure_logging()
    if approvals is None:
        app = FastAPI(title="ombuds", lifespan=_postgres_lifespan)
    else:
        app = FastAPI(title="ombuds")
        app.state.approvals = approvals
    app.include_router(claims_triage_router)
    app.include_router(approvals_router)
    return app


app = create_app()
