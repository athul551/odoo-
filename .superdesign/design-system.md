# Brightloop — Design System

## Product Context
Brightloop builds the digital backbone of a subscription-first software company: one platform to run products, plans, subscriptions, recurring billing, invoices, payments, discounts and revenue reporting. Users: **admin** (full control: products, plans, taxes, discounts, staff), **internal staff** (day-to-day: quotations→subscriptions→invoices→payments), **customers** (self-service portal: own subscriptions and invoices). Product personality: trustworthy financial infrastructure — Odoo-like business SaaS but focused, calm and fast. Every page must feel responsive at thousands-of-records scale.

## Key Surfaces (from the build spec)
1. **Auth** — signup/login/reset (strong password policy), role-based access (admin / staff / customer portal)
2. **Dashboard** — active subscriptions, revenue collected, outstanding vs overdue, filters + summary
3. **Products & Variants** — name, type, sales price, cost price, notes; variants (e.g. brand → +560)
4. **Plans** — price, frequency (daily/weekly/monthly/yearly), min quantity, availability dates, end-of-term behavior (auto-close / allow early close / pause / renew)
5. **Quotations** — templates with plan/product lines, validity days; quotation → subscription lifecycle Draft → Quotation → Confirmed → Active → Closed
6. **Subscriptions** — number, customer, plan, start/expiry, payment terms, lines (product, qty, unit price, taxes, amount), lifecycle status
7. **Invoices** — generated from subscriptions at billing time, auto tax rules, Draft → Confirmed → Paid; confirm/cancel/send/print
8. **Discounts** — admin-only rules: fixed/percent, min purchase/qty, date range, usage limit, product- or subscription-scoped
9. **Payments** — methods, amount, date, note, matched to invoices; paid vs outstanding tracking
10. **Reports** — finance lead's month-end view: active subs, revenue, amounts owed, overdue invoices

## Branding & Styling
- **Brand primary: indigo-600 (#4f46e5)**, hover indigo-700 — carried from the existing codebase; use as the anchor for the visual system
- **Neutral scale: Tailwind slate** — page bg slate-50, surfaces white, text slate-900 headings / slate-500–600 secondary, borders slate-200
- **Semantic status colors** (new, to systematize lifecycle states): success/emerald (paid, active, confirmed), amber (draft, pending), red (overdue, cancelled), sky (informational)
- **Typography**: modern geometric/neutral sans (Inter-style); clear type scale — page titles ~2xl/3xl bold, section labels 13–14px medium uppercase-tracking for table/card headers, body sm/base
- **Shape & depth**: rounded-lg controls, rounded-xl cards, subtle `shadow-sm`; dense-but-breathable data tables with sticky headers
- **Spacing**: based on Tailwind's default 4px scale; dashboard/app pages in a shell with sidebar navigation replacing the current centered shell
- **Motion**: minimal, fast transitions (150–200ms), no heavy animation — a finance tool should feel instant
- **Layout**: light mode first; admin/staff = dense app layout with sidebar; customer portal = simpler centered or narrow layout
- **Motion/animation patterns**: hover elevation on interactive rows/cards, subtle skeleton states for <2s loads

## Specific Requirements
- Every list/table view must include status badges (subscription & invoice lifecycle), quick filters, and under-2s feel even at scale
- Invoices must show auto-computed tax lines and discounts as visible line items
- Admin-only actions (discounts, staff) must be visually gated
- Keep design tokens implementable directly in the codebase's Tailwind (indigo/slate defaults, no exotic CSS)
