"""Owned purchased-stock costing. Count assurance remains in country_workflows.

Specific identification covers individual units and segregated purchased project lots.
No production allocations, returns or implicit FX.
Every revision is an immutable IFRS run over a separately approved input record.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.modules.ifrs.inventory_layers import ProjectCostLayers


def validate_identified_units(data):
    """No inferred allocations: one physical unit per item/location schedule."""
    specific = data.method == "specific_identification"
    identities: dict[tuple[str, str], tuple[tuple[str, str], Decimal]] = {}
    timelines: dict[tuple[str, str], list[tuple[date, int, int, Decimal]]] = defaultdict(list)
    openings: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    bases: dict[tuple[str, str], tuple[str, str, str]] = {}
    population = sum(
        1
        + len(i.receipts)
        + len(i.issues)
        + len(i.opening_layers)
        + sum(len(m.cost_allocations) for m in i.issues)
        for i in data.items
    )
    if specific and population > 20000:
        raise ValueError("Specific-identification population exceeds 20000 rows")
    for item in data.items:
        declared = (
            item.identification_reference,
            item.identification_assessment,
            item.opening_cost_evidence,
            item.opening_layers,
            any(m.cost_allocations for m in item.issues),
            item.identification_basis != "individual_unit",
        )
        if not specific:
            if any(declared):
                raise ValueError("Identified-unit evidence requires specific identification")
            continue
        if (
            not item.sku.strip()
            or not item.identification_reference.strip()
            or len(item.identification_assessment.strip()) < 10
        ):
            raise ValueError("Specific identification requires SKU, unit identity and assessment")
        key = (item.sku.strip(), item.identification_reference.strip())
        basis_kind = (item.uom, item.ownership, item.identification_basis)
        if key in bases and bases[key] != basis_kind:
            raise ValueError("Identified inventory changes ownership/UOM or identification basis")
        bases[key] = basis_kind
        if any(not m.evidence.strip() for m in [*item.receipts, *item.issues]):
            raise ValueError("Identified-unit movements require explicit evidence")
        if item.identification_basis == "segregated_project_lot":
            continue
        if item.opening_layers or any(m.cost_allocations for m in item.issues):
            raise ValueError("Layer allocations require a segregated project lot")
        if item.opening_quantity not in (0, 1):
            raise ValueError("Specific identification requires one individually tracked unit")
        if item.opening_quantity and not item.opening_cost_evidence.strip():
            raise ValueError("Opening identified-unit cost requires evidence")
        if not item.opening_quantity and item.opening_unit_cost:
            raise ValueError("Zero opening units require zero opening cost")
        if any(m.quantity != 1 for m in [*item.receipts, *item.issues]):
            raise ValueError("Identified-unit movements must each contain exactly one unit")
        basis = (item.uom, item.ownership)
        original = item.opening_quantity + sum(
            (r.quantity for r in item.receipts if r.transaction_type == "purchase"),
            Decimal(0),
        )
        prior_basis, prior_original = identities.get(key, (basis, Decimal(0)))
        if prior_basis != basis or prior_original + original > 1:
            raise ValueError("Identified unit is duplicated or changes ownership/UOM")
        identities[key] = (basis, prior_original + original)
        openings[key] += item.opening_quantity
        for sign, movements in ((1, item.receipts), (-1, item.issues)):
            timelines[key].extend((m.date, m.sequence, sign, m.quantity) for m in movements)
    for key, (_, original) in identities.items():
        if original != 1:
            raise ValueError("Identified unit requires exactly one original acquisition")
        held = openings[key]
        for _, _, sign, quantity in sorted(timelines[key]):
            held += sign * quantity
            if held not in (0, 1):
                raise ValueError("Identified unit has overlapping or missing custody movements")


def inventory(data):
    from app.modules.ifrs.calculations import q

    zero = Decimal(0)
    validate_identified_units(data)
    specific = data.method == "specific_identification"
    if data.period_end < data.period_start:
        raise ValueError("Inventory period is reversed")
    if len({item.reference for item in data.items}) != len(data.items):
        raise ValueError("Duplicate inventory item/location reference")
    rows, movements, issues = [], [], []
    identified_layers: list[dict] = []
    identified_allocations: list[dict] = []
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
        project = (
            ProjectCostLayers(item)
            if specific and item.identification_basis == "segregated_project_lot"
            else None
        )
        value = project.cost if project is not None else quantity * item.opening_unit_cost
        opening_value = value
        layers = [[quantity, item.opening_unit_cost]] if quantity else []
        receipts_value = issued_value = zero
        for when, ref, kind, movement in sorted(
            events, key=lambda event: (event[0], event[3].sequence)
        ):
            if kind == "receipt":
                amount = movement.quantity * movement.unit_cost + movement.landed_cost
                quantity += movement.quantity
                if specific and project is None and quantity > 1:
                    raise ValueError("An identified unit cannot be held twice at one location")
                value += amount
                receipts_value += amount
                layers.append([movement.quantity, amount / movement.quantity])
                if project is not None:
                    project.receipt(movement, amount)
            else:
                if movement.quantity > quantity:
                    raise ValueError(
                        "Negative stock; resolve missing receipts or cut-off before costing"
                    )
                amount = zero
                if project is not None:
                    amount = project.issue(movement)
                elif data.method == "weighted_average":
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
                if project is None and movement.quantity == quantity:
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
                        **(
                            {
                                "identification_reference": item.identification_reference.strip(),
                                "identification_basis": item.identification_basis,
                            }
                            if specific
                            else {}
                        ),
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
                    **(
                        {"identification_reference": item.identification_reference.strip()}
                        if specific
                        else {}
                    ),
                }
            )
        if project is not None:
            if project.quantity != quantity or q(project.cost) != q(value):
                raise ValueError(
                    "Specific project layer costs do not reconcile to the movement ledger"
                )
            identified_layers.extend(project.layers.values())
            identified_allocations.extend(project.allocations)
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
                **(
                    {
                        "sku": item.sku,
                        "identification_basis": item.identification_basis,
                        "identification_reference": item.identification_reference.strip(),
                        "identification_assessment": item.identification_assessment,
                        "opening_cost_evidence": item.opening_cost_evidence,
                    }
                    if specific
                    else {}
                ),
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
                and (
                    not specific
                    or all(
                        source[key] == target[key]
                        for key in ["identification_reference", "identification_basis"]
                    )
                )
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
        **(
            {
                "identified_layers": identified_layers,
                "identified_allocations": identified_allocations,
            }
            if identified_layers or identified_allocations
            else {}
        ),
        "limitations": [
            "Purchased stock and matched location transfers only; production and returns require specialist schedules",
            "Specific identification requires separately tracked units or explicitly allocated segregated project lots and independently assessed eligibility; no automatic India tax valuation or physical-count assurance",
            "Prior write-down is the approved allocation to remaining units; custody-only goods are excluded from accounting assets",
            "Ageing does not determine NRV; supplied comparable price and completion/selling costs require review",
        ],
    }
