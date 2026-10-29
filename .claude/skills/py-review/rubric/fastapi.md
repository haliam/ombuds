# FastAPI lens

Applies when the files import `fastapi` or `pydantic`, or sit under an `api/` package. Where the repo has its own rules for these areas, they take precedence.

- **FA-01** · Major · Route handler holds business logic or talks to storage directly — logic in routers cannot be reused or tested without HTTP.
- **FA-02** · Major · Dependency taken from a module-level global instead of `Depends` — tests cannot override it and wiring is hidden.
- **FA-03** · Major · Request or response body is an untyped dict, or a route lacks `response_model` — the boundary is unvalidated and the schema undocumented.
- **FA-04** · Blocker · Blocking I/O (`requests`, `time.sleep`, sync DB driver, file reads) inside `async def` — it stalls the event loop for every request.
- **FA-05** · Minor · Errors returned as ad-hoc dicts or status codes instead of `HTTPException` or a registered handler — clients get inconsistent error shapes.
- **FA-06** · Minor · Setting read from `os.environ` in many places instead of one config object — configuration is scattered and untestable.
