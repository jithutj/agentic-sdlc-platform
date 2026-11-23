"""Append-only attempt reservations under the workflow service's thread lock."""
from .llm import GatewayFailure, GatewayLimits, GatewayUsage


class PostgresBudget:
    def __init__(self, connection, thread_id: str):
        self.connection = connection
        self.thread_id = thread_id

    def usage(self) -> GatewayUsage:
        row = self.connection.execute(
            "SELECT count(*) AS attempts, coalesce(sum(reserved_units),0) AS reserved_units "
            "FROM workflow.llm_attempts WHERE thread_id=%s", (self.thread_id,),
        ).fetchone()
        return GatewayUsage(attempts=row["attempts"], reserved_units=row["reserved_units"])

    def reserve(self, units: int, limits: GatewayLimits) -> None:
        row = self.connection.execute(
            "INSERT INTO workflow.llm_attempts (thread_id, attempt_no, reserved_units) "
            "SELECT %s, count(*)+1, %s FROM workflow.llm_attempts WHERE thread_id=%s "
            "HAVING count(*)<%s AND coalesce(sum(reserved_units),0)+%s<=%s "
            "RETURNING attempt_no",
            (self.thread_id, units, self.thread_id, limits.max_attempts, units, limits.budget_units),
        ).fetchone()
        if row is None:
            code = "retry_exhausted" if self.usage().attempts >= limits.max_attempts else "budget_exceeded"
            raise GatewayFailure(code)
