"""Fail-closed service identity and durable A1 intake. No approval authority."""
import hmac
import os
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
import psycopg

from windmill.red5_linear_dispatch import (ISSUE, PROJECT, REPOSITORY, lookup,
                                          IntegrationUnavailable, ScopeDenied)
from .workflow_store import WorkflowConflict, WorkflowStateError, open_workflows

router = APIRouter()


def authenticate(x_pilot_token: str | None = Header(default=None)):
    expected = os.environ.get("PILOT_INTAKE_TOKEN", "")
    if (len(expected) < 32 or not x_pilot_token
            or not hmac.compare_digest(x_pilot_token.encode(), expected.encode())):
        raise HTTPException(401, "Unauthorized")


class IntakeTask(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    project_id: str = Field(min_length=1, max_length=128)
    issue_id: str = Field(min_length=1, max_length=64)
    repository: str = Field(min_length=1, max_length=128)
    objective: str = Field(min_length=10, max_length=1000, repr=False)
    authorization: Literal["A1"] = "A1"
    operation: Literal["draft"] = "draft"

    @field_validator("objective")
    @classmethod
    def safe_text(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid objective")
        value.encode("utf-8")
        return value


def trusted_scope():
    try:
        scope = {key: str(UUID(os.environ[env])) for key, env in (
            ("workspace_id", "PILOT_LINEAR_WORKSPACE_ID"),
            ("team_id", "PILOT_LINEAR_TEAM_ID"),
            ("issue_uuid", "PILOT_LINEAR_ISSUE_UUID"))}
        project = os.environ["PILOT_LINEAR_PROJECT_ID"]
        scope["linear_project_id"] = "none" if project == "none" else str(UUID(project))
        return scope
    except (KeyError, ValueError):
        raise IntegrationUnavailable from None


@router.post("/v1/intake", dependencies=[Depends(authenticate)])
def intake(task: IntakeTask, idempotency_key: str | None = Header(default=None)):
    if not idempotency_key or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", idempotency_key):
        raise HTTPException(400, "Invalid idempotency key")
    if (task.project_id, task.issue_id, task.repository) != (PROJECT, ISSUE, REPOSITORY):
        raise HTTPException(403, "Pilot scope denied")
    try:
        if os.environ.get("WORKFLOW_PERSISTENCE") != "postgres":
            raise IntegrationUnavailable
        # Caller assertions and Windmill's successful lookup are insufficient.
        scope = trusted_scope()
        lookup(os.environ.get("LINEAR_READ_API_KEY", ""), scope)
        with open_workflows() as workflows:
            return workflows.intake(task.model_dump(), idempotency_key, scope)
    except ScopeDenied:
        raise HTTPException(403, "Pilot scope denied") from None
    except WorkflowConflict:
        raise HTTPException(409, "Conflicting or incomplete intake") from None
    except (IntegrationUnavailable, ValueError, psycopg.Error, WorkflowStateError):
        raise HTTPException(503, "Intake unavailable") from None
