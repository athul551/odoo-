"""Calendar-safe billing period arithmetic (no external deps).

Rule: a period is a half-open interval [start, end). Month and year steps
clamp the day-of-month to the last valid day of the target month, so a
subscription anchored on Jan 31 bills Feb 28 (or Feb 29 in a leap year),
then Mar 31 — it never silently lands on a non-existent date and never
drifts forward over time.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta


def add_months(d: date, months: int) -> date:
    total = (d.year * 12 + (d.month - 1)) + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


class Frequency:
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    CHOICES = [(DAILY, "Daily"), (WEEKLY, "Weekly"), (MONTHLY, "Monthly"), (YEARLY, "Yearly")]


def advance(start: date, frequency: str, periods: int = 1) -> date:
    """Return the start of the period `periods` steps after `start`."""
    if periods < 0:
        raise ValueError("periods must be non-negative")
    if frequency == Frequency.DAILY:
        return start + timedelta(days=periods)
    if frequency == Frequency.WEEKLY:
        return start + timedelta(weeks=periods)
    if frequency == Frequency.MONTHLY:
        return add_months(start, periods)
    if frequency == Frequency.YEARLY:
        return add_months(start, 12 * periods)
    raise ValueError(f"unknown billing frequency: {frequency}")


def period_bounds(start: date, frequency: str) -> tuple[date, date]:
    """Half-open bounds [start, end) of the first period beginning at `start`."""
    return start, advance(start, frequency, 1)
