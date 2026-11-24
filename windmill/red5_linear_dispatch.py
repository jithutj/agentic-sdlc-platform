#requirements:
#wmill==1.875.0
"""Manual A1 dispatch. Standard-library HTTP and Windmill SDK secret retrieval.

Import this file as a Windmill Python script. Configure f/platform/* variables
as described in docs/projects/redeeming-light/pilot.md. Never pass secrets in
job arguments. FastAPI independently repeats the Linear identity checks.
"""
import hashlib
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

LINEAR_URL = "https://api.linear.app/graphql"
API_URL = "http://intake:8000/v1/intake"
PROJECT = "redeeming-light"
ISSUE = "RED-5"
REPOSITORY = "jithutj/redeeminglight"
EXECUTION_PLAN = ["Draft the Astro frontend foundation scope and file outline.",
                  "Keep Codex execution and repository changes disabled pending an isolated runner review."]
QA_PLAN = ["Review proposed scope and acceptance checks before separately authorized execution.",
           "Require independent artifact review before any publication."]
# The existing graph checkpoints this complete deterministic planning artifact.
OBJECTIVE = ("Prepare Astro frontend foundation as a restricted A1 planning draft. "
             "Plan: " + " ".join(EXECUTION_PLAN) + " QA: " + " ".join(QA_PLAN))
QUERY = """query PilotIdentity($id: String!) {
  organization { id }
  issue(id: $id) { id identifier team { id key } project { id } }
}"""


class IntegrationUnavailable(Exception):
    """Redacted transport/configuration failure."""


class ScopeDenied(Exception):
    """Trusted identity did not match the configured pilot."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def post_json(url: str, payload: dict, headers: dict) -> dict:
    # Do not inherit proxy settings or follow redirects carrying credentials.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(url, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with opener.open(request, timeout=15) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise IntegrationUnavailable("Integration request unavailable") from None


def validate_identity(data: dict, scope: dict) -> None:
    try:
        issue = data["data"]["issue"]
        if (data.get("errors") or data["data"]["organization"]["id"] != scope["workspace_id"]
                or issue["id"] != scope["issue_uuid"] or issue["identifier"] != ISSUE
                or issue["team"]["id"] != scope["team_id"] or issue["team"]["key"] != "RED"
                or (issue["project"]["id"] if issue["project"] else "none") != scope["linear_project_id"]):
            raise ScopeDenied
    except (KeyError, TypeError):
        raise ScopeDenied from None


def lookup(linear_key: str, scope: dict) -> None:
    if not linear_key or not all(scope.get(k) for k in
            ("workspace_id", "issue_uuid", "team_id", "linear_project_id")):
        raise IntegrationUnavailable("Pilot configuration incomplete")
    data = post_json(LINEAR_URL, {"query": QUERY, "variables": {"id": ISSUE}},
                     {"Authorization": linear_key})
    validate_identity(data, scope)


def contract() -> dict:
    return {"project_id": PROJECT, "issue_id": ISSUE, "repository": REPOSITORY,
            "objective": OBJECTIVE, "operation": "draft", "authorization": "A1"}


def dispatch(pilot_token: str, linear_key: str, scope: dict) -> dict:
    lookup(linear_key, scope)
    key = hashlib.sha256(b"redeeming-light:RED-5:A1-plan:RED-6-v1").hexdigest()
    result = post_json(API_URL, contract(),
                       {"X-Pilot-Token": pilot_token, "Idempotency-Key": key})
    # Job results contain identifiers and safe flags only; never raw Linear data.
    return {k: result[k] for k in ("run_id", "thread_id", "status", "codex_executed",
                                  "git_write_performed")}


def main(issue_id: str = "RED-5") -> dict:
    if issue_id != ISSUE:
        raise ScopeDenied("Pilot issue denied")
    import wmill
    get = lambda name: wmill.get_variable("f/platform/" + name)
    scope = {k: get(k) for k in ("workspace_id", "issue_uuid", "team_id", "linear_project_id")}
    return dispatch(get("pilot_token"), get("linear_read_key"), scope)
