"""Mocked Linear and handoff transport; no real external integration evidence."""
import copy
from unittest.mock import Mock
import pytest

from windmill import red5_linear_dispatch as dispatch

SCOPE = {"workspace_id": "workspace", "team_id": "team", "issue_uuid": "issue", "linear_project_id": "none"}
DATA = {"data": {"organization": {"id": "workspace"}, "issue": {
    "id": "issue", "identifier": "RED-5", "team": {"id": "team", "key": "RED"}, "project": None}}}


@pytest.mark.parametrize("path,value", [
    (("organization", "id"), "QMO"), (("issue", "id"), "wrong"),
    (("issue", "identifier"), "QMO-5"), (("issue", "team", "id"), "wrong"),
    (("issue", "team", "key"), "QMO"), (("issue", "project"), {"id": "other"}),
])
def test_identity_mismatch_denied(path, value):
    data = copy.deepcopy(DATA)
    node = data["data"]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(dispatch.ScopeDenied):
        dispatch.validate_identity(data, SCOPE)


@pytest.mark.parametrize("data", [{}, {"errors": [{"message": "synthetic"}]}, {"data": {"issue": None}}])
def test_missing_identity_fails_closed(data):
    with pytest.raises(dispatch.ScopeDenied):
        dispatch.validate_identity(data, SCOPE)


def test_read_then_fixed_private_handoff(monkeypatch):
    response = {"run_id": "run", "thread_id": "thread", "status": "awaiting_human_review",
                "codex_executed": False, "git_write_performed": False}
    post = Mock(side_effect=[DATA, response])
    monkeypatch.setattr(dispatch, "post_json", post)
    assert dispatch.dispatch("synthetic-token", "synthetic-key", SCOPE) == response
    assert post.call_args_list[0].args[0] == dispatch.LINEAR_URL
    assert post.call_args_list[1].args[0] == "http://intake:8000/v1/intake"
    assert post.call_args_list[1].args[1] == dispatch.contract()
    assert "description" not in dispatch.QUERY
    assert "mutation" not in dispatch.QUERY


def test_wrong_issue_rejected_before_secret_or_network_access():
    with pytest.raises(dispatch.ScopeDenied):
        dispatch.main("QMO-5")


def test_redirects_are_not_followed():
    assert dispatch.NoRedirect().redirect_request(None, None, None, None, None, None) is None
