import time
import pytest
from app.models import Action, Approval, Level
from app.policy import authorize, Denied

A = Action(project_id="demo", run_id="r1", capability="read:docs", resource="doc:1")

def test_read_allowed():
    authorize(A, Level.A0, project_id="demo", run_id="r1")

def test_cross_project_denied():
    with pytest.raises(Denied):
        authorize(A, Level.A0, project_id="other", run_id="r1")

def test_a0_cannot_write():
    with pytest.raises(Denied):
        authorize(A.model_copy(update={"capability":"write:pr"}), Level.A0, project_id="demo", run_id="r1")

def test_approval_exact_match():
    a = A.model_copy(update={"capability":"write:pr", "artifact_digest":"sha256:abc"})
    p = Approval(project_id="demo", run_id="r1", capability="write:pr", resource="doc:1",
                 artifact_digest="sha256:abc", approver_id="human", expires_at=time.time()+60)
    authorize(a, Level.A2, project_id="demo", run_id="r1", approval=p)
    with pytest.raises(Denied):
        authorize(a.model_copy(update={"artifact_digest":"sha256:changed"}), Level.A2,
                  project_id="demo", run_id="r1", approval=p)

def test_expired_approval_denied():
    a = A.model_copy(update={"capability":"write:pr", "artifact_digest":"sha256:abc"})
    p = Approval(project_id="demo", run_id="r1", capability="write:pr", resource="doc:1",
                 artifact_digest="sha256:abc", approver_id="human", expires_at=time.time()-60)
    with pytest.raises(Denied):
        authorize(a, Level.A2, project_id="demo", run_id="r1", approval=p)

def test_fail_closed_without_audit():
    with pytest.raises(Denied):
        authorize(A, Level.A0, project_id="demo", run_id="r1", audit_available=False)

def test_no_production_capabilities():
    with pytest.raises(Denied):
        authorize(A.model_copy(update={"capability":"deploy:production"}), Level.A3,
                  project_id="demo", run_id="r1")
