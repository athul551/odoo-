# Layouts — Brightloop Frontend

Single app shell, no sidebar/footer/breadcrumbs yet.

- File: `frontend/src/components/layout/AppLayout.jsx`
- Description: Minimal centered page shell — brand wordmark left, tagline right, max-width 6xl, site background comes from `body` in `styles/index.css` (`bg-slate-50 text-slate-900`). Operates as a react-router `Outlet` route.

## AppLayout.jsx (full source)

```jsx
import { Outlet } from 'react-router-dom'

export default function AppLayout() {
  return (
    <main className="mx-auto min-h-screen max-w-6xl px-6 py-12">
      <header className="mb-10 flex items-center justify-between">
        <span className="text-xl font-bold tracking-tight text-indigo-600">Brightloop</span>
        <span className="text-sm text-slate-500">Subscription Management</span>
      </header>
      <Outlet />
    </main>
  )
}
```

- Root file: `index.html` — `<title>Brightloop</title>`, mounts `#root` → `src/main.jsx` (BrowserRouter → App).
- Brand name: **Brightloop** (product is an Odoo-style subscription-management SaaS).
