"""Additive, idempotent schema setup. Run with separate local migration credentials."""
import sys

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row

from .workflow_store import workflow_parameters


def migrate():
    parameters = workflow_parameters()
    parameters["options"] += " -c statement_timeout=60000"
    with psycopg.connect(**parameters, autocommit=True, row_factory=dict_row,
                         prepare_threshold=0) as connection:
        # DDL/index migrations need autocommit; a session lock serializes setup.
        connection.execute("SELECT pg_advisory_lock(3003001)")
        try:
            connection.execute("CREATE SCHEMA IF NOT EXISTS workflow")
            connection.execute("REVOKE ALL ON SCHEMA workflow FROM PUBLIC")
            PostgresSaver(connection).setup()
            connection.execute("""
                CREATE TABLE IF NOT EXISTS workflow.runs (
                    thread_id text PRIMARY KEY,
                    project_id text NOT NULL,
                    run_id text NOT NULL,
                    objective_digest text NOT NULL,
                    graph_version text NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                    UNIQUE (project_id, run_id)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS workflow.approvals (
                    approval_id text PRIMARY KEY,
                    thread_id text NOT NULL REFERENCES workflow.runs(thread_id),
                    checkpoint_id text NOT NULL,
                    state_digest text NOT NULL,
                    approver_id text NOT NULL CHECK (length(trim(approver_id)) > 0),
                    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                    expires_at timestamptz NOT NULL CHECK (expires_at > created_at)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS workflow.approval_uses (
                    approval_id text PRIMARY KEY REFERENCES workflow.approvals(approval_id),
                    reserved_at timestamptz NOT NULL DEFAULT clock_timestamp()
                )
            """)
            connection.execute("GRANT USAGE ON SCHEMA workflow TO sdlc_app")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS workflow.intake_events (
                    project_id text NOT NULL,
                    issue_id text NOT NULL,
                    idempotency_key text NOT NULL,
                    payload_digest text NOT NULL,
                    thread_id text NOT NULL UNIQUE REFERENCES workflow.runs(thread_id),
                    run_id text NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                    PRIMARY KEY (project_id, issue_id),
                    UNIQUE (project_id, idempotency_key),
                    FOREIGN KEY (project_id, run_id) REFERENCES workflow.runs(project_id, run_id)
                )
            """)
            connection.execute("GRANT SELECT, INSERT ON workflow.intake_events TO sdlc_app")
            connection.execute("GRANT SELECT, INSERT ON workflow.runs, workflow.approval_uses TO sdlc_app")
            connection.execute("GRANT SELECT ON workflow.approvals TO sdlc_app")
            connection.execute("""
                GRANT SELECT, INSERT, UPDATE ON workflow.checkpoints,
                    workflow.checkpoint_blobs, workflow.checkpoint_writes TO sdlc_app
            """)
        finally:
            connection.execute("SELECT pg_advisory_unlock(3003001)")


if __name__ == "__main__":
    try:
        migrate()
    except (ValueError, psycopg.Error):
        print("Workflow migration failed; check local configuration and database permissions.", file=sys.stderr)
        sys.exit(1)
    print("Workflow schema ready.")
