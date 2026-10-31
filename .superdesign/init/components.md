# Components — Brightloop Frontend

Framework: **React 18 + Vite** (JSX, not TS). Router: react-router-dom v7. Charts: recharts v2. HTTP: axios. CSS: Tailwind v3 (default palette, **no custom tokens yet**).

Shared UI primitives live in `frontend/src/components/ui/`. There are only two so far — both minimal, single-purpose, and hardcoded to the indigo/slate identity.

## Button
- File: `frontend/src/components/ui/Button.jsx`
- Spreads native `<button>` props, merges custom className.
- Hardcoded: `bg-indigo-600 ... hover:bg-indigo-700`, `rounded-lg`, `text-sm font-medium text-white`.
- No variant/size system yet.

```jsx
export default function Button({ children, className = '', ...props }) {
  return (
    <button className={`rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 ${className}`} {...props}>
      {children}
    </button>
  )
}
```

## Card
- File: `frontend/src/components/ui/Card.jsx`
- Renders a `<section>` — the only container primitive used by pages.
- Hardcoded: white bg, `border-slate-200`, `rounded-xl`, `p-6`, `shadow-sm`.

```jsx
export default function Card({ children, className = '' }) {
  return <section className={`rounded-xl border border-slate-200 bg-white p-6 shadow-sm ${className}`}>{children}</section>
}
```

## Notes for design work
- No Input, Select, Dialog, Table, Tabs, Badge, or Avatar primitives exist yet — new module UIs (plans, subscriptions, invoices) will need them designed from scratch, consistent with Button/Card.
- Page code uses Tailwind default palette directly (`indigo-600`, `slate-50/200/500/600/900`); any redesign should either keep or centralize these into tokens.
