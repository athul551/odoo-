"""
Developer-console telemetry: bounded, in-memory records of what the API did.

Two ring buffers — HTTP requests and the SQL those requests executed — so the
Database page can answer "what did that click actually send to Postgres?".
Per-process and volatile by design: this is an operator's window on a running
server, not an audit trail (the durable audit lives in billing runs, invoices
and payments).
"""

from __future__ import annotations

from collections import deque
from threading import Lock
from time import perf_counter

MAX_ENTRIES = 300

_requests: deque = deque(maxlen=MAX_ENTRIES)
_sql: deque = deque(maxlen=MAX_ENTRIES)
_lock = Lock()


def _append(buffer: deque, entry: dict) -> None:
    with _lock:
        buffer.appendleft(entry)


def _short(value, limit: int = 300) -> str:
    text = repr(value)
    return text if len(text) <= limit else f"{text[:limit]}…"


def recent_requests(limit: int = 100) -> list[dict]:
    with _lock:
        return list(_requests)[:limit]


def recent_sql(limit: int = 100) -> list[dict]:
    with _lock:
        return list(_sql)[:limit]


def clear() -> None:
    with _lock:
        _requests.clear()
        _sql.clear()


class ActivityMiddleware:
    """Record every API request and the SQL it ran, without touching DEBUG."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.db import connections

        started = perf_counter()
        statements: list[dict] = []

        def capture(execute, sql, params, many, context):
            began = perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                statements.append(
                    {
                        "sql": " ".join(str(sql).split())[:800],
                        "params": _short(params),
                        "ms": round((perf_counter() - began) * 1000, 2),
                    }
                )

        connection = connections["default"]
        try:
            with connection.execute_wrapper(capture):
                response = self.get_response(request)
        except Exception:
            # A crash is the most interesting request of all: record it, then
            # let Django answer as usual.
            self._record(request, 500, started, statements, error=True)
            raise

        self._record(
            request,
            getattr(response, "status_code", 0),
            started,
            statements,
        )
        return response

    @staticmethod
    def _record(request, status_code, started, statements, error=False) -> None:
        if request.path.startswith("/api/ops/logs"):
            # Reading the log must not flood it, or auto-refresh becomes noise.
            return
        user = getattr(request, "user", None)
        email = None
        if getattr(user, "is_authenticated", False):
            email = getattr(user, "email", None)
        duration = round((perf_counter() - started) * 1000, 2)

        _append(
            _requests,
            {
                "method": request.method,
                "path": request.path,
                "query": request.META.get("QUERY_STRING", ""),
                "status": status_code,
                "ms": duration,
                "user": email,
                "sql_count": len(statements),
                "error": error,
            },
        )
        for statement in statements:
            statement = {**statement, "method": request.method, "path": request.path}
            _append(_sql, statement)
