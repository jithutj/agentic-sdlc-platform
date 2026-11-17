from enum import Enum
from pydantic import BaseModel, Field

class Level(str, Enum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"

class Task(BaseModel):
    project_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    level: Level = Level.A0

class Action(BaseModel):
    project_id: str
    run_id: str
    capability: str
    resource: str
    artifact_digest: str | None = None

class Approval(BaseModel):
    project_id: str
    run_id: str
    capability: str
    resource: str
    artifact_digest: str
    approver_id: str
    expires_at: float
