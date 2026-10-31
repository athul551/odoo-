# ADR 0001: Idempotent Billing Runs (one invoice per subscription-period)

## Status
Accepted

## Context
Billing day generates invoices for hundreds of due subscriptions at once. The spec demands:
"Nothing should be billed twice or skipped." A naive implementation (`for sub in due: create invoice`)
fails when the run partially fails mid-batch and is re-executed (double billing), or when two
operators/schedulers race the same run (duplicate invoices), or when a run is retried after a crash
(skipped or duplicated periods).

## Decision
Each billing run is a recorded, transactional batch job:

1. Every invoice carries an explicit **billing period** (`period_start`, `period_end`) inherited from
   its subscription's plan frequency.
2. A restrained uniqueness constraint, scoped to **non-cancelled** invoices, enforces
   one invoice per `(subscription, period_start)` — enforced by a partial unique index
   (`UNIQUE (subscription_id, period_start) WHERE status != 'cancelled'`).
3. Generated invoice numbers are produced inside the same transaction and are DB-unique.
4. The run iterates due subscriptions with `select_for_update(skip_locked=True)` so concurrent
   runs process disjoint subsets and a crashed run leaves no half-written invoice without its
   period record.
5. Re-running the billing process is always safe: already-billed periods are skipped by the
   uniqueness constraint, never silently dropped — a run report shows billed / skipped-already-billed.

## Consequences
- Cancelled invoices free their period for rebilling automatically (no manual bookkeeping).
- Migrations must create the partial index (Postgres-specific; the stack is Postgres-only by design).
- Adding a normal unique index would make credit-then-rebill (ADR 0002) impossible; the partial
  version is the whole point.
