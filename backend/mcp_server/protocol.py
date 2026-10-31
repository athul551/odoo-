"""
JSON-RPC 2.0 + MCP method dispatch, independent of transport.

Keeping this layer transport-agnostic is what lets the same server speak stdio
to a local agent and HTTP to a remote one, and lets the tests drive it without
opening a socket.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from django.core.exceptions import PermissionDenied, ValidationError

from apps.subscriptions.models import InvalidTransition

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict, "ServerContext"], Any]
    write: bool = False


@dataclass
class ServerContext:
    actor: Any  # accounts.User, always staff/admin
    read_only: bool = False


class McpError(Exception):
    """A JSON-RPC level error (bad request shape), not a tool failure."""

    def __init__(self, code: int, message: str, data=None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


def _error(request_id, code: int, message: str, data=None) -> dict:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _tool_error_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        if hasattr(exc, "message_dict"):
            return json.dumps({"errors": exc.message_dict}, default=str)
        return json.dumps({"errors": {"non_field_errors": exc.messages}}, default=str)
    if isinstance(exc, InvalidTransition):
        return json.dumps(
            {"errors": {"stage": [exc.reason]}, "code": "invalid_transition"}
        )
    if isinstance(exc, PermissionDenied):
        return json.dumps({"errors": {"detail": [str(exc)]}}, default=str)
    return json.dumps({"errors": {"detail": [str(exc)]}}, default=str)


class McpServer:
    """MCB dispatcher: initialize -> tools/list -> tools/call, plus ping."""

    def __init__(self, context: ServerContext, tools: dict[str, Tool],
                 *, name: str = "brightloop", version: str = "1.0.0"):
        self.context = context
        self.tools = tools
        self.name = name
        self.version = version

    # -- MCP methods ----------------------------------------------------
    def _initialize(self, params: dict) -> dict:
        requested = (params or {}).get("protocolVersion")
        negotiated = (
            requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        )
        return {
            "protocolVersion": negotiated,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": self.name,
                "title": "Brightloop Subscription Management",
                "version": self.version,
            },
            "instructions": (
                "Brightloop subscription management. Read tools are safe; write "
                "tools mutate real invoices and payments. call subscription_transition "
                "in order (send_quotation -> confirm -> activate), and run_billing_day "
                "with confirm=false first to preview."
            ),
        }

    def _tools_list(self) -> dict:
        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                    "annotations": {
                        "readOnlyHint": not tool.write,
                        "destructiveHint": tool.write,
                    },
                }
                for tool in sorted(self.tools.values(), key=lambda t: t.name)
            ]
        }

    def _tools_call(self, params: dict) -> dict:
        name = (params or {}).get("name")
        arguments = (params or {}).get("arguments") or {}
        if not isinstance(arguments, dict):
            raise McpError(INVALID_PARAMS, "arguments must be an object")
        tool = self.tools.get(name)
        if tool is None:
            raise McpError(INVALID_PARAMS, f"Unknown tool: {name!r}")
        if tool.write and self.context.read_only:
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps({"errors": {"detail": [
                        "This server is running read-only; write tools are disabled."
                    ]}}),
                }],
                "isError": True,
            }
        try:
            payload = tool.handler(arguments, self.context)
        except (ValidationError, PermissionDenied, InvalidTransition) as exc:
            return {
                "content": [{"type": "text", "text": _tool_error_text(exc)}],
                "isError": True,
            }
        except Exception as exc:  # tool blew up: report, never kill the session
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps({"errors": {"detail": [
                        f"{type(exc).__name__}: {exc}"
                    ]}}),
                }],
                "isError": True,
            }
        return {
            "content": [{
                "type": "text",
                "text": json.dumps(payload, default=str, indent=2),
            }],
            "isError": False,
        }

    # -- JSON-RPC -------------------------------------------------------
    def handle_message(self, message: Any) -> dict | None:
        if not isinstance(message, dict):
            raise McpError(INVALID_REQUEST, "Each message must be a JSON object")
        method = message.get("method")
        request_id = message.get("id")
        if not method or not isinstance(method, str):
            raise McpError(INVALID_REQUEST, "Missing method")
        is_notification = "id" not in message
        params = message.get("params") or {}

        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = self._tools_list()
            elif method == "tools/call":
                result = self._tools_call(params)
            elif method in ("notifications/initialized", "notifications/cancelled"):
                return None
            else:
                raise McpError(METHOD_NOT_FOUND, f"Method not found: {method}")
        except McpError as exc:
            if is_notification:
                return None
            return _error(request_id, exc.code, exc.message, exc.data)
        except Exception as exc:  # defensive: never leak a stack trace to the wire
            if is_notification:
                return None
            return _error(request_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")

        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def handle_line(self, line: str) -> Any:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            return _error(None, PARSE_ERROR, "Parse error", str(exc))
        if isinstance(payload, list):
            if not payload:
                return _error(None, INVALID_REQUEST, "Empty batch")
            responses = []
            for item in payload:
                try:
                    response = self.handle_message(item)
                except McpError as exc:
                    response = _error(None, exc.code, exc.message, exc.data)
                if response is not None:
                    responses.append(response)
            return responses or None
        try:
            return self.handle_message(payload)
        except McpError as exc:
            return _error(payload.get("id") if isinstance(payload, dict) else None,
                          exc.code, exc.message, exc.data)
