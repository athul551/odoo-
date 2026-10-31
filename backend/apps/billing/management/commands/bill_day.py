"""
Nightly billing run.

    python manage.py bill_day                 # bill everything due today
    python manage.py bill_day --on 2026-11-15
    python manage.py bill_day --dry-run       # what would be billed, no writes

This is the trigger for ``billing.services.run_billing_day``: the idempotent
batch that the cron sidecar (or any scheduler) calls once a day. It exits
non-zero when records failed, so a scheduler alerts instead of silently
dropping a tenant.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.billing.services import preview_billing_day, run_billing_day


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise CommandError(f"--on must be an ISO date (YYYY-MM-DD), got {value!r}")


class Command(BaseCommand):
    help = "Run the billing day: invoice every due period exactly once."

    def add_arguments(self, parser):
        parser.add_argument("--on", type=iso_date, default=None,
                            help="Business date (YYYY-MM-DD, defaults to today).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would be billed without writing.")

    def handle(self, *args, **options):
        on = options["on"] or date.today()

        if options["dry_run"]:
            preview = preview_billing_day(on=on)
            self.stdout.write(
                f"{preview['invoices']} invoice(s) would be billed for "
                f"{preview['subscriptions']} subscription(s) on {preview['on']} "
                f"({preview['missed_periods']} missed period(s) of ended terms)"
            )
            for item in preview["items"]:
                self.stdout.write(
                    f"  {item['subscription']}  {item['period_start']} → "
                    f"{item['period_end']}  {item['customer']}"
                )
            for problem in preview["problems"]:
                self.stderr.write(
                    f"  ! {problem['subscription']}: {problem['error']}"
                )
            return

        run = run_billing_day(on=on)
        self.stdout.write(
            f"billed {run.billed_count} invoice(s), skipped {run.skipped_count} "
            f"already-billed period(s), {run.failed_count} failure(s) on {on}"
        )
        for failure in run.report.get("failed", []):
            self.stderr.write(
                f"  ! {failure['subscription']}: {failure['error']}"
            )
        if run.failed_count:
            # Non-zero exit so a scheduler alerts; the good invoices are kept.
            raise CommandError(
                f"{run.failed_count} subscription(s) could not be billed — "
                f"see billing run {run.pk}"
            )
