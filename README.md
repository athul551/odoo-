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

Any MCP client can connect through `backend/bin/brightloop-mcp`; see `docs/MCP.md` for Claude Code, Codex, Cursor and HTTP connector configuration, plus the safety model (role ceiling, read-only mode, dry-run billing). The normative contract is [`docs/MCP-SPEC.md`](docs/MCP-SPEC.md).

## Frontend (calm-dark product UI)

`frontend/` is the full product surface over the REST API, built in the calm-dark
design system (`#1E1E1E` canvas, hairline panels, one `#7AA2F7` accent, 60px
controls, 12-column layouts). Tokens live in `frontend/tailwind.config.js`;
`docs/` and `.superdesign/design-system.md` describe the intent.

```bash
# terminal 1
cd backend && .venv/bin/python manage.py runserver

# terminal 2
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173`. Sign-up is public and creates a Customer
organization plus its first portal user; staff/admin accounts come from
`manage.py createsuperuser` (or the admin Users page). After sign-in the app
routes by role:

| Role | Landing | Surfaces |
|---|---|---|
| Customer | `/portal` | Overview, subscriptions, invoices, account (profile, password) |
| Staff / Admin | `/` | Dashboard, customers, catalog (products, plans, tax rules, quotation templates), subscriptions + stage machine, billing (preview, runs, invoices, payments), reporting (month-end + chase lists), database |
| Admin only | — | Discounts, Users, Database (migrations, tables, request + SQL log) |

Auth screens are `/login`, `/signup`, `/forgot-password`, `/reset-password`.
The Dashboard has a **Seed demo tenant** button (admin) so billing has
something to preview and bill immediately.

## Operations

Two management commands are the scheduler surface; point cron (or a sidecar) at them nightly:

```bash
cd backend
.venv/bin/python manage.py bill_day --dry-run          # what tonight would bill, no writes
.venv/bin/python manage.py bill_day                    # idempotent batch; exits non-zero on any failed record
.venv/bin/python manage.py sweep_subscriptions         # close expired terms on auto_close_on_expiry plans
```

Both accept `--on YYYY-MM-DD` to backfill or replay a date. The billing batch commits each subscription in its own savepoint: one bad record lands in `report.failed` while every healthy invoice survives, and the run row is written before any work so the attempt is always visible.

### Database backup

The database lives in the compose volume `odoo-_postgres_data`; there is no
second copy unless you make one. Dump it before migrations, restores or demos:

```bash
./scripts/backup-db.sh                          # backups/brightloop-<timestamp>.sql.gz
./scripts/restore-db.sh backups/<file>.sql.gz   # into an empty database
```

Both scripts work with `docker compose` or `docker-compose`, honour
`DB_SERVICE`, `DB_NAME`, `DB_USER` and `BACKUP_DIR`, and the dumps are plain
SQL (gzip), so they restore on any Postgres 16. `backups/` is gitignored: keep
dumps out of the repository and copy them somewhere off this machine.

A nightly line in the user crontab is enough for a dev box:

```cron
0 2 * * * cd "/path/to/odoo-" && ./scripts/backup-db.sh >> backups/cron.log 2>&1
```

### Production notes

- Set `REDIS_URL` so throttle counters (login, writes) are shared across gunicorn workers; without it each worker keeps its own LocMem counter and the configured limits multiply by the worker count.
- The MCP HTTP transport refuses a non-loopback bind without `--token`. Keep the default `127.0.0.1` for local agents, or set the token before containerising it.
