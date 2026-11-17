import pytest


@pytest.fixture(autouse=True)
def isolated_unit_workflows(request, monkeypatch):
    # Unit/regression tests never depend on or mutate a developer's workflow DB.
    if request.node.get_closest_marker("integration") is None:
        monkeypatch.setenv("WORKFLOW_PERSISTENCE", "memory")
