from django.db import models


class NumberSeries(models.Model):
    """
    Gap-free per-prefix, per-year counters for human-facing document numbers.
    next_number() must be called inside a transaction that also writes the
    document: the row lock (SELECT ... FOR UPDATE) serialises concurrent
    billers, and the unique (year, prefix) index makes races impossible.
    """

    year = models.PositiveIntegerField()
    prefix = models.CharField(max_length=8)
    last = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["year", "prefix"], name="number_series_year_prefix")
        ]

    def __str__(self):
        return f"{self.prefix}-{self.year}: {self.last}"

    @classmethod
    def next_number(cls, prefix: str, year: int, *, digits: int = 6) -> str:
        cls.objects.get_or_create(year=year, prefix=prefix, defaults={"last": 0})
        series = cls.objects.select_for_update().get(year=year, prefix=prefix)
        series.last += 1
        series.save(update_fields=["last"])
        return f"{prefix}-{year}-{series.last:0{digits}d}"
