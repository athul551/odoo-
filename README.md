# Brightloop Subscription Management System

Brightloop is a full-stack subscription-management system: plans and products, quotations, subscription lifecycles, recurring billing, payments, discounts, reporting — with a REST API, a staff/admin console, a customer portal, and an MCP server that lets AI agents drive the same domain.

## Architecture

- `frontend/`: React single-page application built with Vite, Tailwind CSS, React Router, Axios, and Recharts.
- `backend/`: Django + Django REST Framework API, divided into domain apps so each area owns its models, serializers, services, and endpoints.
- PostgreSQL is the production and local development database. Docker Compose is included to start it consistently.
- JWT access/refresh tokens are provided by Django REST Framework Simple JWT. The frontend Axios client adds an access token when one is available.
- `backend/mcp_server/`: a Model Context Protocol server (stdio + HTTP) exposing the domain as tools for Claude Code, Codex, Cursor or any MCP client.

Domain rules live in `CONTEXT.md`; locked decisions live in `docs/adr/`. The API contract is documented in `docs/API.md`, the agent surface in `docs/MCP.md`.

See the setup instructions below before starting either service.

## Folder structure

```text
brightloop/
├── backend/
│   ├── config/                 # Django project settings and URL entry points
│   │   └── settings/            # base, development, production settings
│   ├── apps/
│   │   ├── common/              # shared health/API utilities, numbering, time math
│   │   ├── accounts/            # email-login users, roles, JWT, password flows
│   │   ├── api/                 # REST serializers, viewsets, error envelope
│   │   ├── products/            # products, variants, plans
│   │   ├── customers/           # customer organizations
│   │   ├── quotations/          # quotation templates
│   │   ├── subscriptions/       # subscriptions, lines, stage machine
│   │   ├── billing/             # tax rules, invoices, discounts, billing runs
│   │   ├── payments/            # payment ledger
│   │   └── reporting/           # finance summary and chase lists
│   ├── mcp_server/              # MCP tools over the same services
│   ├── bin/brightloop-mcp       # launcher for MCP clients
│   ├── .env.example
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/          # reusable layout and UI components
│   │   ├── lib/api.js           # Axios API client and JWT header support
│   │   ├── pages/               # route-level components
│   │   └── styles/              # Tailwind entry stylesheet
│   ├── .env.example
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.js
├── docker-compose.yml           # PostgreSQL service
└── README.md
```

## Quick start

1. Copy environment templates:

   ```powershell
   Copy-Item backend/.env.example backend/.env
   Copy-Item frontend/.env.example frontend/.env
   ```

2. Start PostgreSQL (requires Docker Desktop):

   ```powershell
   docker compose up -d db
   ```

3. Create and activate a Python virtual environment, then install the API packages:

   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   python manage.py migrate
   python manage.py runserver
   ```

   If PowerShell blocks activation, use `cmd /c .venv\Scripts\activate.bat` or permit the process-scoped policy with `Set-ExecutionPolicy -Scope Process Bypass`.

4. In another terminal, install and start the frontend. Use `npm.cmd` on Windows where PowerShell blocks `npm.ps1`:

   ```powershell
   cd frontend
   npm.cmd install
   npm.cmd run dev
   ```

Open `http://localhost:5173`. The API health check is at `http://127.0.0.1:8000/api/health/`.

## Verification

With PostgreSQL running and the packages installed:

```powershell
cd backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```

```powershell
cd frontend
npm.cmd run build
```

## Agents (MCP)

```bash
cd backend
.venv/bin/python -m mcp_server --print-tools          # discover tools
.venv/bin/python -m mcp_server --actor you@example.io  # stdio server
```

Any MCP client can connect through `backend/bin/brightloop-mcp`; see `docs/MCP.md` for Claude Code, Codex, Cursor and HTTP connector configuration, plus the safety model (role ceiling, read-only mode, dry-run billing).

## Backend console (frontend)

`frontend/` is a React console over the REST API, built to exercise the backend end to end: customers, catalog, the subscription stage machine, billing day, invoices/payments, and a Database page with migration state, table counts and a live request/SQL log.

```bash
# terminal 1
cd backend && .venv/bin/python manage.py runserver

# terminal 2
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173` and sign in with an admin account. If the database has none:

```bash
cd backend
.venv/bin/python manage.py createsuperuser
```

The Dashboard has a **Seed demo tenant** button (admin) that creates a product, plan, two customers and three subscriptions in different stages, so the Billing page has something to preview and bill immediately.

The Database page is served by `/api/ops/` and is enabled only while `OPS_TOOLS_ENABLED` is on (defaults to `DEBUG`). It can apply pending migrations and shows the last 300 requests and SQL statements of the worker that served the page.

## Operations

Two management commands are the scheduler surface; point cron (or a sidecar) at them nightly:

```bash
cd backend
.venv/bin/python manage.py bill_day --dry-run          # what tonight would bill, no writes
.venv/bin/python manage.py bill_day                    # idempotent batch; exits non-zero on any failed record
.venv/bin/python manage.py sweep_subscriptions         # close expired terms on auto_close_on_expiry plans
```

Both accept `--on YYYY-MM-DD` to backfill or replay a date. The billing batch commits each subscription in its own savepoint: one bad record lands in `report.failed` while every healthy invoice survives, and the run row is written before any work so the attempt is always visible.

### Production notes

- Set `REDIS_URL` so throttle counters (login, writes) are shared across gunicorn workers; without it each worker keeps its own LocMem counter and the configured limits multiply by the worker count.
- The MCP HTTP transport refuses a non-loopback bind without `--token`. Keep the default `127.0.0.1` for local agents, or set the token before containerising it.
