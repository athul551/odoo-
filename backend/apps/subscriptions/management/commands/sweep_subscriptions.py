"""
Term-expiry sweep.

    python manage.py sweep_subscriptions
    python manage.py sweep_subscriptions --on 2026-11-01

Closes the Active subscriptions whose plan has ``auto_close_on_expiry`` set and
whose term has ended. Without a trigger the per-plan switch was dead
configuration, and expired Actives piled up until MRR was fiction.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.subscriptions.services import auto_close_expired


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise CommandError(f"--on must be an ISO date (YYYY-MM-DD), got {value!r}")


class Command(BaseCommand):
    help = "Close Active subscriptions that reached expiry on auto-close plans."

    def add_arguments(self, parser):
        parser.add_argument("--on", type=iso_date, default=None,
                            help="Business date (YYYY-MM-DD, defaults to today).")

    def handle(self, *args, **options):
        on = options["on"] or date.today()
        closed = auto_close_expired(on=on)
        self.stdout.write(f"{len(closed)} subscription(s) auto-closed on {on}")
        for subscription in closed:
            self.stdout.write(
                f"  {subscription.number}  {subscription.customer.name}"
            )
