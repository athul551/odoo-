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

## Amendment: completeness and batch isolation (2026-10-31)

The idempotency guarantee above was sound, but completeness was not: candidates were filtered on
`expiry_date__gt=on`, so a period that fell due before a term ended and was never billed could never
be billed again, and the whole batch shared one transaction — a single malformed record (a bad plan
frequency) rolled back every other invoice *and* the run row itself.

Amended decisions:

1. **Candidates are scanned by period, not by expiry.** Any Active subscription whose term started by
   the business date is a candidate, ended or not; the per-period bound `cursor < expiry_date` keeps
   the scan inside the term. The preview reports those periods as `missed_periods` so an operator sees
   revenue waiting on an ended term.
2. **The run row is written before any work, outside the batch transaction.** An attempted run is
   always auditable, even if the process is killed mid-batch.
3. **Each subscription commits in its own savepoint.** A record that raises is collected in
   `report["failed"]` and counted in `failed_count`; the remaining invoices still commit.
4. **Paused periods are dropped, never deferred.** A recorded pause span that overlaps a period
   excludes it permanently (see CONTEXT.md, "Pause Span"), rather than skipping it and back-billing
   it on resume.
5. **A scheduler trigger is part of the design, not deployment trivia.** `manage.py bill_day` runs the
   batch and exits non-zero on failures; `manage.py sweep_subscriptions` closes expired terms on
   `auto_close_on_expiry` plans. Without the sweep, that per-plan switch is dead configuration.

### Known limitation

The scan covers **Active** terms only. A subscription that was closed while a period was still
unbilled is not revisited, because there is no `closed_on` field to bound a post-close scan — billing
past an early close would charge for service that ended. Until that field exists, the operator sees
the gap through `missed_periods` *before* closing the term, and can raise a manual invoice.


