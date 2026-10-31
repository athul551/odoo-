# Pages & Dependencies — Brightloop Frontend

Config-based routing in `src/App.jsx` (react-router-dom v7 `Routes`), nested under an `<AppLayout />` route.

## /
Entry: `frontend/src/pages/DashboardPage.jsx`
Dependencies:
- `frontend/src/components/ui/Card.jsx`

Renders: placeholder welcome text ("Welcome to Brightloop") + a Card listing planned modules (Products, plans, customers, quotations, subscriptions, billing, payments, discounts, financial reports).

Dependencies:
- src/pages/DashboardPage.jsx
  - src/components/ui/Card.jsx

## AppLayout (route shell for /)
Entry: `frontend/src/components/layout/AppLayout.jsx`
Dependencies: none (uses `Outlet`)

## * (404)
Entry: `frontend/src/pages/NotFoundPage.jsx`
Dependencies: `react-router-dom` `Link` only. Trivial page — skip in design work.

Dependencies:
- src/pages/NotFoundPage.jsx

## Entry chain (all pages)
- `frontend/index.html` → `frontend/src/main.jsx` (BrowserRouter) → `frontend/src/App.jsx`
- `src/main.jsx` imports `frontend/src/styles/index.css`
- `src/App.jsx` imports `frontend/src/components/layout/AppLayout.jsx`
- `frontend/src/lib/api.js` (axios instance, not imported by any page yet)

## API surface (backend, for designing data views)
Django app modules with urlconfs registered in `backend/config/urls.py`:
`accounts`, `billing`, `common`, `customers`, `payments`, `products`, `quotations`, `reporting`, `subscriptions`.
Auth uses Bearer token from `localStorage['brightloop_access_token']` (see `frontend/src/lib/api.js`).
