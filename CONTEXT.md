# CONTEXT.md — Brightloop Subscription Management

Glossary of domain terms. Implementation details belong in code/ADRs, not here.

## Identity & Access

- **User** — An authentication identity: unique email (**globally unique across all roles**), password (minimum 9 characters — "more than eight" — with at least one uppercase, one lowercase, one special character). Has exactly one **Role**.

## Roles

- **Admin** — Full-system operator. Only role that can create Plans, Taxes, Discount Rules, and other Users. Gestalt owner of the system's configuration.
- **Staff** — Internal operator for day-to-day work: customers, quotations, subscriptions, invoices, payments. Cannot create users, plans, taxes, or discount rules.
- **Customer User** — End-customer role. Sees only the data of the **Customer** account they belong to (their subscriptions and invoices), via the portal.

## Customer

## Customer

- **Customer** — The billable organization (from the small shop to the yearly-contract company). Holds address, payment terms, and tax data. **One Customer has many Customer Users, and each Customer has many Subscriptions**; subscriptions, quotations, invoices, and payments all belong to a Customer. A Customer User logs in on behalf of exactly one Customer.
- **Account** — Reserved for the *customer-facing* name of "Customer + its portal" in sign-up copy. One Customer has one portal Account.

## Catalog

- **Product** — A sellable offering. Attributes per spec: name, type, sales price, cost price, notes. Can have **Product Variants** (e.g. by brand), where a variant defines a price delta (e.g. "Odoo brand" → +560).
- **Product Variant** — A purchasable configuration of a Product, expressed as an attribute/value pair (e.g. attribute `brand`, value `Odoo`) with a **Price Delta**. Effective price = Product sales price + delta; an effective price may never go negative.
- **Plan** — A recurring billable offering **belonging to a Product** (the product is what is sold; the plan defines how/when it recurs): price, billing frequency (daily / weekly / monthly / yearly), minimum quantity, and an **Availability Window**. Decides **Plan Behaviors**: auto-close at term end, early close, pause, renew — per plan.
- **Availability Window** — Date range during which a plan may be newly selected for a subscription. It governs selection only: existing subscriptions on a window that has closed continue to bill normally.
- **Plan Behaviors** — Per-plan truth table of: `auto_close_on_expiry`, `allow_early_close`, `allow_pause`, `allow_renew`.
- **Tax Rule** — Admin-defined rule used to compute tax amounts automatically on invoice lines.

## Sales / Lifecycle

- **Quotation Template** — Reusable blueprint of plan and product lines with a validity window (N days). Starting-point for a Subscription.
- **Subscription** — The central contract record, with unique **number**. Belongs to a Customer, references a Plan, has start date, expiry date, and payment terms. Progresses through exactly this **Stage** sequence: `Draft → Quotation → Confirmed → Active → Closed`.
- **Stage** — The Subscription lifecycle enum above. Transitions are linear and never backward (sole exception: `renew` re-activates a closed subscription). Legal moves: `Draft → Quotation`, `Quotation → Confirmed`, `Confirmed → Active`, and `Active → Closed`; Draft/Quotation/Confirmed may also go straight to Closed (abandoned sale). Every other move is an `InvalidTransition`. `pause`/`resume` are a flag on an Active subscription, not stages; a paused subscription is skipped by Billing Runs.
- **Validity** — How long a Quotation stays open for the customer to accept, set by the originating **Quotation Template**'s validity days.
- **Renew** — Only allowed when the plan permits it: extends an Active subscription by one full period, or re-activates a Closed one whose expiry has passed (a new term, priced at current plan price). Renew does not resurrect a still-running Active term early.
- **Subscription Number** — Immutable human-facing identifier assigned from a per-year counter at subscription creation (e.g. `SUB-2026-000001`). Never reused, even if the subscription is later closed.
- **Subscription Line** — Row of a subscription offering: Product/variant, quantity, unit price, taxes, amount. Unit price snapshots the product/variant price at line creation; later product re-pricing never rewrites history. A (product, variant) pair may appear at most once per subscription.
- **Tax Rule** — Admin-defined rule used to compute tax amounts automatically on invoice lines: name, percentage rate, active flag. A line's tax amount = amount × rate/100 (tax shown on top of the line amount).
- **Payment Term** — How long after invoicing the customer pays.

## Billing

- **Billing Run** — The batch process executed on each billing day: for every subscription due in that period, generate exactly one **Invoice** — idempotent: a given (Subscription, billing period) can never produce a second invoice, and no due period may be skipped silently.
- **Billing Period** — The recurring interval (per the Plan frequency) for which a subscription billable window is computed. The **due** subscription is one whose next period start edge has passed.
- **Invoice** — Issued from a Subscription: customer details, product lines, taxes, totals prefilled. Lifespan: `Draft → Confirmed → Paid`, with **Cancel** as an exit. Draft invoices may be edited; Confirmed ones may not. **Cancelling a Confirmed or Paid invoice requires first removing its payments**; the affected billing period then falls due again in a later Billing Run — a period is never silently skipped, and never double-billed (credit-then-rebill).
- **Invoice Line** — Exact copy of the Subscription Line at issuance time (price snapshot independent of later product/plan changes).

## Pricing

- **Discount Rule** — Admin-only. Fixed amount or percentage; may require a minimum purchase amount or quantity; date-bounded (`applies_from`/`applies_until`); limited number of uses. **Scope**: product-scoped (its product list, empty = any product) or subscription-scoped (its subscription list, empty = any).
- **Discount Application** — A rule realized on a specific invoice, recorded as an **Applied Discount** row, chosen automatically by the Billing Run. A product-scoped rule reduces matching lines (tax follows the reduced amount); a subscription-scoped rule reduces the whole line subtotal, allocated pro-rata across lines. Applied only while the rule is active, inside its window, above its minimums, and within its remaining uses.
- **One Discount per Line** — A line receives at most one product-scoped discount: the eligible rule with the largest benefit (ties by creation order). Multiple product discounts stacking on one line is refused by design.
- **One Order Discount per Invoice** — A subscription-scoped rule applies at most once per invoice, computed on the subtotal *after* line discounts. It may coexist with line discounts but not with a second subscription-scoped rule.
- **Applied Discount** — Row linking (Invoice, Rule) — plus its line, for product scope. Counts as one **use** per invoice (not per line).
- **Discount Usage** — Times a rule has been used = invoices carrying an Applied Discount on a non-cancelled invoice. Cancelling an invoice returns the use; an expired or exhausted rule simply stops being chosen — it is never revoked from invoices already issued.
- **Payment** — Money received: method, amount, date, note, matched to exactly one Invoice. An Invoice's status derives from its confirmed amount received.

## Statuses (Invoice)

- **Outstanding** — Confirmed, not yet fully paid; overdue once past its due date.
- **Overdue** — Outstanding past the payment-term deadline.
