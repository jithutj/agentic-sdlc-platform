"""Local-only starter. API has no authentication; never expose to a network."""
import os
import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .database import database_ready
from .models import Task
from .workflow_store import WorkflowConflict, WorkflowStateError, open_workflows, preview

app = FastAPI(title="Agentic SDLC — Local Read/Draft Starter", version="0.1.0")

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
