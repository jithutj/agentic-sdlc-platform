"""TEST ONLY: synthetic Linear response, real intake, PostgreSQL and LangGraph.

Used exclusively by compose.integration.yaml. Never start this command with real
credentials or attach this listener to an existing development/production stack.
"""
import uvicorn
import app.intake
from windmill.red5_linear_dispatch import validate_identity

SCOPE = {"workspace_id": "00000000-0000-0000-0000-000000000001",
         "team_id": "00000000-0000-0000-0000-000000000002",
         "issue_uuid": "00000000-0000-0000-0000-000000000003", "linear_project_id": "none"}
DATA = {"data": {"organization": {"id": SCOPE["workspace_id"]}, "issue": {
    "id": SCOPE["issue_uuid"], "identifier": "RED-5",
    "team": {"id": SCOPE["team_id"], "key": "RED"}, "project": None}}}


def simulated_lookup(key, scope):
    if key != "synthetic-linear-key" or scope != SCOPE:
        raise ValueError("Simulation requires synthetic configuration")
    validate_identity(DATA, scope)


if __name__ == "__main__":
    app.intake.lookup = simulated_lookup
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
