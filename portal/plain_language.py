"""Plain-English naming layer for the dashboards and the Seven Controls.

WHY THIS FILE EXISTS
--------------------
The tile labels written into the computation modules are deliberately
technical: they name the exact sheet column and the exact test applied, so a
CA or an auditor can trace any number back to its source. That is the right
wording for that reader and it is NOT changed here.

A stakeholder reading the same board does not want "Rows where To be ordered
Qty > 0". They want "32 materials are short of what production needs. Each
one needs a purchase order raised."

So this module is a pure *presentation* dictionary, applied at the API
boundary. Nothing in it computes, filters, sums or reorders anything:

  * every computation module is untouched — the numbers, the row lists and
    the verdict logic are byte-for-byte what they were;
  * the technical ``label`` / ``sub`` are still sent on every tile, so the
    "Technical" view keeps the audit wording;
  * the plain wording is added alongside as ``plain_label`` / ``plain_sub``.

If a board, tile or column has no entry here it simply falls through to its
technical wording. Adding a tile to a computation module can therefore never
break this file, and a typo here can never change a number.

WORDING RULES followed throughout (from the stakeholder brief):
  * no column letters, no sheet jargon, no internal vocabulary — "cover"
    becomes "days of stock left", "lead time" becomes "how long the supplier
    takes", "buffer" becomes "the minimum we keep on purpose", "MTS/MTO"
    become "kept in stock" / "bought only when ordered";
  * say what the number means AND what it implies — money about to be spent
    is named as such, and so is money already spent;
  * never dress up a limitation. "Cannot be judged" stays "cannot be
    judged", never "fine".
"""

import re

# ── Templating ──────────────────────────────────────────────────────────────
# A plain sub may be a plain string, a format template, or a callable taking
# the tile dict. Templates may use:
#     {value}  the tile's displayed value (already formatted, e.g. "₹10.77 Cr")
#     {rows}   the drill-through row count behind the tile
#     {sub}    the original technical sub, for the rare tile whose detail is
#              genuinely worth keeping verbatim (a vendor name, an item code)


# Counts are live, so "1 materials have..." is a real possibility on any tile
# whose number happens to land on one today. Rather than write every sentence
# twice, the formatted text gets one agreement pass. A phrase this does not
# recognise is simply left alone — it can never produce a wrong number, only
# slightly stiff English.

_NOUNS = ("materials", "rows", "order lines", "accounts codes", "codes",
          "items", "groups", "lines", "rules", "materials groups")
_VERBS = {
    "are": "is", "have": "has", "carry": "carries", "reach": "reaches",
    "show": "shows", "hold": "holds", "land": "lands", "look": "looks",
    "share": "shares", "start": "starts", "sit": "sits", "need": "needs",
    "come": "comes", "drop": "drops", "trip": "trips", "raise": "raises",
    "count": "counts", "do": "does",
}
_ONE = re.compile(
    r"\b1 (?P<noun>" + "|".join(_NOUNS) + r")\b(?P<gap> )?(?P<verb>[a-z]+)?"
)


# Once the subject is singular, the rest of the sentence has to follow it —
# "1 row has no accounts code, so they cannot be matched" is worse than the
# plural it replaced. These only run when a singularisation actually happened,
# so a genuinely plural sentence is never touched.
_PRONOUNS = [
    (re.compile(r"\bThese are\b"), "This is"),
    (re.compile(r"\bthese are\b"), "this is"),
    (re.compile(r"\bThese\b"), "This"),
    (re.compile(r"\bthese\b"), "this"),
    (re.compile(r"\bthey\b"), "it"),
    (re.compile(r"\bthem\b"), "it"),
    (re.compile(r"\btheir\b"), "its"),
]


def _agree(text):
    hit = False

    def sub(m):
        nonlocal hit
        hit = True
        out = "1 " + m.group("noun")[:-1]
        verb = m.group("verb")
        if verb is None:
            return out
        return out + " " + _VERBS.get(verb, verb)

    text = _ONE.sub(sub, text)
    if hit:
        for pat, to in _PRONOUNS:
            text = pat.sub(to, text)
    return text


def _fmt(spec, tile):
    if callable(spec):
        return _agree(spec(tile))
    try:
        return _agree(spec.format(
            value=tile.get("value"),
            rows=tile.get("row_count", 0),
            sub=tile.get("sub", ""),
        ))
    except (KeyError, IndexError, ValueError):
        # A bad template must degrade to the technical wording, never 500.
        return tile.get("sub", "")


# ── Tile wording, board by board ────────────────────────────────────────────
# (plain label, plain sub)

TILES = {
    # ─── Dashboard 1 — what to buy today ──────────────────────────────────
    "d1": {
        "items_needing_order": (
            "Material To Be Purchased",
            "{value} materials are short of what production needs. Each one needs a "
            "purchase order raised.",
        ),
        "order_value_at_stake": (
            "Money Needed To Buy Material",
            "Buying everything on the list above would cost about {value}. This is money "
            "you are about to spend, not money lost.",
        ),
        "below_red_level": (
            "Stock Below Safety Level (Red Level)",
            "{value} materials have dropped below the minimum level we ourselves set as "
            "the point to reorder — this includes any items at zero stock.",
        ),
        "no_delivery_date": (
            "Delivery Date Not Known",
            "For all {value} materials above, nobody has recorded when the material will "
            "arrive — so we cannot tell production when to expect it.",
        ),
    },

    # ─── Dashboard 2 — will we run out ────────────────────────────────────
    "d2": {
        "cover_short": (
            "Stock Will Finish Before Material Comes",
            "{value} materials will finish before a fresh delivery can reach us. Even if "
            "we order today, production still stops.",
        ),
        "severely_exposed": (
            "Too Late Even If Ordered Today",
            "{value} materials have less than half the stock needed to last until a "
            "delivery could arrive. Look at a substitute, a part shipment, or moving the "
            "production date.",
        ),
        "value_exposed": (
            "Money Needed To Cover Shortage",
            "{value} is what it would cost to buy the shortfall on the materials above.",
        ),
        "lines_measurable": (
            "Material We Can Check (Rest No Data Available)",
            "This question can only be answered for {value} materials. The rest have no "
            "supplier delivery time or no daily usage recorded, so this board stays "
            "silent about them — that is not the same as saying they are safe.",
        ),
    },

    # ─── Dashboard 3 — traffic light ──────────────────────────────────────
    "d3": {
        "red": (
            "Red — Buy Immediately",
            "{value} materials have fallen below the minimum level we set for them. These "
            "should be ordered now.",
        ),
        "yellow": (
            "Yellow — Watch, Buy Soon",
            "{value} materials are in the warning zone: not critical yet, but heading "
            "that way.",
        ),
        "green": (
            "Green — Stock Is Enough",
            "{value} materials are sitting at a comfortable stock level. Nothing to do.",
        ),
        "blue": (
            "Blue — Extra Stock, Money Blocked",
            "{value} materials hold more stock than the plan asks for. That is extra cash "
            "sitting in the store, not extra safety.",
        ),
        "active_lines": (
            "Material Having Fixed Level",
            "Only {value} materials have stock levels defined, so the traffic light can "
            "only judge these.",
        ),
        "suppressed": (
            "Hidden Red Items — Check Manually",
            "{value} materials are genuinely below the minimum, but a rule inside the "
            "sheet leaves them out of its own red count. We show them here so they are "
            "not missed.",
        ),
    },

    # ─── Dashboard 4 — what our stock is worth ────────────────────────────
    "d4": {
        "total_value": (
            "Total Value Of Stock In Store",
            "The material lying in the store today is worth about {value}, using our own "
            "manual price estimate.",
        ),
        "holding_stock": (
            "Material Actually Lying In Store",
            "{value} materials actually have a balance in the store. The rest show nil.",
        ),
        "zero_stock": (
            "Material Showing Nil Stock",
            "{value} materials show no stock at all. Some bins are genuinely empty, and "
            "some are only a failed lookup — so this number should not be read as fact "
            "yet.",
        ),
        "largest_group": (
            "Highest Value Item Group",
            "Most of the money sits in one group: {value}. ({sub})",
        ),
        "no_rate": (
            "Rate Not Entered (Value Not Counted)",
            "{value} materials have no price recorded, so their stock counts as ₹0 in "
            "every money figure in this portal. The real total is higher than what we "
            "show.",
        ),
        "group_breakdown": (
            "Group-Wise Value Split",
            "A split across {value} material groups: how many materials, how much weight "
            "and how much money sits in each.",
        ),
        "dead_stock_capital": (
            "Money Sleeping In Old Stock",
            "{value} is tied up in materials that are barely moving or not moving "
            "at all. This money is already spent and sitting in the store.",
        ),
    },

    # ─── Dashboard 5 — stock that isn't moving ────────────────────────────
    "d5": {
        "non_moving": (
            "Material Not Used At All",
            "{value} materials have shown no movement whatsoever.",
        ),
        "slow_moving": (
            "Material Used Very Slowly",
            "{value} materials are moving, but slowly.",
        ),
        "fast_medium": (
            "Material In Regular Use",
            "{value} materials are genuinely in regular use — fast or medium-fast moving. "
            "This is the part of the material list that is actually working.",
        ),
        "dead_holding_stock": (
            "Idle Material Lying In Store",
            "{value} materials are slow-moving or not moving at all, and still have "
            "material lying in the store.",
        ),
    },

    # ─── Dashboard 6 — cash held as safety stock ──────────────────────────
    "d6": {
        "buffer_committed": (
            "Money Needed For Minimum Stock",
            "Our own policy of always keeping a minimum quantity in the store commits "
            "{value}, before a single purchase order is raised.",
        ),
        "mts_lines": (
            "Material Kept Ready In Advance (MTS)",
            "{value} materials are stocked in advance, because production expects them to "
            "be on the shelf.",
        ),
        "mto_lines": (
            "Material Bought Only Against Order (MTO)",
            "{value} materials are bought only when a customer order needs them, so no "
            "safety stock is expected for these.",
        ),
        "mts_no_buffer": (
            "Minimum Level Not Fixed",
            "{value} materials are supposed to be kept in stock, but no minimum quantity "
            "has ever been set for them. That is a gap in the policy, not in the store.",
        ),
        "stock_above_green": (
            "Extra Stock Above Minimum Level",
            "{value} of material and money sits above the green level we ourselves set, "
            "across {sub}.",
        ),
    },

    # ─── Dashboard 7 — how long our stock will last ───────────────────────
    "d7": {
        "band_0_15_total": (
            "Stock For Less Than 15 Days",
            "{value} materials look like they have under 15 days of stock left. Do not "
            "quote this figure on its own — read the two lines below first.",
        ),
        "genuinely_short": (
            "Really Short — Daily Use Material",
            "{value} materials are truly running low: under 15 days of stock and being "
            "consumed every day.",
        ),
        "not_measurable": (
            "Cannot Be Judged — No Usage Data",
            "{value} materials land in the lowest band only because no daily usage is "
            "recorded against them, not because they are short. Nothing is necessarily "
            "wrong with these.",
        ),
        "band_30": (
            "Stock For 15 To 30 Days",
            "{value} materials have between 15 and 30 days of stock left.",
        ),
        "band_60": (
            "Stock For 1 To 2 Months",
            "{value} materials have between 30 and 60 days of stock left.",
        ),
        "band_120": (
            "Stock For 2 To 4 Months",
            "{value} materials have between 60 and 120 days of stock left.",
        ),
        "over_120": (
            "Stock For More Than 4 Months",
            "{value} materials hold over four months of stock. Worth asking whether we "
            "need this much.",
        ),
    },

    # ─── Dashboard 8 — can we trust this sheet ────────────────────────────
    "d8": {
        "trust_score": (
            "Sheet Reliability Score",
            "{value} of rows are complete enough to be relied on — they carry a material "
            "code, an accounts code, a price, and real stock movement. Every other row "
            "has at least one of those missing.",
        ),
        "silent_zero": (
            "Rows With No Numbers At All",
            "{value} rows show zero everywhere: no opening stock, nothing received, "
            "nothing issued, no balance. Usually that means the lookup failed, not that "
            "the bin is empty.",
        ),
        "no_rm_code": (
            "Missing Material Code",
            "{value} rows have no material code, so they cannot be matched against any "
            "other system.",
        ),
        "no_tally_code": (
            "Missing Accounts Code",
            "{value} rows have no accounts code, so they cannot be tied back to the "
            "books.",
        ),
        "no_rate": (
            "Missing Price",
            "{value} rows have no price, so they quietly count as ₹0 in every money "
            "figure in this portal.",
        ),
        "no_delivery_date": (
            "Missing Arrival Date",
            "{value} rows have no expected arrival date filled in. Nobody is recording "
            "when material is due to reach us.",
        ),
        "no_mps": (
            "No Sales Demand Behind It",
            "{value} rows have no sales demand recorded against them, so any purchase on "
            "these is a store top-up rather than a customer order.",
        ),
    },

    # ─── Dashboard 9 — where the sheet contradicts itself ─────────────────
    "d9": {
        "two_order_qty_disagree": (
            "Two Different Order Quantities",
            "On {value} materials the sheet gives two different answers for how much to "
            "buy. Somebody has to decide which one is right.",
        ),
        "broken_ltc": (
            "Broken Usage Calculation",
            "On {value} materials one usage figure reads zero while the daily usage is "
            "above zero. The calculation behind it is not working.",
        ),
        "high_but_short": (
            "Marked Overstocked And Also Short",
            "{value} materials are labelled as carrying high stock and, on the very same "
            "row, as having under 15 days left. Both cannot be true.",
        ),
        "ordering_dead": (
            "Ordering Something That Isn't Moving",
            "{value} materials are being ordered even though the sheet says they are slow "
            "or not moving at all.",
        ),
        "ordering_no_demand": (
            "Ordering With No Customer Demand",
            "{value} materials are being ordered with no sales demand recorded behind "
            "them.",
        ),
        "rag_suppressed": (
            "Red Alerts The Sheet Hides",
            "{value} materials are genuinely below the minimum level, but a rule inside "
            "the sheet leaves them out of its own red count.",
        ),
    },

    # ─── Control 1 — have we already ordered it ───────────────────────────
    "c1": {
        "feed_status": (
            "Purchase Order Data",
            "{value} — we are reading the live purchase order list and matching it to each "
            "material by its code, falling back to the material name where the code is "
            "missing.",
        ),
        "requirement_population": (
            "Materials Being Checked",
            "{value} materials are asking to be bought. Every one of them is checked "
            "against the orders already placed.",
        ),
        "not_on_order": (
            "Nobody Has Ordered It",
            "{value} materials are needed and nothing at all has been ordered for them. "
            "Raise the purchase order.",
        ),
        "partly_covered": (
            "Ordered, But Not Enough",
            "{value} materials have an order, but it does not cover the full quantity "
            "needed. The balance still has to be ordered.",
        ),
        "already_covered": (
            "Already Fully Ordered",
            "{value} materials are already covered by an order that has not yet arrived. "
            "Do not order these again.",
        ),
        "over_ordered": (
            "Ordered More Than Needed",
            "{value} materials have more on order than we actually need. There may be a "
            "duplicate purchase order behind this.",
        ),
        "overdue_cover": (
            "Ordered But The Supplier Is Late",
            "{value} materials are on order, but the supplier has already missed the date "
            "they promised. This is the chase list — it does not mean the ordering was "
            "wrong.",
        ),
        "unverifiable": (
            "Cannot Be Checked",
            "{value} materials have no usable code, so they cannot be matched to any "
            "order. The code has to be fixed first.",
        ),
        "value_reconciliation": (
            "The Figures Balance",
            "The groups above add up to {value} — exactly the total we started with, "
            "which proves nothing has been double-counted or quietly dropped.",
        ),
        "shared_codes": (
            "Same Code On Several Rows",
            "{value} rows share a code with another row. The quantity on order is divided "
            "between them by share, never counted twice — otherwise one order would look "
            "like it covered two separate needs.",
        ),
        "notes": (
            "Things To Be Aware Of",
            "Points that limit what this board can prove. Worth reading before you rely "
            "on the numbers above.",
        ),
    },

    # ─── Control 2 — did anyone actually order it ─────────────────────────
    "c2": {
        "register_status": (
            "Waiting-Time Record",
            lambda t: (
                "We keep our own record of when each material first started asking to be "
                "bought, because no other system records it — "
                f"{t.get('value')} so far. "
                + (
                    "The record is still new, so no waiting time below can be longer than "
                    "the record itself. These become fully meaningful from the second "
                    "week onward."
                    if "WARNING" in (t.get("sub") or "")
                    else "The record is now old enough for the waiting times below to be "
                         "meaningful."
                )
            ),
        ),
        "requirement_population": (
            "Materials Needing A Purchase Order",
            "{value} materials are asking to be bought. Each is checked for whether an "
            "order actually exists behind it.",
        ),
        "not_ordered": (
            "Still Not Ordered",
            "{value} materials are needed and no purchase order exists for them yet.",
        ),
        "new_in_queue": (
            "Just Came Up — Normal",
            "{value} materials started asking within the last two days. That is normal "
            "working time; no action needed.",
        ),
        "unactioned": (
            "Waiting Too Long",
            "{value} materials have been waiting three to seven days with no order "
            "raised. The buyer should either order them or write down why not.",
        ),
        "overdue_action": (
            "Badly Overdue",
            "{value} materials have been waiting more than a week and still nobody has "
            "ordered them. This needs to go up the line.",
        ),
        "critical_time_lost": (
            "Too Late To Recover",
            "{value} materials have been waiting longer than the supplier takes to "
            "deliver. Running out is now certain, not a risk.",
        ),
        "ordered_committed": (
            "Ordered, With A Date",
            "{value} materials have a purchase order and the supplier has given a date. "
            "This is exactly what should be filled into the arrival-date column.",
        ),
        "ordered_no_commitment": (
            "Ordered, No Date Given",
            "{value} materials have an order, but the supplier has not committed to any "
            "date. Chase them for one.",
        ),
        "part_ordered": (
            "Only Part Ordered",
            "{value} materials have an order for less than the quantity needed. The "
            "remaining quantity is still unattended.",
        ),
        "reconciliation": (
            "The Figures Balance",
            "Ordered plus not-ordered equals the total exactly ({value}) — nothing has "
            "been counted twice or lost.",
        ),
        "notes": (
            "Things To Be Aware Of",
            "Points that limit what this board can prove. Worth reading before you rely "
            "on the numbers above.",
        ),
    },

    # ─── Control 3 — are we buying what we already have too much of ───────
    "c3": {
        "requirement_population": (
            "Materials Being Checked",
            "{value} materials are asking to be bought. Each is checked against what we "
            "already hold in the store.",
        ),
        "flagged_union": (
            "Question These Before Ordering",
            "{value} of the materials we are about to buy are either not selling or "
            "already overstocked. Somebody should record a reason before these orders go "
            "out.",
        ),
        "non_slow_moving": (
            "Not Selling",
            "{value} of the materials on the buy list are marked as slow-moving or not "
            "moving at all.",
        ),
        "high_inventory": (
            "Already Overstocked",
            "{value} of the materials on the buy list already carry more than twice the "
            "stock level we plan for.",
        ),
        "double_flag": (
            "Both Problems At Once",
            "{value} materials are not moving AND already overstocked, and we are still "
            "about to buy more. These should be escalated, not merely questioned.",
        ),
        "no_customer_pull": (
            "No Customer Order Behind It",
            "{value} materials are being bought to top up the store, not against a "
            "customer order. That is allowed — it just should not be invisible.",
        ),
        "above_buffer": (
            "Already Above The Minimum",
            "{value} materials already hold more than the minimum quantity our policy "
            "asks for.",
        ),
        "clear": (
            "Fine To Order",
            "{value} materials on the buy list raise none of the concerns above.",
        ),
        "notes": (
            "Things To Be Aware Of",
            "Points that limit what this board can prove. Worth reading before you rely "
            "on the numbers above.",
        ),
    },

    # ─── Control 4 — will it arrive before we run out ─────────────────────
    "c4": {
        "lines_measurable": (
            "Materials We Can Judge",
            "This question can only be answered for {value} materials. The others have no "
            "supplier delivery time or no daily usage recorded.",
        ),
        "not_assessable": (
            "Cannot Be Judged",
            "{value} materials are missing either the supplier's delivery time or their "
            "daily usage, so this board says nothing about them. That is not the same as "
            "saying they are safe.",
        ),
        "cover_short": (
            "Will Run Out First",
            "{value} materials will finish before a delivery can reach us.",
        ),
        "severely_exposed": (
            "Ordering Won't Save These",
            "{value} materials have less than half the stock needed to last until "
            "delivery. Look at a substitute, a part shipment, or moving the production "
            "date.",
        ),
        "already_out": (
            "Already Empty",
            "{value} materials are at zero stock and still being consumed. This needs an "
            "emergency response today.",
        ),
        "value_exposed": (
            "Cost To Cover These",
            "{value} is the cost of buying what is short on the materials above.",
        ),
        "cover_short_no_requirement": (
            "Short, And Nobody Has Noticed",
            "{value} materials will run out before delivery and no purchase order has "
            "even been asked for. These are the most dangerous lines on this board.",
        ),
        "covered": (
            "Enough Time",
            "{value} materials have enough stock to last until a delivery arrives.",
        ),
        "po_enhancement": (
            "Supplier's Promised Date vs Run-Out Date",
            "Not available yet. Comparing the date the supplier promised against the day "
            "we actually run out needs a data feed we do not have.",
        ),
        "worst_gap": (
            "Worst Case",
            "The worst material runs out {value} before a delivery could reach us "
            "({sub}).",
        ),
        "notes": (
            "Things To Be Aware Of",
            "Points that limit what this board can prove. Worth reading before you rely "
            "on the numbers above.",
        ),
    },

    # ─── Control 5 — we paid in advance, did the material come ────────────
    "c5": {
        "feed_status": (
            "What We Can And Cannot See",
            "{value}. We can see which orders were placed on advance-payment terms, so "
            "the risk can be sized — but there is no accounts ledger connected here, so "
            "we cannot confirm that money actually left the bank. Every figure below is "
            "money at risk, never confirmed loss.",
        ),
        "advance_population": (
            "Orders On Advance Terms",
            "{value} order lines were placed on terms that require paying the supplier "
            "before delivery.",
        ),
        "exposure_at_risk": (
            "Money At Risk",
            "{value} was committed up front across {rows} order lines where nothing has "
            "been received and the delivery time has already passed.",
        ),
        "overdue_nothing": (
            "Paid, Nothing Received",
            "{value} order lines are past their delivery time with nothing received at "
            "all. Chase the supplier.",
        ),
        "recovery_risk": (
            "Time To Get The Money Back",
            "{value} order lines are more than twice past their delivery time with "
            "nothing received. These need a formal recovery, not a phone call.",
        ),
        "advance_on_dead": (
            "Paid Up Front For Idle Material",
            "{value} order lines committed money in advance for material the sheet says "
            "is not moving.",
        ),
        "part_received": (
            "Partly Delivered",
            "{value} order lines have received some of the material. The advance is partly "
            "justified — track the balance.",
        ),
        "within_lead": (
            "Still Within Time",
            "{value} order lines are still inside the agreed delivery time. Nothing is "
            "wrong with these yet.",
        ),
        "worst_vendor": (
            "Largest Single Supplier Risk",
            "{value} sits with one supplier ({sub}).",
        ),
        "not_checkable": (
            "What We Cannot Check",
            "Two situations cannot be seen from here: an advance paid with no purchase "
            "order behind it, and a supplier who owes us money while we also owe them. "
            "Both need the accounts ledger. Reported as unknown, never as zero.",
        ),
        "notes": (
            "Things To Be Aware Of",
            "Points that limit what this board can prove. The first one matters most: "
            "advance TERMS are not the same as advance PAID.",
        ),
    },

    # ─── Control 6 — is this a real item in our books ──────────────────────
    "c6": {
        "join_readiness": (
            "Codes Fit To Match",
            "{value} of rows carry a usable, non-duplicate code — good enough to be "
            "matched against another system. The rest cannot be matched reliably.",
        ),
        "no_rm_code": (
            "No Material Code",
            "{value} rows have no material code at all. Nothing can be matched to these.",
        ),
        "no_tally_code": (
            "No Accounts Code",
            "{value} rows have no accounts code, so they cannot be tied back to the "
            "books.",
        ),
        "placeholder_code": (
            "“Code Required” Typed In",
            "{value} rows have the words “Item Code Required” sitting in the box "
            "that is supposed to hold the code.",
        ),
        "duplicate_mapping": (
            "Same Code Used Twice",
            "{value} accounts codes are shared across {rows} rows. When one code stands "
            "for several materials, quantity checks stop working.",
        ),
        "distinct_real_codes": (
            "Genuinely Different Codes",
            "There are only {value} truly distinct codes across all the rows. The gap "
            "between that and the row count is itself the finding.",
        ),
        "no_group": (
            "No Material Group",
            "{value} rows have no material group recorded against them.",
        ),
        "not_yet_checkable": (
            "What We Cannot Check Yet",
            "Four checks need the official item list from the other system: whether the "
            "code exists there, whether it is still active, and whether the unit and the "
            "group match. Until then they are reported as unknown, never as a pass.",
        ),
        "notes": (
            "Things To Be Aware Of",
            "Points that limit what this board can prove. Worth reading before you rely "
            "on the numbers above.",
        ),
    },

    # ─── Control 7 — is that zero real ────────────────────────────────────
    "c7": {
        "confirmed_pct": (
            "Rows We Can Believe",
            "{value} of rows show real numbers. The rest are blank in every stock column, "
            "and until those can be confirmed, every other board is partly working on "
            "unverified data.",
        ),
        "quad_zero": (
            "Blank In Every Stock Column",
            "{value} rows show zero opening stock, zero received, zero issued and zero "
            "balance — all four at once. Real materials rarely look like this; a failed "
            "lookup does.",
        ),
        "unconfirmed_resolvable": (
            "Fixable By A Data Feed",
            "{value} of those rows do carry a proper accounts code, so a stock report from "
            "the other system will settle whether they are genuinely empty.",
        ),
        "unresolvable_master_data": (
            "Cannot Be Fixed By Data",
            "{value} rows have no usable code, so no data feed can ever settle them. The "
            "code has to be corrected first.",
        ),
        "quad_zero_with_requirement": (
            "About To Buy Something We May Already Have",
            "{value} materials show nothing in stock and are on the buy list. If the zero "
            "is wrong, we are about to buy material that is already sitting in the store. "
            "Highest priority on this board.",
        ),
        "genuine_run_down": (
            "Genuinely Used Up",
            "{value} materials show a nil balance but real movement during the period. "
            "These are real events, not lookup failures.",
        ),
        "notes": (
            "Things To Be Aware Of",
            "Points that limit what this board can prove. Worth reading before you rely "
            "on the numbers above.",
        ),
    },
}


# ── Drill-through column headings ───────────────────────────────────────────
# Keyed on the column's stable key, so a column can be reused on any board and
# still read the same way everywhere.

COLUMNS = {
    "sr_no":               "Row",
    "rm_code":             "Material Code",
    "tally_code":          "Accounts Code",
    "rm_specification":    "Material",
    "item_code":           "Item Code",
    "item_description":    "Material",
    "group":               "Material Group",
    "category":            "Movement",
    "inventory_type":      "Stock Policy",
    "current_stock_kg":    "In Store (kg)",
    "current_stock_days":  "Days Of Stock Left",
    "lead_time_days":      "Supplier Takes (days)",
    "lead_days":           "Supplier Takes (days)",
    "daily_consumption":   "Used Per Day",
    "to_be_ordered_qty":   "Quantity To Buy",
    "reorder_qty":         "Reorder Quantity",
    "mps_demand":          "Sales Demand",
    "rate":                "Price Per Unit",
    "value":               "Money Value",
    "green_level":         "Healthy Level",
    "yellow_level":        "Warning Level",
    "red_level":           "Minimum Level",
    "levels":              "Planned Level",
    "inventory_coverage":  "Days-Of-Stock Band",
    "till_date_inventory": "Stock Note",
    "opening":             "Opening Stock",
    "receipt":             "Received In",
    "issued":              "Issued Out",
    "shortfall":           "Short By (kg)",
    "excess":              "Above Healthy Level (kg)",
    "excess_kg":           "Extra (kg)",
    "delta_kg":            "Above Healthy Level (kg)",
    "diff":                "Difference",
    "gap":                 "Short By (days)",
    "age_days":            "Days Waiting",
    "first_seen":          "First Asked On",
    "computed_ltc":        "Usage We Calculated",
    "imported_ltc":        "Usage In The Sheet",
    "lines":               "Materials",
    "note":                "Why",
    "action":              "Action",
    "suggested_action":    "What To Do",
    "status":              "Status",
    "verdict":             "Result",
    "rules_tripped":       "Concerns Raised",
    "fail_reasons":        "Fails Because",
    "owner":               "Owner",
    # Purchase-order side
    "po_number":           "Order Number",
    "po_numbers":          "Order Number(s)",
    "po_date":             "Order Date",
    "po_live":             "On Order Now",
    "po_overdue":          "On Order But Late",
    "po_outstanding":      "Still Due On Order",
    "po_earliest_due":     "Promised Date",
    "po_days_late":        "Days Late",
    "po_vendors":          "Supplier(s)",
    "vendor":              "Supplier",
    "ordered_qty":         "Ordered",
    "received_qty":        "Received",
    "balance_to_raise":    "Still To Order",
    "net_amount":          "Order Value",
    "advance_pct":         "Paid Up Front (%)",
    "exposure":            "Money At Risk",
}


# ── Verdict / status wording ────────────────────────────────────────────────
# The pill text a stakeholder actually reads. Anything not listed falls
# through unchanged, so a new verdict can never render as blank.

VERDICTS = {
    # Dashboard 1 statuses
    "STOCK-OUT":                   "NOTHING LEFT",
    "CRITICAL":                    "URGENT",
    "WATCH":                       "KEEP AN EYE ON IT",
    # Control 1
    "NOT ON ORDER":                "NOT ORDERED",
    "PARTLY COVERED":              "ORDERED, NOT ENOUGH",
    "ALREADY COVERED":             "ALREADY ORDERED",
    "OVER-ORDERED":                "ORDERED TOO MUCH",
    "UNVERIFIABLE":                "CANNOT CHECK — CODE MISSING",
    # Control 2
    "NEW — IN QUEUE":              "JUST CAME UP",
    "UNACTIONED":                  "WAITING TOO LONG",
    "OVERDUE ACTION":              "BADLY OVERDUE",
    "CRITICAL — TIME LOST":        "TOO LATE TO RECOVER",
    "ORDERED AND COMMITTED":       "ORDERED, DATE GIVEN",
    "ORDERED, NO COMMITMENT":      "ORDERED, NO DATE",
    "PART ORDERED":                "ONLY PART ORDERED",
    # Control 3
    "STOP — DEAD ITEM":            "STOP — NOT MOVING",
    "STOP — ALREADY OVER-STOCKED": "STOP — ALREADY TOO MUCH",
    "STOP — DOUBLE FLAG":          "STOP — TWO PROBLEMS AT ONCE",
    "CHALLENGE":                   "QUESTION THIS",
    "CLEAR":                       "FINE TO ORDER",
    "HIGH INVENTORY":              "ALREADY OVERSTOCKED",
    # Control 4
    "COVERED":                     "ENOUGH TIME",
    "WILL RUN SHORT":              "WILL RUN OUT FIRST",
    "SEVERELY EXPOSED":            "ORDERING WON'T SAVE IT",
    "ALREADY OUT":                 "ALREADY EMPTY",
    "NOT ASSESSABLE":              "CANNOT BE JUDGED",
    # Control 5
    "WITHIN LEAD TIME":            "STILL WITHIN TIME",
    "OVERDUE — NOTHING RECEIVED":  "LATE, NOTHING RECEIVED",
    "RECOVERY RISK":               "GET THE MONEY BACK",
    "ADVANCE ON DEAD STOCK":       "PAID UP FRONT FOR IDLE MATERIAL",
    "PART RECEIVED":               "PARTLY DELIVERED",
    "FULLY RECEIVED":              "FULLY DELIVERED",
    # Control 6
    "NO CODE":                     "NO CODE AT ALL",
    "PLACEHOLDER CODE":            "CODE NOT FILLED IN",
    "DUPLICATE MAPPING":           "CODE USED TWICE",
    "NOT YET CONFIRMED — awaiting item master":
                                   "CANNOT CHECK YET — NEED THE ITEM LIST",
    # Control 7
    "UNCONFIRMED":                 "NOT CONFIRMED YET",
    "UNRESOLVABLE — MASTER DATA":  "CODE MUST BE FIXED FIRST",
    "GENUINE RUN-DOWN":            "GENUINELY USED UP",
}


# ── Public helpers ──────────────────────────────────────────────────────────

def annotate_tiles(board_key, tiles):
    """Return a copy of ``tiles`` with ``plain_label`` / ``plain_sub`` added.

    Never mutates the stored JSON, never removes or rewrites the technical
    ``label`` / ``sub``, and silently leaves any unmapped tile alone.
    """
    mapping = TILES.get(board_key, {})
    out = {}
    for key, tile in (tiles or {}).items():
        entry = mapping.get(key)
        if not entry:
            out[key] = tile
            continue
        plain_label, plain_sub = entry
        out[key] = dict(
            tile,
            plain_label=plain_label,
            plain_sub=_fmt(plain_sub, tile),
        )
    return out


def annotate_columns(columns):
    """Return a copy of a column spec list with ``plain_label`` added."""
    return [
        dict(c, plain_label=COLUMNS.get(c.get("key"), c.get("label")))
        for c in (columns or [])
    ]


def verdict_map(columns):
    """The subset of VERDICTS relevant to a drill table's pill columns.

    Sent with the rows so the frontend can show plain verdicts *and* filter
    and export on the same values, instead of translating in two places.
    """
    if not any(c.get("pill") for c in (columns or [])):
        return {}
    return dict(VERDICTS)
