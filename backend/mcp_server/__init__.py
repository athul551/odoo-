"""
Brightloop MCP server: the domain exposed as Model Context Protocol tools.

Any MCP-capable agent (Claude Code, Codex CLI, Cursor, Cline, a ChatGPT
connector over HTTP) can list plans, quote, activate, bill, collect and report
against the same services the REST API uses — never raw SQL, never bypassing
role gates or the stage machine.

Two transports, one dispatcher:

    stdio  -- newline-delimited JSON-RPC on stdin/stdout (default)
    http   -- POST /mcp, JSON responses, optional bearer token
"""
