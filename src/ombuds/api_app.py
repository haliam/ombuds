"""FastAPI app factory, mounts feature routes"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ombuds import config
from ombuds.features.claims_triage.api.routes import router as claims_triage_router
from ombuds.features.claims_triage.application.runtime import build_runtime
from ombuds.platform.ai.budget import BudgetExceededError
from ombuds.platform.ai.tool_loop import ToolDispatcher
from ombuds.platform.guardrails.api import router as approvals_router
from ombuds.platform.guardrails.approval_gate import ApprovalStore
from ombuds.platform.guardrails.policy_engine import OpaHttpPolicyEngine
from ombuds.platform.infrastructure.postgres import create_pool
from ombuds.platform.observability.logging import configure_logging
from ombuds.platform.observability.tracing import configure_tracing

_SCALAR_HTML = """<!doctype html>
<html>
  <head>
    <title>ombuds API reference</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
  </head>
  <body>
    <script id="api-reference" data-url="/openapi.json"></script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
  </body>
</html>
"""


@asynccontextmanager
async def _postgres_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the Postgres pool for the life of the app: open it, build the runtime over it, close it on shutdown."""
    pool = create_pool(config.DATABASE_URL, config.DATABASE_POOL_MAX_SIZE)
    runtime = build_runtime(
        pool, OpaHttpPolicyEngine(config.OPA_URL, config.OPA_TIMEOUT_SECONDS), config.PAYOUT_LIMIT_EUR
    )
    app.state.approvals = runtime.approvals
    app.state.registry = runtime.registry
    try:
        yield
    finally:
        pool.close()


def _budget_exceeded(request: Request, exc: Exception) -> JSONResponse:
    """The LLM spend cap is reached (ADR-0018): refuse with 429 instead of an opaque 500."""
    return JSONResponse(status_code=429, content={"detail": str(exc)})


def create_app(approvals: ApprovalStore | None = None, registry: ToolDispatcher | None = None) -> FastAPI:
    """Build the FastAPI app: the claims-triage feature's routes plus the platform-level approvals routes.

    The approval store and tool registry are chosen here, the composition root, and reached by routes through
    `Depends`. By default both come from the Postgres-backed runtime, opened at startup and closed at
    shutdown. Tests pass `approvals` and/or `registry` (e.g. an in-memory `ApprovalGate`) to skip the
    database; a route whose dependency was not passed fails if called.
    """
    configure_logging()
    configure_tracing(config.OTEL_TRACES_EXPORTER)
    if approvals is None and registry is None:
        app = FastAPI(title="ombuds", lifespan=_postgres_lifespan)
    else:
        app = FastAPI(title="ombuds")
        if approvals is not None:
            app.state.approvals = approvals
        if registry is not None:
            app.state.registry = registry
    app.add_exception_handler(BudgetExceededError, _budget_exceeded)
    app.include_router(claims_triage_router)
    app.include_router(approvals_router)

    @app.get("/scalar", include_in_schema=False)
    def scalar() -> HTMLResponse:
        """Scalar API reference, rendered from `/openapi.json` (alongside FastAPI's `/docs` and `/redoc`)."""
        return HTMLResponse(_SCALAR_HTML)

    return app


app = create_app()
