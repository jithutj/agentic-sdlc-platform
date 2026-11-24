import pytest


@pytest.fixture(autouse=True)
def isolated_unit_workflows(request, monkeypatch):
    # Unit/regression tests never depend on or mutate a developer's workflow DB.
    if request.node.get_closest_marker("integration") is None:
        monkeypatch.setenv("WORKFLOW_PERSISTENCE", "memory")
        for name in ("LLM_PROVIDER", "LLM_MAX_INPUT_CHARS", "LLM_MAX_OUTPUT_BYTES",
                     "LLM_MAX_ATTEMPTS", "LLM_TIMEOUT_SECONDS", "LLM_RUN_TIMEOUT_SECONDS",
                     "LLM_RUN_BUDGET_UNITS"):
            monkeypatch.delenv(name, raising=False)
