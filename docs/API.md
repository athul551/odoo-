# Brightloop REST API

Base URL: `http://localhost:8000/api/`

All authenticated calls send `Authorization: Bearer <access-token>`. Access tokens live 30 minutes; refresh tokens 7 days and rotate on blacklist (logout, password change, password reset).

## Error shape

Every failure — domain rule, permission, validation, conflict — answers in one envelope:

```json
{
  "errors": { "field_or_detail": ["human readable message"] },
  "code": "optional_machine_code"
}
```

`errors` is an object of field → messages, or a list for non-field problems. `code` appears when a client should branch:

| HTTP | `code` | Meaning |
|---|---|---|
| 400 | – | Validation / domain rule refused the request |
| 401 | – | Missing, expired or blacklisted token |
| 403 | – | Authenticated but the role is not allowed |
| 404 | – | Not found — **or** a portal user asking for another customer's row |
| 409 | `invalid_transition` | Illegal subscription stage move |
| 409 | `conflict` | Two writers raced on a unique/check constraint; retry |
| 429 | – | Throttled (login, register, password reset) |

## Authentication

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `auth/register/` | public | Customer sign-up: creates the Customer **and** its first Customer User atomically. Returns JWT pair + profile. |
| POST | `auth/token/` | public | Login. Returns `access`, `refresh`, `user`. |
| POST | `auth/token/refresh/` | public | Rotate an access token. |
| POST | `auth/logout/` | any | Blacklist the supplied refresh token. |
| GET/PATCH | `auth/me/` | any | Profile; PATCH only `first_name`/`last_name`. |
| POST | `auth/password/reset/` | public | Email a single-use reset link. Always 200 — no account enumeration. |
| POST | `auth/password/reset/confirm/` | public | `{uid, token, new_password, new_password_confirm}`. |
| POST | `auth/password/change/` | any | `{current_password, new_password, new_password_confirm}`; returns a fresh JWT pair. |

Password policy (spec): **more than eight characters** (min 9) with at least one uppercase, one lowercase and one special character. Changing or resetting a password revokes every outstanding refresh token.

### Sign-up

```bash
curl -sX POST localhost:8000/api/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@shire.io","password":"Sunshine!9qZ",
       "password_confirm":"Sunshine!9qZ","organization_name":"Shire Logistics"}'
```

## Roles

| Resource | Admin | Staff | Customer (portal) |
|---|---|---|---|
| `users/` | full | — | — |
| `products/`, `plans/` | full | read | read |
| `tax-rules/` | full | read | — |
| `discount-rules/` | full | — | — |
| `quotation-templates/` | full | full | — |
| `customers/` | full | full | read own |
| `subscriptions/` | full | full | read own |
| `invoices/` | full | full | read own |
| `payments/` | full | full | — (visible inside their invoices) |
| `billing-runs/` | full | full | — |
| `reporting/` | read | read | — |

Portal users are **scoped in the queryset**, so another customer's record is a 404 — not a 403 that would confirm it exists.

## Resources

Pagination: `?page=&page_size=` (page size capped at 200). Every list returns `{count, next, previous, results}`.

### Customers

`GET|POST /customers/`, `GET|PATCH|DELETE /customers/{id}/`
Filters: `?q=` (name / contact email). Response includes `subscription_count`.

### Products and plans

`GET|POST /products/`, `GET|PATCH|DELETE /products/{id}/`
- `variants` is a nested list with **replace semantics**: unknown axis/value pairs are created, known ones updated, omitted ones deactivated (never deleted — subscription lines protect them).
- `effective_price = sales_price + price_delta` and may never go negative.

```json
{
  "name": "CRM Suite", "type": "service",
  "sales_price": "100.00", "cost_price": "40.00",
  "variants": [{"attribute": "brand", "value": "Odoo", "price_delta": "560.00"}]
}
```

`GET|POST /plans/`, `GET|PATCH|DELETE /plans/{id}/`
Filters: `?product=`, `?frequency=`, `?selectable=true`, `?include_archived=true`.
Plan behaviors (`auto_close_on_expiry`, `allow_early_close`, `allow_pause`, `allow_renew`) default to the documented model values even for form-encoded clients.

### Quotation templates

`GET|POST /quotation-templates/`, `GET|PATCH|DELETE /quotation-templates/{id}/` — nested `lines` replace the blueprint; `unit_price` is snapshotted from the product/variant price.

### Subscriptions

`GET|POST /subscriptions/`, `GET|PATCH|DELETE /subscriptions/{id}/`
Filters: `?stage=`, `?customer=`, `?plan=`, `?q=`.
PATCH accepts only `start_date`, `expiry_date`, `payment_terms_days` — stages move through actions.
Each subscription serialises its `pause_periods` (`{id, started_on, ended_on, reason}`; `ended_on: null` means still paused) and `allow_pause` (the plan's switch), so the portal only offers the action when it is legal.

Stage actions (`POST /subscriptions/{id}/…`):

| Action | Transition | Notes |
|---|---|---|
| `send-quotation/` | Draft → Quotation | requires ≥1 line; sets `validity_until` |
| `confirm/` | Quotation → Confirmed | refuses lapsed validity / a plan that left its window |
| `activate/` | Confirmed → Active | optional `start_date`, `expiry_date` |
| `close/` | any open → Closed | `{reason}`; early close may be refused by the plan |
| `renew/` | Active stays Active | extends one calendar-safe period; reopens an expired Closed term |
| `pause/` / `resume/` | flag on Active | records a pause span; billing drops overlapping periods. Staff/admin may pause any Active subscription; a **customer may pause/resume their own** when the plan allows it |

Line editing (Draft/Quotation only):

```
POST   /subscriptions/{id}/lines/              {product, variant?, quantity, tax_rule?, unit_price?}
DELETE /subscriptions/{id}/lines/{line_id}/
```

`POST /subscriptions/` body: `{customer, plan, start_date, expiry_date?, payment_terms_days?, origin_template?, lines[]}`. The plan must be selectable today; `(product, variant)` may appear once; quantity must meet the plan minimum. Re-adding the same product answers **409 `conflict`**.

### Invoices

`GET /invoices/`, `GET /invoices/{id}/`
Filters: `?status=`, `?customer=`, `?subscription=`, `?overdue=true`, `?unpaid=true`.
The list shape is light (no lines/payments); the detail includes lines, payments and applied discounts.

Actions: `POST /invoices/{id}/confirm/` (issues it, sets `due_date` from payment terms), `send/` (marks it sent **and emails the customer's contact email** through Django's email backend — configure SMTP in production), `mark-printed/`, `cancel/` (`{reason}`). The console prints through a dedicated printable view.
Cancelling a confirmed/paid invoice with payments attached is refused — remove the payments first. The freed period rebills in the next run.

### Payments

`GET /payments/`, `POST /payments/`, `DELETE /payments/{id}/`
Filters: `?invoice=`, `?customer=`.
Overpayment is refused with the exact remaining amount. The invoice status derives from the ledger: fully covered → `paid`; a removed payment drops it back to `confirmed`.

```json
{"invoice": 12, "amount": "118.00", "method": "card", "reference": "TXN-1"}
```

### Discount rules (admin only)

`GET /discount-rules/`, `POST /discount-rules/`, `GET /discount-rules/{id}/`, `POST /discount-rules/{id}/deactivate/`
Rules are never deleted; deactivation keeps issued invoices truthful.

```json
{"name": "Launch 10", "scope": "product", "kind": "percent", "value": "10.00",
 "applies_from": "2026-01-01", "product_ids": [3], "usage_limit": 100}
```

### Billing runs

`GET /billing-runs/`, `GET /billing-runs/{id}/`, `POST /billing-runs/run/`

```json
{"on": "2026-11-15", "dry_run": true}
```

`dry_run: true` answers "what would tonight bill" with no writes. A real run is idempotent: a period already invoiced is skipped, a cancelled invoice frees its period for rebilling.

The batch is isolated per subscription: one malformed record is reported in `report.failed` (and counted in `failed_count`) while every other invoice still commits, and the run row itself is written before any work so an attempt is always auditable.

The preview also reports revenue waiting on ended terms:

```json
{"on": "2026-05-01", "subscriptions": 1, "invoices": 3, "missed_periods": 3,
 "problems": [], "items": [{"subscription": "SUB-2026-000001", "period_start": "2026-01-01",
 "period_end": "2026-02-01", "term_ended": true}]}
```

`missed_periods` counts due periods of subscriptions whose term has already ended — the signal that a billing day was skipped. Paused spans are never billed, before or after a resume.

Schedulers call `python manage.py bill_day [--on DATE] [--dry-run]`; it exits non-zero when any record failed. `python manage.py sweep_subscriptions [--on DATE]` closes Active subscriptions on `auto_close_on_expiry` plans whose term has ended (without it that per-plan switch does nothing, and expired Actives inflate MRR).

### Reporting

`GET /reporting/summary/?start=&end=&as_of=&customer_id=` — active/paused subscriptions, MRR/ARR, invoiced, collected, outstanding, overdue.
`GET /reporting/chase/?kind=overdue|outstanding&older_than_days=&page=&page_size=` — collections lists, oldest due first.

MRR normalisation is declared domain maths: daily ×365⁄12, weekly ×52⁄12, monthly ×1, yearly ÷12, aggregated in SQL. Only Active, unpaused subscriptions still inside their term count: an expired term carries no MRR even before the sweep closes it.

### Developer console (`/ops/`, admin only)

Off unless `OPS_TOOLS_ENABLED` is on (it defaults to `DEBUG`); disabled endpoints answer **404**, not 403, so a production deployment never advertises them.

| Endpoint | What it returns |
|---|---|
| `GET /ops/overview/` | connection details, business row counts, migration totals |
| `GET /ops/migrations/` | applied + pending migrations per app, with timestamps |
| `POST /ops/migrations/` | runs `migrate` and returns its output plus the new state |
| `GET /ops/tables/` | every table with an exact row count and on-disk size |
| `GET /ops/logs/?limit=` | recent HTTP requests and the SQL each one executed |
| `DELETE /ops/logs/` | clears the in-memory buffers |
| `POST /ops/demo-data/` | seeds one coherent demo tenant (idempotent) |

The request/SQL buffers are per-worker, in-memory and bounded (300 entries); they exist to answer "what did that click actually send to Postgres?" in development, not as an audit trail.

## Performance

The spec's "under 2 seconds with thousands of records" is enforced by tests: `apps/api/tests` plus `apps/reporting/tests.ScalePerformanceTests` seed thousands of rows and assert both the wall clock and a query-count ceiling.

## Quick smoke

```bash
TOKEN=$(curl -sX POST localhost:8000/api/auth/token/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@brightloop.io","password":"Sunshine!9qZ"}' | jq -r .access)

curl -s localhost:8000/api/subscriptions/?stage=active -H "Authorization: Bearer $TOKEN"
curl -sX POST localhost:8000/api/billing-runs/run/ -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"dry_run": true}'
```
