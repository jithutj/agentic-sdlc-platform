"""Local draft compatibility plus a restricted, authenticated integration listener."""
import os
import psycopg
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from .intake import router
from .database import database_ready
from .models import AnalysisTask, Task
from .llm import GatewayFailure
from .policy import Denied
from .analysis_http import AnalysisBodyLimit
from .workflow_store import (WorkflowConflict, WorkflowStateError, open_workflows,
                             preview, preview_analysis)

app = FastAPI(title="Agentic SDLC — Local Read/Draft Starter", version="0.1.0")
app.include_router(router)
app.add_middleware(AnalysisBodyLimit)


@app.middleware("http")
async def listener_boundary(request, call_next):
    # The same application serves two listeners. Windmill cannot reach the
    # localhost compatibility service or invoke its unauthenticated routes.
    if (os.environ.get("LOCAL_DEMO_ROUTES", "true") != "true"
            and request.url.path not in ("/health", "/db-health", "/v1/intake")):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    if request.url.path == "/v1/intake":
        from .intake import authenticate
        from fastapi import HTTPException
        try:
            authenticate(request.headers.get("x-pilot-token"))
        except HTTPException:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        # Bound streamed input before Pydantic or JSON parsing.
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 8192:
                return JSONResponse(status_code=413, content={"detail": "Intake too large"})
            body.extend(chunk)
        request._body = bytes(body)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def safe_validation(request, error):
    if request.url.path == "/v1/intake":
        return JSONResponse(status_code=422, content={"detail": "Invalid intake task"})
    if request.url.path == "/analysis":
        return JSONResponse(status_code=422, content={"status": "invalid_analysis_request"})
    return await request_validation_exception_handler(request, error)

@app.get("/health")
def health():
    return {"status": "ok", "mode": "local_demo", "external_writes": False}

@app.get("/db-health")
def db_health():
    if database_ready():
        return {"status": "ok"}
    return JSONResponse(status_code=503, content={"status": "unavailable"})

@app.post("/draft")
def create_draft(task: Task):
    # Do not accept external tool requests or execute code.
    mode = os.environ.get("WORKFLOW_PERSISTENCE", "memory")
    try:
        if mode == "memory":
            return preview(task)
        if mode != "postgres":
            raise ValueError("Invalid workflow configuration")
        with open_workflows() as workflows:
            return workflows.create(task)
    except WorkflowConflict:
        return JSONResponse(status_code=409, content={"status": "run_already_exists"})
    except (ValueError, psycopg.Error, WorkflowStateError):
        return JSONResponse(status_code=503, content={"status": "workflow_unavailable"})

@app.post("/analysis")
def create_analysis(task: AnalysisTask):
    try:
        mode = os.environ.get("WORKFLOW_PERSISTENCE", "memory")
        if mode == "memory":
            result = preview_analysis(task)
        elif mode == "postgres":
            with open_workflows() as workflows:
                result = workflows.create_analysis(task)
        else:
            raise ValueError("Invalid workflow configuration")
        if result["status"] == "analysis_failed":
            status = {"budget_exceeded": 429, "input_limit_exceeded": 422,
                      "provider_timeout": 504, "execution_timeout": 504,
                      "invalid_configuration": 503}.get(result["analysis_error"], 502)
            return JSONResponse(status_code=status, content=result)
        return result
    except WorkflowConflict:
        return JSONResponse(status_code=409, content={"status": "run_already_exists"})
    except Denied:
        return JSONResponse(status_code=403, content={"status": "analysis_denied"})
    except (GatewayFailure, ValueError, psycopg.Error, WorkflowStateError):
        return JSONResponse(status_code=503, content={"status": "analysis_unavailable"})
