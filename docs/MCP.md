# Brightloop MCP server

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes the Brightloop domain as tools, so any MCP-capable agent — Claude Code, Codex CLI, Cursor, Cline, a custom client, or a remote HTTP connector — can quote, activate, bill, collect and report without writing SQL.

It is **not** a second implementation. Every tool calls the same service layer as the REST API (`subscriptions.services`, `billing.services`, `payments.services`, `reporting.services`), so stage rules, role gates, idempotent billing and ledger maths behave identically whichever door is used.

## Run it

From `backend/`:

```bash
# stdio (local agents), acting as the first active admin
.venv/bin/python -m mcp_server

# act as a named operator, read-only (safe exploration)
.venv/bin/python -m mcp_server --actor ops@brightloop.io --read-only

# HTTP for remote agents / connectors
.venv/bin/python -m mcp_server --transport http --host 127.0.0.1 --port 8765 --token s3cret

# discovery / debugging: dump the tool catalogue
.venv/bin/python -m mcp_server --print-tools
```

`backend/bin/brightloop-mcp` is a launcher that `cd`s into `backend/` first, so clients that do not support a working directory can use one absolute path.

| Flag | Env fallback | Default |
|---|---|---|
| `--actor EMAIL` | `BRIGHTLOOP_MCP_ACTOR` | first active admin |
| `--read-only` | `BRIGHTLOOP_MCP_READ_ONLY=1` | off |
| `--transport stdio\|http` | – | `stdio` |
| `--host`, `--port` | – | `127.0.0.1`, `8765` |
| `--token` | `BRIGHTLOOP_MCP_TOKEN` | none |
| `--settings` | `DJANGO_SETTINGS_MODULE` | `config.settings.development` |

The process reads the same `DATABASE_URL` / `.env` as Django, so no extra configuration is needed.

## Connecting agents

### Claude Code / Cursor / Cline (project `.mcp.json`)

```json
{
  "mcpServers": {
    "brightloop": {
      "command": "/absolute/path/to/backend/bin/brightloop-mcp",
      "args": ["--actor", "ops@brightloop.io"]
    }
  }
}
```

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.brightloop]
command = "/absolute/path/to/backend/bin/brightloop-mcp"
args = ["--actor", "ops@brightloop.io"]
```

### Windows / no bash

```json
{
  "mcpServers": {
    "brightloop": {
      "command": "C:\\path\\backend\\.venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_server", "--actor", "ops@brightloop.io"],
      "cwd": "C:\\path\\backend"
    }
  }
}
```

### Remote / HTTP clients

```bash
# one-shot JSON-RPC over HTTP
curl -s localhost:8765/mcp \
  -H 'Authorization: Bearer s3cret' -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

The endpoint speaks JSON-RPC 2.0 over `POST /mcp`, answers `202` for notifications, and keeps no session state. Put it behind TLS (reverse proxy) if it leaves localhost, and always set `--token` when it does.

## Security model

- The **actor's role is the ceiling**. A `STAFF` actor cannot create discount rules or users; `whoami` reports exactly what the agent may do.
- MCP refuses to start as a customer-role user: the portal is not an automation surface.
- `--read-only` keeps the catalogue visible but refuses every write tool with an `isError` result.
- `run_billing_day` requires `confirm: true`; without it the caller gets the preview, so an agent cannot bill by accident.
- HTTP mode optionally requires `Authorization: Bearer <token>`; the server binds `127.0.0.1` unless told otherwise.
- Tool failures are returned as `isError: true` content, never as a crashed session, and never as a stack trace to the client.

## Tools

Read tools (`readOnlyHint: true`) are safe to call at any time.

| Tool | Write | What it does |
|---|---|---|
| `whoami` | – | actor email/role, read-only flag, capabilities |
| `list_customers` | – | search organizations |
| `get_customer` | – | one organization |
| `list_products` | – | catalog with variants and effective prices |
| `list_plans` | – | plans; `selectable_only` respects the availability window |
| `list_tax_rules` | – | tax percentages |
| `list_subscriptions` | – | filter by customer, stage, text |
| `get_subscription` | – | lines, totals, stage |
| `create_subscription` | ✔ | Draft subscription + lines; returns `SUB-…` |
| `add_subscription_line` | ✔ | respects plan minimum and one-line-per-product |
| `remove_subscription_line` | ✔ | recomputes totals |
| `subscription_transition` | ✔ | `send_quotation` → `confirm` → `activate`, plus `close`, `renew`, `pause`, `resume` |
| `preview_billing_day` | – | what would be billed on a date |
| `run_billing_day` | ✔ | idempotent batch; needs `confirm: true` |
| `list_invoices` | – | filter by customer, status, subscription, `overdue` |
| `get_invoice` | – | lines, payments, applied discounts |
| `invoice_action` | ✔ | `confirm`, `send`, `print`, `cancel` |
| `record_payment` | ✔ | refuses overpayment; Paid derives from the ledger |
| `remove_payment` | ✔ | correct a mis-recorded receipt |
| `list_discount_rules` | – | with usage counts |
| `create_discount_rule` | ✔ | admin only |
| `deactivate_discount_rule` | ✔ | admin only; never revokes issued invoices |
| `reporting_summary` | – | MRR/ARR, invoiced, collected, outstanding, overdue |
| `reporting_chase` | – | overdue / outstanding collections lists |
| `list_billing_runs` | – | batch history |

## Example session

```jsonc
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_plans",
  "arguments":{"selectable_only":true}}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"create_subscription",
  "arguments":{"customer_id":1,"plan_id":1,"start_date":"2026-11-01",
               "lines":[{"product_id":1,"quantity":2,"tax_rule_id":1}]}}}
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"run_billing_day",
  "arguments":{"on":"2026-11-15"}}}                        // preview only
{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"run_billing_day",
  "arguments":{"on":"2026-11-15","confirm":true}}}
```

## Protocol details

- Protocol versions `2024-11-05`, `2025-03-26`, `2025-06-18` are accepted; anything else falls back to `2025-06-18`.
- Methods: `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`. Batch arrays are supported.
- stdio framing is newline-delimited JSON; logs go to **stderr** so they never corrupt the protocol stream.
- Standard JSON-RPC errors: `-32700` parse, `-32600` invalid request, `-32601` unknown method, `-32602` unknown tool / bad params.

## Tests

```bash
cd backend && .venv/bin/python manage.py test apps.api.tests.test_mcp
```

Covers the handshake, protocol negotiation, the tool catalogue, every mutating tool, read-only refusal, role ceilings (staff vs admin), notification/batch/parse-error handling, and a real HTTP round-trip including the bearer token.
