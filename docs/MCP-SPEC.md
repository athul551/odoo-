# Brightloop MCP server — specification

Status: **normative for this repository**
Protocol baseline: MCP `2025-06-18` (versions `2024-11-05`, `2025-03-26` accepted)
Server: `brightloop` (`mcp_server/`, Python, stdlib only)

This document defines the contract between the Brightloop MCP server and an MCP
client: what must be on the wire, what the server must refuse, and what every
tool must guarantee. It is **not** a copy of the upstream Model Context
Protocol specification — upstream remains authoritative for JSON-RPC framing and
MCP semantics. Where the two disagree on the wire, upstream wins; where they
disagree on Brightloop's tools, security or authority model, this document wins.

The implementation lives in `backend/mcp_server/`; the operator guide is
`docs/MCP.md`; conformance tests are `backend/apps/api/tests/test_mcp.py`.

## 1. Scope

In scope:

- transports (`stdio`, `HTTP`), framing, lifecycle, error model;
- the tool catalogue contract: discovery, schemas, invocation, result shape;
- the authority model (actor, role ceiling, read-only, confirmation gates);
- security requirements for binding the server beyond localhost.

Out of scope (the server MUST NOT claim these capabilities):

- MCP resources, prompts, sampling, elicitation, roots;
- server-initiated streams (SSE) and subscriptions;
- multi-tenant sessions: one process acts as exactly one actor.

## 2. Conformance language

`MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT` and `MAY` are used as in RFC 2119.
A conforming server satisfies every `MUST`; deviations from a `SHOULD` are
listed in §12.

## 3. Authority model

3.1 **Actor.** The server acts as exactly one user, chosen at process start
(`--actor`, `BRIGHTLOOP_MCP_ACTOR`, else the first active admin). A client
MUST NOT be able to choose or override the actor per request.

3.2 **Staff only.** The actor MUST be `staff` or `admin`. A customer-role
actor MUST cause startup to fail with a non-zero exit: the portal is not an
automation surface.

3.3 **Role ceiling.** A tool MUST NOT grant more authority than the REST API
grants the same actor. Tools that require an admin (discount rules, user
management) MUST fail for a staff actor with a tool error, not a protocol
error.

3.4 **Read-only mode.** With `--read-only` (or `BRIGHTLOOP_MCP_READ_ONLY=1`),
the catalogue MUST remain fully visible, and every write tool MUST refuse to
execute and return `isError: true` with a JSON body explaining why. The server
MUST NOT hide write tools, so a client can reason about the full surface.

3.5 **Service layer only.** Every tool MUST call the same domain service the
REST API calls (`apps.*.services`). A tool MUST NOT write through the ORM
directly, and MUST NOT reimplement a business rule.

3.6 **Confirmation gates.** Tools whose effect is a batch or a sweep MUST
require `confirm: true` and MUST return a read-only preview otherwise:

| Tool | Gate |
|---|---|
| `run_billing_day` | `confirm: true`; otherwise returns the billing preview |
| `sweep_expired_subscriptions` | `confirm: true`; otherwise returns `would_close` |

3.7 **Destructive annotation.** Because any write can move money or state,
every write tool MUST be annotated `destructiveHint: true` — even creations.
This is deliberately conservative: agents should ask before writing.

## 4. Transports

### 4.1 stdio (default)

- One JSON-RPC message per line, UTF-8, newline-delimited.
- The server MUST read from stdin and write responses to stdout.
- stdout MUST contain protocol messages only. All logging MUST go to stderr.
- Blank lines MUST be ignored.
- The process MUST exit when stdin closes.

### 4.2 HTTP

- Endpoint: `POST /mcp` (a trailing slash and the root path are accepted).
- Request body MUST be UTF-8 JSON. A body larger than 1,000,000 bytes MUST be
  rejected with `400`.
- `Content-Length` is required; a missing or zero length is treated as an empty
  body and rejected with `400`.
- A request that produces a response MUST answer `200` with
  `Content-Type: application/json`.
- A request that is only notifications (or a batch of notifications) MUST
  answer `202` with no body.
- `GET /mcp` MUST answer `405` with `Allow: POST, DELETE`: this server never
  opens a server-initiated SSE stream.
- `DELETE /mcp` MUST be a no-op (`204`): sessions are stateless.
- Every response MUST carry `Mcp-Session-Id: brightloop`. The header is
  informational; clients MUST NOT rely on server-side session state.

### 4.3 Binding and authentication (fail closed)

- A non-loopback bind (`--host` other than `127.0.0.1`, `localhost`, `::1`)
  MUST be refused at startup unless a bearer token is configured. Startup MUST
  exit with status `2` and a message that names `--token`.
- The request handler MUST re-check the bind host, so a server constructed
  directly (bypassing the CLI) cannot serve an open bind.
- When a token is configured, every `POST /mcp` MUST require
  `Authorization: Bearer <token>` and MUST answer `401` otherwise.
- A loopback bind without a token is allowed and MUST print a warning: local
  agents are trusted, network peers are not.
- TLS termination is the deployment's responsibility; the server MUST be put
  behind a TLS reverse proxy before it leaves localhost.

## 5. Message model

5.1 Every message MUST be a JSON object with `"jsonrpc": "2.0"`, a `method`
string, and optional `params`. An `id` makes it a request; its absence makes it
a notification.

5.2 The response MUST echo `id` and contain exactly one of `result` or `error`.

5.3 A top-level JSON array is a batch. The server MUST answer with an array of
responses, omitting notifications. An empty array MUST answer `-32600`. A batch
containing only notifications MUST produce no response (`202` over HTTP).

5.4 Notifications MUST NOT produce a response, even when they are unknown or
malformed.

5.5 Error codes:

| Code | Meaning | When |
|---|---|---|
| `-32700` | Parse error | body is not JSON |
| `-32600` | Invalid request | not an object, missing/blank `method`, empty batch |
| `-32601` | Method not found | unknown MCP method |
| `-32602` | Invalid params | unknown tool name, `arguments` not an object |
| `-32603` | Internal error | defensive catch-all |

5.6 The server MUST NOT leak a stack trace or source path to the wire. Error
messages MAY contain an exception class and message.

## 6. Lifecycle

6.1 `initialize` MUST return:

```json
{
  "protocolVersion": "2025-06-18",
  "capabilities": {"tools": {"listChanged": false}},
  "serverInfo": {"name": "brightloop", "title": "...", "version": "1.0.0"},
  "instructions": "..."
}
```

6.2 Version negotiation: if `params.protocolVersion` is one of
`2024-11-05`, `2025-03-26`, `2025-06-18`, the server MUST echo it. Otherwise it
MUST answer the newest supported version (`2025-06-18`). It MUST NOT fail the
handshake over a version it does not know.

6.3 The server is stateless. Clients SHOULD send `notifications/initialized`
after the handshake; the server MUST accept and ignore it. `tools/list` and
`tools/call` MAY be served without a prior `initialize`.

6.4 `notifications/cancelled` MUST be accepted and ignored (no in-flight work
to cancel: calls are synchronous).

6.5 `ping` MUST return an empty object.

## 7. Tools

### 7.1 Discovery — `tools/list`

- MUST return every tool, sorted by `name` (stable ordering for diffs).
- Each entry MUST carry `name`, `description`, `inputSchema` (a JSON Schema
  object) and `annotations` with `readOnlyHint` and `destructiveHint`.
- `readOnlyHint` MUST be `true` exactly when the tool performs no write.
- Tool names MUST be `snake_case` and stable. Renaming a tool is a breaking
  change (§10).

### 7.2 Invocation — `tools/call`

- `params.name` MUST identify a tool; an unknown name MUST answer `-32602`
  (protocol error), not a tool error.
- `params.arguments` MUST be an object when present; anything else MUST answer
  `-32602`.
- The result MUST be:

```json
{"content": [{"type": "text", "text": "<JSON>"}], "isError": false}
```

- `text` MUST be JSON. It MAY be pretty-printed and MUST use `default=str` for
  non-JSON values (dates, decimals) so the client always receives valid JSON.

### 7.3 Failure semantics

- Domain failures — `ValidationError`, `PermissionDenied`,
  `InvalidTransition`, and unexpected exceptions — MUST be returned as
  `isError: true` with the same JSON error shape as the REST API:
  `{"errors": {"field": ["message"]}}` or `{"errors": {"detail": [...]}}`,
  plus `code: "invalid_transition"` for stage violations.
- `isError` MUST NOT be used for protocol errors; those use JSON-RPC `error`.
- A tool failure MUST NOT terminate the process or the HTTP connection.
- A read-only refusal MUST be an `isError` result, not `-32602`.

### 7.4 Input conventions

- Dates: ISO `YYYY-MM-DD`; omitted dates default to the server's today.
- Identifiers: integers (`customer_id`, `plan_id`, `product_id`, `tax_rule_id`).
- Money: decimal strings, never floats.
- Enumerations: declared in `inputSchema`; unknown values MUST fail validation.
- A tool MUST reject unknown *required* context with a clear message; it MAY
  ignore unknown optional keys.

### 7.5 Catalogue requirements

Every tool MUST:

1. map to a domain service call, with the actor passed explicitly;
2. declare `write` correctly (and therefore its annotations);
3. be covered by at least one conformance test (§11);
4. document its confirmation gate, if any, in its `description`.

The current catalogue (15 read, 11 write, 26 total) is listed in `docs/MCP.md`.
Adding, removing or renaming a tool MUST update that table and this document's
version.

## 8. Domain invariants the tools must preserve

The MCP surface MUST NOT weaken any invariant the REST API enforces:

- **Billing is idempotent.** Re-running `run_billing_day` for the same date
  MUST NOT create a duplicate invoice for a period. A cancelled invoice frees
  its period (credit-then-rebill).
- **Batch isolation.** A malformed subscription MUST be reported in
  `report.failed` and MUST NOT abort the rest of the batch.
- **No skipped periods.** Due periods of a term that already ended MUST still
  be billable; the preview MUST surface them as `missed_periods`.
- **Pause stops billing.** A period overlapping a recorded pause span MUST NOT
  be billed, before or after a resume.
- **Payments never overpay.** `record_payment` MUST refuse an amount above the
  remaining due.
- **Stage machine is linear.** `subscription_transition` MUST reject skipped or
  backward moves with `code: "invalid_transition"`.
- **Portal scoping is irrelevant here** — MCP actors are staff/admin — but a
  tool MUST NOT expose another customer's rows to a customer-scoped actor,
  because such an actor cannot start the server.

## 9. Security requirements

- The actor is fixed at startup; no request header, query parameter or tool
  argument may change it.
- The bearer token MUST NOT be logged, echoed, or included in tool output.
- Request bodies MUST be bounded (§4.2) and MUST be parsed as UTF-8.
- The server MUST NOT enable CORS; it is not a browser-facing API.
- The server MUST refuse to start as a customer-role user, and MUST refuse an
  open bind without a token.
- Tool output MUST be limited to what the corresponding REST serializer
  returns; no passwords, tokens or session identifiers.
- Rate limiting and request logging are the reverse proxy's job; the server
  provides neither (§12).

## 10. Versioning and compatibility

- `PROTOCOL_VERSION` is the newest supported MCP version; the accepted list is
  `SUPPORTED_PROTOCOL_VERSIONS`. Adding a version is additive.
- Tool names and input schemas are a public API. Additive changes (new optional
  argument, new tool) are minor. Removing an argument, tightening a type or
  renaming a tool is breaking and MUST ship as a new tool name plus a
  deprecation note in `docs/MCP.md`.
- `serverInfo.version` follows semver and MUST change when the catalogue
  changes.
- A client that ignores unknown result fields MUST keep working; the server
  SHOULD only add fields, never repurpose them.

## 11. Conformance tests

A change to `mcp_server/` MUST keep these green
(`cd backend && .venv/bin/python manage.py test apps.api.tests.test_mcp`):

1. `initialize` handshake shape and `serverInfo`.
2. Unknown protocol version falls back to the newest supported.
3. `tools/list` returns the full catalogue, sorted, with annotations.
4. Every write tool is annotated destructive and every read tool is not.
5. Every tool's `inputSchema` is an object with a `properties` map.
6. `tools/call` unknown tool → `-32602`; non-object arguments → `-32602`.
7. Domain failure → `isError: true` with the REST error shape.
8. `invalid_transition` carries its machine code.
9. Read-only mode refuses every write tool and allows every read tool.
10. Staff cannot call admin-only tools; admin can.
11. Notifications produce no response; batches return one response per request;
    parse errors return `-32700`; empty batch returns `-32600`.
12. HTTP round trip: `200` + JSON, `202` for notifications, `401` without the
    token, `405` on GET, `204` on DELETE.
13. Fail-closed bind: non-loopback without a token raises `ValueError`;
    loopback without a token is allowed.
14. `--print-tools` emits the catalogue as JSON and exits 0.
15. A billing preview followed by `confirm: true` bills exactly once.

## 12. Known limitations

Recorded here so they are decisions, not surprises:

- **No resources, prompts or sampling.** The domain is exposed as tools only.
- **No SSE.** `GET /mcp` is `405`; a client that requires a server stream is not
  supported.
- **Stateless sessions.** `DELETE /mcp` is a no-op and `Mcp-Session-Id` is
  constant.
- **`DELETE /mcp` is unauthenticated** (it changes nothing). A future revision
  SHOULD authenticate it for uniformity.
- **Token comparison is `==`**, not constant-time. A future revision SHOULD use
  `hmac.compare_digest`.
- **One actor per process.** Multi-tenant hosting needs one process per actor
  (or a token-to-actor map, which is not implemented).
- **No per-tool throttling.** Put a rate limiter in front of the HTTP transport.
- **No chunked request bodies.** `Content-Length` is required.

## 13. Compliance checklist for new tools

- [ ] Calls a domain service with the actor; no ORM writes.
- [ ] `write` flag correct; annotations follow from it.
- [ ] Description states the effect and any `confirm` gate.
- [ ] Input schema uses ISO dates, integer ids, decimal strings.
- [ ] Failures use the REST error shape; stage errors carry `invalid_transition`.
- [ ] Added to `docs/MCP.md` and covered by a conformance test.
- [ ] `serverInfo.version` bumped if the catalogue changed.
