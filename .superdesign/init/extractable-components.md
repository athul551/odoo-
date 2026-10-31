# Extractable Components — Brightloop Frontend

Everything below exists in code and can be extracted as reusable DraftComponents.

## AppLayout
- Source: `frontend/src/components/layout/AppLayout.jsx`
- Category: layout
- Description: Centered page shell — indigo wordmark header ("Brightloop" | "Subscription Management") over an Outlet
- Extractable props: none yet (fully hardcoded; candidates: `brandName`, `headerNote`)
- Hardcoded: brand text, tagline, all classes

## Button
- Source: `frontend/src/components/ui/Button.jsx`
- Category: basic
- Description: Primary solid-indigo button, spreads native props
- Extractable props: `children`, passthrough button props; no variant prop exists
- Hardcoded: indigo bg/hover, `rounded-lg`, `text-sm font-medium`, padding

## Card
- Source: `frontend/src/components/ui/Card.jsx`
- Category: basic
- Description: White rounded panel with border + soft shadow; only container primitive
- Extractable props: `children`, `className`
- Hardcoded: `rounded-xl`, `border-slate-200`, `p-6`, `shadow-sm`

## DashboardPage (extractable pattern, not extracted yet)
- Source: `frontend/src/pages/DashboardPage.jsx`
- Category: layout
- Description: Page-title block + placeholder roadmap; the shape of future module pages
- Extractable props: `title`, `subtitle`
- Hardcoded: all copy

## Not yet extracted (must be designed new)
Input, Select, Checkbox, Dialog, Table, Tabs, Badge, Avatar, Sidebar, Footer, Breadcrumb — no primitives and no usage exist.
