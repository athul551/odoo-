# Brightloop — Design System (Calm Operations, Dark First)

## Product Context

Brightloop is a subscription-management operating system: plans & products, quotations, subscription lifecycles (Draft → Quotation → Confirmed → Active → Closed), recurring billing runs, invoices, payments, discounts, and revenue reporting.

Users:
- **Admin** — full control: users, products/plans, tax rules, discount rules, plus everything staff do.
- **Staff** — day-to-day: customers, subscriptions, billing day, invoices, payments, reporting.
- **Customer (portal role)** — self-service only: sees their own customer account's subscriptions and invoices.

Design personality: a calm, professional, welcoming operations tool. Visual noise creates operator anxiety on a system that moves real money; this UI must reassure through structure, restraint, and instant spatial orientation. Gear toward long working shifts and thousands of records.

## Core Blueprint (constraint summary — hard rules, not suggestions)

1. **Spatial ergonomics**
   - Every screen is laid out on a **12-column grid** (desktop canvas ~1920px, 15–20px gutters). Alignment is non-negotiable.
   - **Macro padding**: 80–100px vertical padding between major operational modules. **Micro gaps**: 15–20px between fields/buttons.
   - Dense tables still breathe: generous row height (≥56px), generous section spacing.
2. **Orientation & IA**
   - Universal **top nav bar** (system-wide: brand, global search, service switcher/billing day, profile) + contextual **side rail** for sub-module sections. Cog layer, not decoration.
   - **Unmistakable active states**: high-contrast background tint + bold accent indicator on the active nav item / tab. Never let the operator guess where they are or what mode they're in (esp. read-only vs editable, draft vs issued).
   - **Typographic hierarchy**: overview titles 48–60px, module subheaders 24–36px, table body 14–18px crisp readable text.
3. **Tactile ergonomics**
   - All high-frequency interactive controls (primary CTAs, search bars, filters, form inputs, selects) standardized to **60px height**.
   - **Button tiers**: primary = solid filled neutral-light-on-dark or single accent; secondary = muted outline/tinted; destructive = reserved alert tone, only for irreversible actions (close subscription, cancel invoice, remove payment, deactivate rule).
   - One primary CTA per screen region. Fewer, larger, calmer controls beat many small ones.
4. **Color economy**
   - **Dark operations base**: background `#1E1E1E` (page) with slightly raised neutral panels `#252526`–`#2A2A2D` and hairline borders `#3A3A3D`. Avoid saturated color on bulk data.
   - Data containers stay grayscale; **one restrained accent (soft leading blue, e.g. #6B9AFF-family, desaturated for dark bg) is reserved only for**: active/focused states, active tab indicators, and the primary CTA.
   - Semantic status colors exist but are muted, small-area only (badges, dots, text) — never large fills: green (active/paid/confirmed), amber (draft/pending), red (overdue/cancelled/failed), violet/sky (info, paused).
5. **Data visualization**: Recharts-style charts (MRR trend, invoiced-vs-collected) in muted grays + the single accent; no rainbow charts.
6. **Responsive**
   - Desktop first (12-col). Collapse to **single-column vertical stacks** on tablet/mobile.
   - Mobile navigation becomes a **hamburger toggle in the thumb zone** (bottom-reachable), field staff stay productive.

## Key Surfaces

1. **Auth** — sign-in / sign-up / reset-password in the calm dark aesthetic; strong password policy messages (min 9 chars, 1 upper, 1 lower, 1 special).
2. **Admin/Staff Dashboard** — the operations centre: active/paused subscription counts, MRR/ARR, invoiced vs collected vs outstanding vs overdue, billing-day preview/entry, chase lists.
3. **Catalog** — products (with variants + price deltas), plans (frequency, availability window, behaviors: auto-close / early close / pause / renew), tax rules, quotation templates.
4. **Customers** — organizations with subscription counts, filters.
5. **Subscriptions** — dense list + detail with the stage machine actions (send-quotation → confirm → activate → close/renew), pause spans, immutable lines with tax, activity history.
6. **Billing** — billing-run preview (dry run) → execute, run history with failed-record reports; invoices (Draft → Confirmed → Paid, cancel exit) with lines, taxes, applied discounts; payments ledger.
7. **Discounts (admin only)** — percent/fixed, product- or subscription-scoped, windows, minimums, usage limits; deactivation (never delete).
8. **Reporting** — month-end summary + collections chase lists (outstanding/overdue).
9. **Users (admin only)** — staff/admin provisioning, deactivation.
10. **Customer portal** — simplified read-only surfaces: own subscriptions and invoices.

## Visual Language (tokens to centralize in Tailwind `theme.extend`)

- **Backgrounds**: page `#1E1E1E`; panels/cards `#252526`; raised/hover `#2D2D30`; hairline borders `#3A3A3D`; null/sunken surfaces (table header rows) `#232326`.
- **Text**: primary `#ECECEA`, secondary `#A6A6A3`, tertiary/labels `#7C7C78`.
- **Accent (single, sparing)**: `#7AA2F7` blue family — active nav tint, focus rings, primary CTA fill, tab underline. Hover `#89ABF8`.
- **Status (muted, small areas)**: success `#7DC98F`, warning `#D9B36A`, danger `#E58B84`, info `#8FB8DE`.
- **Typography**: neutral grotesque sans (Inter/Söhne-class). Scale: 48–60px overview titles (light weight, tracking-tight), 24–36px module headers, 14–18px body/table text, 12px uppercase tabular labels for KPI captions.
- **Shape/depth**: minimal radius (6–10px), flat surfaces separated by hairlines and elevation steps, NOT shadows; subtle 1px borders everywhere instead of glow.
- **Controls**: 60px standard height for buttons/inputs/selects; radius matching panels; focus = accent ring; disabled = 40% opacity.
- **Spacing**: 4px base scale; section macro-gaps 80/96px; card padding 32–40px; control micro-gaps 16–20px.
- **Motion**: purposeful and fast: 150–200ms ease-out; no bouncy animation; skeleton placeholders; hover = background step, not elevation.
- **Grid overlays**: dashboards as explicit 12-col compositions: e.g. KPI band (12-col, 4–3 cards), 8-col chart + 4-col chase list, 12-col billing console.

## Specific Requirements

- Every list view: status badge column (lifecycle/invoice state), sticky header, quick filters, page-size cap 200, always ordered newest/most-relevant first — under 2s feel.
- Invoice detail must show taxes and applied discounts as visible line rows (they are domain truth, not decoration).
- Role gating is visual: admin-only surfaces (discounts, users, tax write) hide or disable for staff; customer portal is a distinct, much calmer, read-mostly skin.
- Destructive tier only for: close subscription, cancel invoice, remove payment, deactivate discount rule — always require a typed/selected reason where the API demands one.
- Currency everywhere (`$1,234.00` style, right-aligned in tables), ISO dates (2026-11-15), subscription numbers as `SUB-2026-000001` monospace references.
- Design tokens must be implementable 1:1 in Tailwind (custom hexes in `theme.extend`, no exotic CSS).
