"""Trusted in-process workflow boundary. No HTTP approval, lookup or resume API."""
from contextlib import contextmanager
import hashlib
import json
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Command

from .database import connection_parameters
from .models import Action, AnalysisTask, Task
from .analysis_workflow import ANALYSIS_GRAPH_VERSION, build_analysis_graph
from .llm import GatewayLimits, MemoryBudget, configured_client
from .llm_budget import PostgresBudget
from .policy import authorize
from .requirements import analyze
from .workflow import GRAPH_VERSION, build_graph


class WorkflowConflict(Exception):
    """An existing project/run cannot be overwritten or retrieved through create."""


class WorkflowNotFound(Exception):
    """Opaque identity did not match the requested project and run."""


class ResumeDenied(Exception):
    """No valid, unused approval for this exact pending checkpoint."""


class WorkflowStateError(Exception):
    """Stored identity/state does not match the immutable run registry."""


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def initial_state(task: Task, thread_id: str) -> dict:
    return {"project_id": task.project_id, "run_id": task.run_id,
            "objective": task.objective, "draft": "", "status": "queued",
            "thread_id": thread_id, "graph_version": GRAPH_VERSION, "approval_id": ""}


def public_state(state: dict) -> dict:
    # Keep LangGraph interrupt objects and internal approval metadata out of HTTP.
    result = {key: state[key] for key in
              ("project_id", "run_id", "objective", "draft", "status", "thread_id")}
    if state["graph_version"] == ANALYSIS_GRAPH_VERSION:
        result.update({key: state[key] for key in ("requirements", "llm_usage", "analysis_error")})
    return result


def preview(task: Task) -> dict:
    """Preserve the Python-only demo; this checkpointer dies with the request."""
    thread_id = str(uuid4())
    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke(initial_state(task, thread_id), config)
    return public_state(graph.get_state(config).values)


def analysis_limits(task: AnalysisTask) -> GatewayLimits:
    # Reuse the demo local-draft capability; this does not grant real tool authority.
    authorize(Action(project_id=task.project_id, run_id=task.run_id,
                     capability="draft:local", resource="requirements:local"), task.level,
              project_id=task.project_id, run_id=task.run_id)
    configured_client()  # Reject unsupported configuration before registering a run.
    return GatewayLimits.from_environment()


def initial_analysis_state(task: AnalysisTask, thread_id: str, limits: GatewayLimits) -> dict:
    return dict(initial_state(task, thread_id), graph_version=ANALYSIS_GRAPH_VERSION,
                gateway_limits=limits.model_dump(), requirements=None, analysis_error="",
                llm_usage={"attempts": 0, "reserved_units": 0})


def preview_analysis(task: AnalysisTask) -> dict:
    limits = analysis_limits(task)
    ledger = MemoryBudget()
    client = configured_client()
    graph = build_analysis_graph(InMemorySaver(), lambda state: analyze(state, client, ledger))
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke(initial_analysis_state(task, thread_id, limits), config)
    return public_state(graph.get_state(config).values)


def workflow_parameters() -> dict:
    parameters = connection_parameters(read_only=False)
    parameters["options"] += " -c lock_timeout=3000 -c search_path=workflow,pg_catalog"
    return parameters


@contextmanager
def open_workflows():
    # setup()/DDL belongs only to the separately credentialed migration command.
    with psycopg.connect(**workflow_parameters(), autocommit=True,
                         row_factory=dict_row, prepare_threshold=0) as connection:
        yield PersistentWorkflows(connection)


class PersistentWorkflows:
    def __init__(self, connection):
        self.connection = connection
        serializer = JsonPlusSerializer(allowed_msgpack_modules=[], allowed_json_modules=[])
        saver = PostgresSaver(connection, serde=serializer)
        self.graph = build_graph(saver)
        self.analysis_graph = build_analysis_graph(saver, self._analyze)

    def _analyze(self, state: dict) -> dict:
        return analyze(state, configured_client(), PostgresBudget(self.connection, state["thread_id"]))

    def _graph_for(self, version: str):
        if version == GRAPH_VERSION:
            return self.graph
        if version == ANALYSIS_GRAPH_VERSION:
            return self.analysis_graph
        raise WorkflowStateError

    @contextmanager
    def _locked(self, thread_id: str):
        # Serialize this thread across API workers/processes, including approval use.
        # Hash collisions only serialize unrelated threads; they never select state.
        lock_key = int.from_bytes(hashlib.sha256(thread_id.encode()).digest()[:8],
                                  "big", signed=True)
        self.connection.execute("SELECT pg_advisory_lock(%s)", (lock_key,))
        try:
            yield
        finally:
            self.connection.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))

    def _identity(self, project_id: str, run_id: str, thread_id: str) -> dict:
        try:
            if str(UUID(thread_id)) != thread_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise WorkflowNotFound from None
        row = self.connection.execute(
            "SELECT * FROM workflow.runs WHERE project_id=%s AND run_id=%s AND thread_id=%s",
            (project_id, run_id, thread_id),
        ).fetchone()
        if row is None:
            raise WorkflowNotFound
        self._graph_for(row["graph_version"])
        return row

    def _snapshot(self, identity: dict):
        graph = self._graph_for(identity["graph_version"])
        snapshot = graph.get_state({"configurable": {"thread_id": identity["thread_id"]}})
        state = snapshot.values
        if not state or any(state.get(key) != identity[key] for key in
                            ("project_id", "run_id", "thread_id", "graph_version")):
            raise WorkflowStateError
        if digest(state.get("objective")) != identity["objective_digest"]:
            raise WorkflowStateError
        return snapshot

    def create(self, task: Task) -> dict:
        return self._create(task, GRAPH_VERSION)

    def create_analysis(self, task: AnalysisTask) -> dict:
        limits = analysis_limits(task)
        return self._create(task, ANALYSIS_GRAPH_VERSION, limits)

    def _create(self, task: Task, version: str, limits: GatewayLimits | None = None) -> dict:
        thread_id = str(uuid4())
        try:
            self.connection.execute(
                "INSERT INTO workflow.runs "
                "(thread_id, project_id, run_id, objective_digest, graph_version) "
                "VALUES (%s,%s,%s,%s,%s)",
                (thread_id, task.project_id, task.run_id, digest(task.objective), version),
            )
        except psycopg.errors.UniqueViolation:
            raise WorkflowConflict from None
        with self._locked(thread_id):
            config = {"configurable": {"thread_id": thread_id}}
            state = initial_analysis_state(task, thread_id, limits) if limits is not None else initial_state(task, thread_id)
            self._graph_for(version).invoke(state, config, durability="sync")
            identity = self._identity(task.project_id, task.run_id, thread_id)
            return public_state(self._snapshot(identity).values)

    def intake(self, payload: dict, idempotency_key: str, scope: dict) -> dict:
        """One durable pilot event; retries read state and never resume the graph."""
        from windmill.red5_linear_dispatch import OBJECTIVE, EXECUTION_PLAN, QA_PLAN
        payload_digest = digest({"task": payload, "scope": scope, "planning_artifact": OBJECTIVE})
        project_id, issue_id = payload["project_id"], payload["issue_id"]
        # Lock the event, not a caller-selected key: fresh keys cannot create
        # duplicate pilot runs. Session lock survives the registration commit.
        with self._locked("intake:" + project_id + ":" + issue_id):
            prior = self.connection.execute(
                "SELECT * FROM workflow.intake_events WHERE project_id=%s "
                "AND (issue_id=%s OR idempotency_key=%s)",
                (project_id, issue_id, idempotency_key),
            ).fetchone()
            if prior:
                if prior["payload_digest"] != payload_digest or prior["issue_id"] != issue_id:
                    raise WorkflowConflict
                state = self.read(project_id, prior["run_id"], prior["thread_id"])
            else:
                task = Task(project_id=project_id, run_id=str(uuid4()), objective=OBJECTIVE)
                thread_id = str(uuid4())
                with self.connection.transaction():
                    self.connection.execute(
                        "INSERT INTO workflow.runs "
                        "(thread_id,project_id,run_id,objective_digest,graph_version) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (thread_id, project_id, task.run_id, digest(task.objective), GRAPH_VERSION),
                    )
                    self.connection.execute(
                        "INSERT INTO workflow.intake_events "
                        "(project_id,issue_id,idempotency_key,payload_digest,thread_id,run_id) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (project_id, issue_id, idempotency_key, payload_digest, thread_id, task.run_id),
                    )
                with self._locked(thread_id):
                    self.graph.invoke(initial_state(task, thread_id),
                                      {"configurable": {"thread_id": thread_id}}, durability="sync")
                    state = public_state(self._snapshot(self._identity(
                        project_id, task.run_id, thread_id)).values)
            return {k: state[k] for k in ("project_id", "run_id", "thread_id", "status")} | {
                "approved": False, "codex_executed": False, "git_write_performed": False,
                "execution_plan": EXECUTION_PLAN, "qa_plan": QA_PLAN}

    def read(self, project_id: str, run_id: str, thread_id: str) -> dict:
        """Internal only: IDs plus the server-generated opaque thread handle."""
        identity = self._identity(project_id, run_id, thread_id)
        with self._locked(thread_id):
            return public_state(self._snapshot(identity).values)

    def pending_review(self, project_id: str, run_id: str, thread_id: str) -> dict:
        """Internal review data for a future independently authenticated approval issuer."""
        identity = self._identity(project_id, run_id, thread_id)
        with self._locked(thread_id):
            snapshot = self._snapshot(identity)
            if snapshot.next != ("review",) or not any(t.interrupts for t in snapshot.tasks):
                raise ResumeDenied
            return {"thread_id": thread_id,
                    "checkpoint_id": snapshot.config["configurable"]["checkpoint_id"],
                    "state_digest": digest(snapshot.values)}

    def resume(self, project_id: str, run_id: str, thread_id: str, approval_id: str) -> dict:
        """Internal only. Runtime credentials cannot insert or edit approval records."""
        try:
            if str(UUID(approval_id)) != approval_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ResumeDenied from None
        identity = self._identity(project_id, run_id, thread_id)
        with self._locked(thread_id):
            snapshot = self._snapshot(identity)
            if snapshot.next != ("review",) or not any(t.interrupts for t in snapshot.tasks):
                raise ResumeDenied
            checkpoint_id = snapshot.config["configurable"]["checkpoint_id"]
            # Atomic INSERT reserves the one-use approval before execution. A crash
            # after reservation fails closed: a new approval is required, not replay.
            claimed = self.connection.execute(
                "INSERT INTO workflow.approval_uses (approval_id) "
                "SELECT approval_id FROM workflow.approvals "
                "WHERE approval_id=%s AND thread_id=%s AND checkpoint_id=%s "
                "AND state_digest=%s AND expires_at>clock_timestamp() "
                "ON CONFLICT DO NOTHING RETURNING approval_id",
                (approval_id, thread_id, checkpoint_id, digest(snapshot.values)),
            ).fetchone()
            if claimed is None:
                raise ResumeDenied
            graph = self._graph_for(identity["graph_version"])
            graph.invoke(Command(resume={"approval_id": approval_id}),
                         {"configurable": {"thread_id": thread_id}}, durability="sync")
            return public_state(self._snapshot(identity).values)
