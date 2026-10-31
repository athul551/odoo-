# Theme — Brightloop Frontend

## Part 1 — Compact token summary (no custom tokens exist; this is the de-facto palette from usage)

**Identity / brand**
- Primary/brand color: Tailwind `indigo-600` (`#4f46e5`), hover `indigo-700` (`#4338ca`) — used by logo, Button
- Surfaces: page bg `slate-50` (`#f8fafc`) via `body`; cards white with `border-slate-200` (`#e2e8f0`), `rounded-xl`, `shadow-sm`
- Page text: `slate-900` (`#0f172a`) headings, `slate-500/600` (`#64748b` / `#475569`) secondary via Tailwind defaults

**Typography**
- Font: system default (plain `<body>` — no font-family config anywhere)
- Wordmark: `text-xl font-bold tracking-tight` (indigo-600)
- Page title: `text-3xl font-bold`
- Body: default 16px; secondary text `text-sm`

**Shape & spacing**
- Buttons: `rounded-lg`, `px-4 py-2`
- Cards: `rounded-xl`, `p-6`
- Layout: centered shell `max-w-6xl mx-auto px-6 py-12`

**Tailwind config**: empty extend — nothing customized yet. Breakpoints/colors are stock Tailwind 3.4 defaults. Light mode only, no dark theme.

## Part 2 — Raw source

### frontend/tailwind.config.js
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: { extend: {} },
  plugins: [],
}
```

### frontend/src/styles/index.css (entire global CSS)
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body { @apply bg-slate-50 text-slate-900 antialiased; }
}
```

### Design-space note
The design system is effectively **un-built**: brand color is only implied by hardcoded Tailwind classes. A redesign session may establish real tokens (brand palette, font, dark mode) and the design output should indicate values to centralize into `tailwind.config.js` → `theme.extend`.
