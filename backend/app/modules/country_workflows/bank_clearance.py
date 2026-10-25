"""Explicit subsequent clearance; preserve the reporting-date BRS population."""

from collections import defaultdict
from datetime import date
from decimal import Decimal


def clearances(data, tables):
    from app.modules.country_workflows.audit_calculations import result

    def indexed(role):
        rows = tables[role]
        index = {row["id"]: row for row in rows}
        if len(index) != len(rows):
            raise ValueError("Duplicate bank clearance source row ID")
        return index

    items, transactions = indexed("outstanding"), indexed("statement")
    allocations = indexed("allocations")
    for row in [*items.values(), *transactions.values()]:
        if row["account"] != data.account or row["currency"] != data.currency:
            raise ValueError("Bank clearance account or currency differs from selected scope")
    identities = set()
    for item in items.values():
        identity = (item["reference"], item["date"], Decimal(item["amount"]))
        if identity in identities:
            raise ValueError(
                "Duplicate outstanding reference/date/amount; resolve the original BRS population"
            )
        identities.add(identity)
        if date.fromisoformat(item["balance_date"]) != data.as_of:
            raise ValueError("Outstanding balance date must equal the reporting date")
        if not Decimal(item["amount"]) or date.fromisoformat(item["date"]) > data.as_of:
            raise ValueError("Invalid reporting-date outstanding bank item")
    for transaction in transactions.values():
        if not data.as_of < date.fromisoformat(transaction["date"]) <= data.review_through:
            raise ValueError(
                "Bank clearance statement must lie strictly after reporting date within review window"
            )
    used_item: defaultdict[str, Decimal] = defaultdict(Decimal)
    used_transaction: defaultdict[str, Decimal] = defaultdict(Decimal)
    links = defaultdict(list)
    pairs = set()
    for allocation in allocations.values():
        if allocation["currency"] != data.currency:
            raise ValueError("Clearance allocation currency differs from selected scope")
        pair = allocation["outstanding_id"], allocation["transaction_id"]
        if pair in pairs:
            raise ValueError("Duplicate outstanding/statement clearance allocation")
        pairs.add(pair)
        item, transaction = items.get(pair[0]), transactions.get(pair[1])
        if not item or not transaction:
            raise ValueError(
                "Clearance allocation references a missing outstanding or statement row"
            )
        if transaction.get("is_reversal"):
            raise ValueError("A reversal bank movement cannot establish subsequent clearance")
        original, settled = Decimal(item["amount"]), Decimal(transaction["amount"])
        if original * settled <= 0:
            raise ValueError("Clearance requires the same signed movement direction")
        amount = Decimal(allocation["amount"])
        if amount <= 0:
            raise ValueError("Clearance allocation must be positive")
        used_item[item["id"]] += amount
        used_transaction[transaction["id"]] += amount
        if used_item[item["id"]] > abs(original) or used_transaction[transaction["id"]] > abs(
            settled
        ):
            raise ValueError("Outstanding item or bank movement is overallocated")
        links[item["id"]].append(
            {
                "allocation_id": allocation["id"],
                "transaction_id": transaction["id"],
                "cleared_on": transaction["date"],
                "amount": str(amount),
                "evidence_reference": allocation["evidence_reference"],
                "rationale": allocation["rationale"],
            }
        )
    rows = []
    for item in items.values():
        original = Decimal(item["amount"])
        residual = abs(original) - used_item[item["id"]]
        rows.append(
            {
                "id": "outstanding:" + item["id"],
                "kind": "outstanding",
                "source_id": item["id"],
                "reference": item["reference"],
                "account": item["account"],
                "currency": item["currency"],
                "reporting_date_amount": str(original),
                "subsequently_cleared": str(used_item[item["id"]]),
                "remaining_after_review": str(residual if original > 0 else -residual),
                "age_at_reporting_days": (data.as_of - date.fromisoformat(item["date"])).days,
                "clearances": links[item["id"]],
                "state": "MATCHED"
                if residual == 0
                else "PARTIALLY_CLEARED"
                if used_item[item["id"]]
                else "NOT_CLEARED",
            }
        )
    for transaction in transactions.values():
        residual = abs(Decimal(transaction["amount"])) - used_transaction[transaction["id"]]
        rows.append(
            {
                "id": "statement:" + transaction["id"],
                "kind": "statement",
                "source_id": transaction["id"],
                "currency": transaction["currency"],
                "statement_amount": transaction["amount"],
                "is_reversal": bool(transaction.get("is_reversal")),
                "allocated": str(used_transaction[transaction["id"]]),
                "unallocated_amount": str(residual),
                "state": "REVERSAL_NOT_CLEARANCE"
                if transaction.get("is_reversal")
                else "MATCHED" if residual == 0 else "UNALLOCATED_STATEMENT_MOVEMENT",
            }
        )
    return {
        **result(
            rows,
            limitations=[
                "Subsequent clearance preserves reporting-date outstanding amounts; it does not rewrite the BRS or post entries",
                "Explicit retained allocations only; same account, currency and direction; no reference-only automatic clearance",
                "Unallocated later movements remain visible and may relate to other periods or transactions",
                "Flagged reversals remain visible but cannot settle outstanding items; reversal pairing is separately assessed",
            ],
        ),
        "execution_mode": "rules_baseline",
        "reporting_date_population_changed": False,
    }
