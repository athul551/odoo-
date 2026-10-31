# ADR 0003: Emails Are Globally Unique Across All Roles

## Status
Accepted

## Context
Users span three roles (admin, staff, customer). "Each email can belong to only one account."
If emails were unique only per role-world, the same email could be both a staff identity and a
customer identity, causing ambiguous JWT claims, confusing password-reset letters, and a
portability trap when a person changes role.

## Decision
One `users` table, one email column, one global unique constraint. A user's email identifies them
regardless of role; reassigning someone (e.g. a shop employee becomes staff) is an explicit admin
action on the row — email stays unique throughout.

## Consequences
- Password reset always resolves to exactly one user — no role-selection dance.
- JWT claims carry the single user id + role; no per-role namespaces to keep coherent.
- Admin and staff emails coexist in the same namespace as customer emails; uniqueness violations
  surface at signup instead of silently as confusing logins.
