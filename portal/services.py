"""Purchase-department business logic, kept out of the views so it can be
unit-tested and reused (a scheduled job, an export, a future LPP engine)."""

import math


class EBQError(ValueError):
    """Raised when the EBQ inputs can't produce a meaningful answer."""


def economic_batch_quantity(annual_demand, ordering_cost, holding_cost):
    """Classic EBQ / EOQ — the order size where ordering cost and holding cost
    balance, i.e. the cheapest quantity to buy each time.

        EBQ = sqrt( 2 * D * S / H )

    D = annual usage (kg/yr), S = cost to place one order (₹),
    H = cost to hold 1 kg for a year (₹).

    All three must be positive: at zero holding cost the formula divides by
    zero (and the "optimal" order would be infinite), and at zero demand or
    ordering cost there is nothing to optimise.
    """
    D, S, H = float(annual_demand), float(ordering_cost), float(holding_cost)

    if D <= 0 or S <= 0 or H <= 0:
        raise EBQError("Annual demand, ordering cost and holding cost must all be greater than zero.")

    quantity = math.sqrt(2 * D * S / H)
    return {
        "ebq": quantity,
        "orders_per_year": D / quantity,
        # At the optimum, ordering cost == holding cost, so the combined
        # annual cost collapses to this closed form.
        "total_annual_cost": math.sqrt(2 * D * S * H),
        "inputs": {"annual_demand": D, "ordering_cost": S, "holding_cost": H},
    }
