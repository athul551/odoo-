# ADR 0002: Invoice Cancellation is Credit-then-Rebill, not Skip

## Status
Accepted

## Context
The spec lets the team "confirm, cancel, send or print any invoice." Cancelling a confirmed or paid
invoice after money has landed raises a domain question: does the cancelled billing period get
invoiced again, or is the revenue written off?

## Decision
1. An invoice with confirmed status cannot be cancelled while payments remain attached; payments
   must be removed (or refunded externally) first — the API refuses, it doesn't cascade.
2. Cancelling an invoice (draft or confirmed) makes it `status='cancelled'`; it stops being counted
   in spawned-uniqueness (see ADR 0001), so the subscription's period becomes billable again in
   the next billing run.
3. The system therefore never silently skips a period and never double-bills one: at most one
   active invoice exists per period, and every period gets exactly one in the end.

## Consequences
- Revenue reporting must exclude cancelled invoices (aggregate on confirmed/paid only).
- No "credit note" entity exists yet; if real-world refunds are needed later, a credit-note model
  complements rather than replaces this flow.
- Auditability: invoice number sequence is never reused; cancelled numbers stay listed, flagged.
