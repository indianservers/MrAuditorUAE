"""Owned purchased-stock costing. Count assurance remains in country_workflows.

No production allocations, specific identification, returns or implicit FX.
Every revision is an immutable IFRS run over a separately approved input record.
"""

from collections import defaultdict
from decimal import Decimal


def inventory(data):
    from app.modules.ifrs.calculations import q

    zero = Decimal(0)
    if data.period_end < data.period_start:
        raise ValueError("Inventory period is reversed")
    if len({item.reference for item in data.items}) != len(data.items):
        raise ValueError("Duplicate inventory item/location reference")
    rows, movements, issues = [], [], []
    transfers = defaultdict(list)
    for item in data.items:
        events = [(r.date, r.reference, "receipt", r) for r in item.receipts]
        events += [(r.date, r.reference, "issue", r) for r in item.issues]
        if len({ref for _, ref, _, _ in events}) != len(events):
            raise ValueError("Duplicate stock movement reference")
        if any(not data.period_start <= when <= data.period_end for when, *_ in events):
            raise ValueError(
                "Backdated/out-of-period stock requires a revised approved period input"
            )
        # Same-day receipt/issue ordering changes cost. Do not invent an order.
        if len({(r.date, r.sequence) for *_, r in events}) != len(events):
            raise ValueError("Same-day movements require distinct approved sequence numbers")
        quantity = item.opening_quantity
        value = quantity * item.opening_unit_cost
        opening_value = value
        layers = [[quantity, item.opening_unit_cost]] if quantity else []
        receipts_value = issued_value = zero
        for when, ref, kind, movement in sorted(
            events, key=lambda event: (event[0], event[3].sequence)
        ):
            if kind == "receipt":
                amount = movement.quantity * movement.unit_cost + movement.landed_cost
                quantity += movement.quantity
                value += amount
                receipts_value += amount
                layers.append([movement.quantity, amount / movement.quantity])
            else:
                if movement.quantity > quantity:
                    raise ValueError(
                        "Negative stock; resolve missing receipts or cut-off before costing"
                    )
                amount = zero
                if data.method == "weighted_average":
                    amount = value / quantity * movement.quantity
                else:
                    remaining = movement.quantity
                    while remaining:
                        take = min(layers[0][0], remaining)
                        amount += take * layers[0][1]
                        remaining -= take
                        layers[0][0] -= take
                        if not layers[0][0]:
                            layers.pop(0)
                if movement.quantity == quantity:
                    # Full derecognition consumes the exact remaining cost, including
                    # subprecision unit-cost division residuals.
                    amount = value
                quantity -= movement.quantity
                value -= amount
                issued_value += amount
            if movement.transaction_type.startswith("transfer_"):
                if not movement.transfer_reference or not item.sku:
                    raise ValueError("Transfers require a shared reference and explicit SKU")
                transfers[movement.transfer_reference].append(
                    {
                        "item": item.reference,
                        "sku": item.sku,
                        "uom": item.uom,
                        "ownership": item.ownership,
                        "location": item.location,
                        "date": when,
                        "sequence": movement.sequence,
                        "direction": movement.transaction_type,
                        "quantity": movement.quantity,
                        "cost": amount,
                    }
                )
            elif movement.transfer_reference:
                raise ValueError("A transfer reference requires a transfer movement type")
            movements.append(
                {
                    "item": item.reference,
                    "reference": ref,
                    "date": when,
                    "kind": kind,
                    "transaction_type": movement.transaction_type,
                    "transfer_reference": movement.transfer_reference,
                    "quantity": movement.quantity,
                    "cost": q(amount),
                    "closing_quantity": quantity,
                    "closing_cost": q(value),
                    "evidence": movement.evidence,
                }
            )
        if quantity != item.expected_closing_quantity:
            issues.append(
                {
                    "code": "QUANTITY_RECONCILIATION",
                    "reference": item.reference,
                    "blocking": True,
                    "difference": quantity - item.expected_closing_quantity,
                    "remediation": "Review count/cut-off bridge and approve quantity correction separately",
                }
            )
        if item.prior_write_down_remaining > value:
            raise ValueError("Remaining prior write-down exceeds cost of remaining units")
        nrv = quantity * max(zero, item.selling_price - item.completion_cost - item.selling_cost)
        write_down = max(zero, value - nrv)
        expense = write_down - item.prior_write_down_remaining
        owned = item.ownership == "owned"
        rows.append(
            {
                "reference": item.reference,
                "uom": item.uom,
                "location": item.location,
                "ownership": item.ownership,
                "opening_cost": q(opening_value),
                "receipt_cost": q(receipts_value),
                "issue_cost": q(issued_value),
                "closing_quantity": quantity,
                "closing_cost": q(value),
                "nrv": q(nrv),
                "prior_write_down_remaining": item.prior_write_down_remaining,
                "closing_write_down": q(write_down),
                "write_down_expense_or_reversal": q(expense),
                "accounting_carrying": q(min(value, nrv)) if owned else zero,
                "recognised_expense_or_reversal": q(expense) if owned else zero,
                "cost_rollforward_difference": q(
                    opening_value + receipts_value - issued_value - value
                ),
                "nrv_evidence": item.nrv_evidence,
            }
        )
    transfer_rows = []
    for reference, pair in sorted(transfers.items()):
        outgoing = [row for row in pair if row["direction"] == "transfer_out"]
        incoming = [row for row in pair if row["direction"] == "transfer_in"]
        matched = len(outgoing) == len(incoming) == 1
        if matched:
            source, target = outgoing[0], incoming[0]
            matched = (
                source["item"] != target["item"]
                and source["location"] != target["location"]
                and all(
                    source[key] == target[key] for key in ["sku", "uom", "ownership", "quantity"]
                )
                and q(source["cost"]) == q(target["cost"])
                and (source["date"], source["sequence"]) <= (target["date"], target["sequence"])
            )
        transfer_rows.append(
            {"reference": reference, "legs": pair, "state": "MATCHED" if matched else "BLOCKED"}
        )
        if not matched:
            issues.append(
                {
                    "code": "TRANSFER_NOT_RECONCILED",
                    "reference": reference,
                    "blocking": True,
                    "remediation": "Match source and destination SKU, UOM, ownership, quantity, dated sequence and actual issue cost; no transfer profit or balancing amount",
                }
            )
    return {
        "schedule": rows,
        "movements": movements,
        "issues": issues,
        "transfers": transfer_rows,
        "closing_carrying": sum((r["accounting_carrying"] for r in rows), zero),
        "write_down_movement": sum((r["recognised_expense_or_reversal"] for r in rows), zero),
        "method": data.method,
        "limitations": [
            "Purchased stock and matched location transfers only; production, returns and specific identification require specialist schedules",
            "Prior write-down is the approved allocation to remaining units; custody-only goods are excluded from accounting assets",
            "Ageing does not determine NRV; supplied comparable price and completion/selling costs require review",
        ],
    }
