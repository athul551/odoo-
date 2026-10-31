"""
Minimal HTTP transport for the MCP server (streamable-HTTP shaped).

POST /mcp     -> JSON-RPC in, JSON (or 202 for notifications) out
GET  /mcp     -> 405: this server never opens a server-initiated SSE stream
DELETE /mcp   -> 204: sessions are stateless, so ending one is a no-op

It is deliberately dependency-free (stdlib http.server), and it is meant to be
bound to localhost or put behind a reverse proxy with TLS. If a token is
configured, every request must carry ``Authorization: Bearer <token>``.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY_BYTES = 1_000_000
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


class McpRequestHandler(BaseHTTPRequestHandler):
    server_version = "BrightloopMCP/1.0"
    protocol_version = "HTTP/1.1"

    # -- helpers --------------------------------------------------------
    def _json(self, status: int, payload) -> None:
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        if payload is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Mcp-Session-Id", getattr(self.server, "session_id", "brightloop"))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _authorised(self) -> bool:
        """
        Fail closed. A server bound beyond loopback without a token would let
        any network peer act as the configured --actor (possibly an admin),
        so that combination is refused at construction and again here.
        """
        token = getattr(self.server, "token", None)
        if token:
            return self.headers.get("Authorization", "") == f"Bearer {token}"
        host = getattr(self.server, "bind_host", "127.0.0.1")
        return host in LOOPBACK_HOSTS

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return b""
        if length > MAX_BODY_BYTES:
            return b""
        return self.rfile.read(length)

    # -- verbs ----------------------------------------------------------
    def do_POST(self):  # noqa: N802
        if self.path.split("?")[0].rstrip("/") not in ("/mcp", ""):
            self._json(404, {"errors": {"detail": ["Use POST /mcp."]}})
            return
        if not self._authorised():
            self._json(401, {"errors": {"detail": ["Invalid or missing bearer token."]}})
            return
        raw = self._read_body()
        if not raw:
            self._json(400, {"errors": {"detail": ["Empty request body."]}})
            return
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            self._json(400, {"errors": {"detail": ["Body must be UTF-8 JSON."]}})
            return
        response = self.server.mcp.handle_line(text)
        if response is None:
            self._json(202, None)
        else:
            self._json(200, response)

    def do_GET(self):  # noqa: N802
        self.send_response(405)
        self.send_header("Allow", "POST, DELETE")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_DELETE(self):  # noqa: N802
        self._json(204, None)

    def log_message(self, fmt, *args):  # keep stdout for the protocol
        import sys

        sys.stderr.write(f"[brightloop-mcp] {self.address_string()} {fmt % args}\n")


def build_http_server(*, mcp, host: str = "127.0.0.1", port: int = 8765,
                      token: str | None = None) -> ThreadingHTTPServer:
    """
    Build the HTTP transport.

    Refuses to expose itself beyond loopback without a bearer token: an
    unauthenticated 0.0.0.0 bind would let any network peer act as the
    configured actor, including running billing.
    """
    if not token and host not in LOOPBACK_HOSTS:
        raise ValueError(
            f"refusing to bind HTTP transport to {host!r} without a token. "
            "Pass --token (or BRIGHTLOOP_MCP_TOKEN); open binds must "
            "authenticate, or keep the default 127.0.0.1 for local agents."
        )
    httpd = ThreadingHTTPServer((host, port), McpRequestHandler)
    httpd.mcp = mcp
    httpd.token = token
    httpd.bind_host = host
    httpd.session_id = "brightloop"
    return httpd
