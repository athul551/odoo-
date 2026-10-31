# Routes — Brightloop Frontend

Router: react-router-dom v7, configured in `frontend/src/App.jsx` (no separate routes file).

| URL path | Component | Layout | Renders |
|---|---|---|---|
| `/` | `frontend/src/pages/DashboardPage.jsx` | `AppLayout` | Placeholder dashboard (welcome + roadmap card) |
| `*` | `frontend/src/pages/NotFoundPage.jsx` | none | "Page not found" + link home |

Full router source (`frontend/src/App.jsx`):

```jsx
import { Route, Routes } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import DashboardPage from './pages/DashboardPage'
import NotFoundPage from './pages/NotFoundPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<DashboardPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
```

## Planned module routes (from codebase skeleton — not yet implemented)
Backend Django apps signal the planned product surface, each likely to become a frontend route:
`/products`, `/customers`, `/quotations`, `/subscriptions`, `/billing`, `/payments`, `/reports`, plus auth (`accounts` app; Bearer token already wired in `lib/api.js`).
