"""Local-only starter. API has no authentication; never expose to a network."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .database import database_ready
from .models import Task
from .workflow import graph

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
    return graph.invoke({"project_id": task.project_id, "run_id": task.run_id,
                         "objective": task.objective, "draft": "", "status": "queued"})
