"""Local-only starter. API has no authentication; never expose to a network."""
from fastapi import FastAPI
from .models import Task
from .workflow import graph

app = FastAPI(title="Agentic SDLC — Local Read/Draft Starter", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok", "mode": "local_demo", "external_writes": False}

@app.post("/draft")
def create_draft(task: Task):
    # Do not accept external tool requests or execute code.
    return graph.invoke({"project_id": task.project_id, "run_id": task.run_id,
                         "objective": task.objective, "draft": "", "status": "queued"})
