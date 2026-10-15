"""FastAPI app factory, mounts feature routes"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ombuds import config
from ombuds.features.claims_triage.api.routes import router as claims_triage_router
from ombuds.features.claims_triage.application.runtime import build_runtime
from ombuds.platform.ai.tool_loop import ToolDispatcher
from ombuds.platform.guardrails.api import router as approvals_router
from ombuds.platform.guardrails.approval_gate import ApprovalStore
from ombuds.platform.infrastructure.postgres import create_pool
from ombuds.platform.observability.logging import configure_logging


@asynccontextmanager
async def _postgres_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the Postgres pool for the life of the app: open it, build the runtime over it, close it on shutdown."""
    pool = create_pool(config.DATABASE_URL, config.DATABASE_POOL_MAX_SIZE)
    runtime = build_runtime(pool)
    app.state.approvals = runtime.approvals
    app.state.registry = runtime.registry
    try:
        yield
    finally:
        pool.close()


def create_app(approvals: ApprovalStore | None = None, registry: ToolDispatcher | None = None) -> FastAPI:
    """Build the FastAPI app: the claims-triage feature's routes plus the platform-level approvals routes.

    The approval store and tool registry are chosen here, the composition root, and reached by routes through
    `Depends`. By default both come from the Postgres-backed runtime, opened at startup and closed at
    shutdown. Tests pass `approvals` and/or `registry` (e.g. an in-memory `ApprovalGate`) to skip the
    database; a route whose dependency was not passed fails if called.
    """
    configure_logging()
    if approvals is None and registry is None:
        app = FastAPI(title="ombuds", lifespan=_postgres_lifespan)
    else:
        app = FastAPI(title="ombuds")
        if approvals is not None:
            app.state.approvals = approvals
        if registry is not None:
            app.state.registry = registry
    app.include_router(claims_triage_router)
    app.include_router(approvals_router)
    return app


app = create_app()
