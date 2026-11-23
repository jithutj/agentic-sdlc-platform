from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_validator

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

class AnalysisTask(Task):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    project_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    objective: str = Field(min_length=1, max_length=4000, repr=False)
    level: Level = Level.A1

    @field_validator("project_id", "run_id", "objective")
    @classmethod
    def valid_analysis_text(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Nonblank PostgreSQL-compatible text required")
        try:
            value.encode("utf-8")
        except UnicodeError:
            raise ValueError("Valid UTF-8 text required") from None
        return value

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
