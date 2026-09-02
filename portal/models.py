from django.db import models


class RawMaterial(models.Model):
    """A raw material tracked by the Purchase department.

    ``on_hand`` mirrors the current stock figure that will eventually come
    straight from the TCS iON stock export; the reorder columns are the
    purchasing policy for that material. The buy decision itself is derived,
    never stored — see ``to_purchase``.
    """

    name = models.CharField(max_length=120, unique=True)
    on_hand = models.DecimalField(max_digits=12, decimal_places=2, help_text="Current stock in kg")
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, help_text="Buy when stock falls to or below this")
    reorder_qty = models.DecimalField(max_digits=12, decimal_places=2, help_text="How much to buy when triggered")
    is_active = models.BooleanField(default=True)
    # Purchasing reads this list in a deliberate order — primary strip stock
    # first, then fasteners, then consumables — which alphabetising would
    # scramble. Lower numbers sort first.
    sort_order = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    @property
    def to_purchase(self):
        """Reorder qty when stock has hit the reorder level, otherwise zero."""
        if self.on_hand <= self.reorder_level:
            return self.reorder_qty
        return 0

    @property
    def needs_purchase(self):
        return self.to_purchase > 0

    @property
    def status(self):
        return "PURCHASE" if self.needs_purchase else "OK"

    def __str__(self):
        return self.name
