"""Fail-closed demo PEP/PDP. Not a production credential or approval broker."""
import time
from .models import Action, Approval, Level

READ = frozenset({"read:docs", "read:issues", "read:repo"})
DRAFT = frozenset({"draft:local"})
PROTECTED = frozenset({"write:pr", "write:issue"})
# A3 is intentionally NOT granted: no production or merge capabilities in this starter.

class Denied(Exception):
    pass

def authorize(action: Action, level: Level, *, project_id: str, run_id: str,
              approval: Approval | None = None, audit_available: bool = True) -> None:
    if not audit_available:
        raise Denied("audit_unavailable")
    if action.project_id != project_id or action.run_id != run_id:
        raise Denied("scope_mismatch")
    if action.capability in READ:
        return
    if action.capability in DRAFT and level in {Level.A1, Level.A2, Level.A3}:
        return
    if action.capability in PROTECTED and level in {Level.A2, Level.A3}:
        if not approval:
            raise Denied("approval_required")
        if not all((approval.project_id == action.project_id,
                    approval.run_id == action.run_id,
                    approval.capability == action.capability,
                    approval.resource == action.resource,
                    approval.artifact_digest == action.artifact_digest,
                    bool(approval.approver_id), approval.expires_at > time.time())):
            raise Denied("invalid_approval")
        return
    raise Denied("capability_denied")
