"""
Entry point: ``python -m mcp_server`` from the backend directory.

    # stdio, acting as the first admin
    python -m mcp_server

    # act as a named operator, read-only
    python -m mcp_server --actor ops@brightloop.io --read-only

    # HTTP for remote agents / connectors
    python -m mcp_server --transport http --port 8765 --token s3cret

The actor's domain role is the ceiling of what the agent can do: a STAFF actor
cannot create discount rules or users, exactly like the REST API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="brightloop-mcp",
        description="Model Context Protocol server for the Brightloop API.",
    )
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument(
        "--actor", default=os.environ.get("BRIGHTLOOP_MCP_ACTOR"),
        help="Email of the staff/admin user the tools act as "
             "(default: BRIGHTLOOP_MCP_ACTOR, else the first active admin).",
    )
    parser.add_argument(
        "--read-only", action="store_true",
        default=os.environ.get("BRIGHTLOOP_MCP_READ_ONLY", "").lower()
        in ("1", "true", "yes"),
        help="Expose write tools but refuse to execute them.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--token", default=os.environ.get("BRIGHTLOOP_MCP_TOKEN"),
        help="Require Authorization: Bearer <token> on HTTP requests.",
    )
    parser.add_argument(
        "--settings", default=os.environ.get(
            "DJANGO_SETTINGS_MODULE", "config.settings.development"
        ),
    )
    parser.add_argument(
        "--print-tools", action="store_true",
        help="Print the tool catalogue as JSON and exit (discovery/debug).",
    )
    return parser.parse_args(argv)


def bootstrap_django(settings_module: str) -> None:
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)
    import django

    django.setup()


def resolve_actor(email: str | None):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    queryset = User.objects.select_related("customer").filter(is_active=True)
    if email:
        user = queryset.filter(email__iexact=email.strip()).first()
        if user is None:
            raise SystemExit(f"[brightloop-mcp] no active user with email {email!r}")
    else:
        user = queryset.filter(role=User.Role.ADMIN).order_by("pk").first()
        if user is None:
            user = queryset.filter(is_superuser=True).order_by("pk").first()
        if user is None:
            raise SystemExit(
                "[brightloop-mcp] no admin user found. Create one with "
                "`manage.py createsuperuser`, or pass --actor you@example.com"
            )
    if not user.is_member_of_staff:
        raise SystemExit(
            f"[brightloop-mcp] {user.email} is a {user.role}; MCP operators must be "
            "staff or admin (the portal is not an automation surface)."
        )
    return user


def serve_stdio(server) -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        response = server.handle_line(line)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


def main(argv=None) -> int:
    args = parse_args(argv)
    bootstrap_django(args.settings)

    from mcp_server.http_transport import build_http_server
    from mcp_server.protocol import McpServer, ServerContext
    from mcp_server.tools import build_tools

    if args.print_tools:
        tools = build_tools()
        json.dump(
            [{"name": t.name, "description": t.description,
              "inputSchema": t.input_schema, "write": t.write}
             for t in sorted(tools.values(), key=lambda x: x.name)],
            sys.stdout, indent=2,
        )
        sys.stdout.write("\n")
        return 0

    actor = resolve_actor(args.actor)
    context = ServerContext(actor=actor, read_only=args.read_only)
    server = McpServer(context=context, tools=build_tools())

    if args.transport == "http":
        httpd = build_http_server(
            mcp=server, host=args.host, port=args.port, token=args.token
        )
        sys.stderr.write(
            f"[brightloop-mcp] acting as {actor.email} ({actor.role}); "
            f"HTTP on http://{args.host}:{args.port}/mcp"
            f"{' (token required)' if args.token else ''}"
            f"{' [read-only]' if args.read_only else ''}\n"
        )
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()
        return 0

    sys.stderr.write(
        f"[brightloop-mcp] acting as {actor.email} ({actor.role}); stdio ready"
        f"{' [read-only]' if args.read_only else ''}\n"
    )
    serve_stdio(server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
