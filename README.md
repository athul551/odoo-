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
