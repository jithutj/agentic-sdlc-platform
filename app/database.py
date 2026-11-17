"""Environment configuration and a read-only connectivity probe."""
import os

import psycopg


def connection_parameters(*, read_only: bool = True) -> dict:
    """Use separate parameters so passwords never need URL escaping."""
    required = {key: os.environ.get(env, "") for key, env in (
        ("host", "DB_HOST"), ("dbname", "DB_NAME"),
        ("user", "DB_USER"), ("password", "DB_PASSWORD"),
    )}
    if not all(required.values()):
        raise ValueError("Database configuration is incomplete")
    # A single host avoids multiplying libpq's per-host connection timeout.
    if "," in required["host"] or any(c.isspace() for c in required["host"]):
        raise ValueError("Configure a single database host")
    timeout = int(os.environ.get("DB_CONNECT_TIMEOUT", "3"))
    port = int(os.environ.get("DB_PORT", "5432"))
    if not 2 <= timeout <= 10 or not 1 <= port <= 65535:
        raise ValueError("Database connection bounds are invalid")
    mode = "on" if read_only else "off"
    return dict(required, port=port, connect_timeout=timeout,
                options=f"-c statement_timeout=3000 -c default_transaction_read_only={mode}")


def database_ready() -> bool:
    try:
        with psycopg.connect(**connection_parameters()) as connection:
            row = connection.execute(
                "SELECT 1, extversion FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()
            return row is not None and row[0] == 1 and bool(row[1])
    except (ValueError, psycopg.Error):
        # Driver/configuration errors may contain credentials or connection details.
        return False
