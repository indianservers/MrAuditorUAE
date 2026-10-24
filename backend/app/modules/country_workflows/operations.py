"""Reconciled operational schedules extending the existing country workflow engine."""

from collections import defaultdict
from datetime import date
from decimal import Decimal


def allocations(data, tables):
    from app.modules.country_workflows.audit_calculations import control_rows, money, result

    items = {row["id"]: row for row in tables["items"]}
    payments = {row["id"]: row for row in tables["payments"]}
    allocated_item: defaultdict[str, Decimal] = defaultdict(Decimal)
    allocated_payment: defaultdict[str, Decimal] = defaultdict(Decimal)
    evidence = defaultdict(list)
    for payment in payments.values():
        if date.fromisoformat(payment["date"]) > data.as_of:
            raise ValueError("Future cash movement is outside this allocation schedule")
    for row in tables["allocations"]:
        item, payment = items.get(row["item_id"]), payments.get(row["payment_id"])
        if not item or not payment:
            raise ValueError("Allocation references a missing invoice or cash movement")
        if payment["confirmation_status"] != "confirmed":
            raise ValueError("Pending/reversed cash cannot settle an invoice")
        if any(item[k] != payment[k] for k in ["account", "counterparty", "currency"]):
            raise ValueError(
                "Allocation account/party/currency mismatch; explicit FX bridge required"
            )
        if row["currency"] != payment["currency"]:
            raise ValueError("Allocation currency differs from cash movement")
        if payment["direction"] != ("receipt" if item["side"] == "receivable" else "payment"):
            raise ValueError("Cash movement direction differs from subledger side")
        if item["document_date"] > payment["date"]:
            raise ValueError(
                "Pre-invoice cash is an advance; approve its subsequent allocation separately"
            )
        amount = money(row)
        allocated_item[item["id"]] += amount
        allocated_payment[payment["id"]] += amount
        evidence[item["id"]].append(row["id"])
        if allocated_item[item["id"]] > money(item) or allocated_payment[payment["id"]] > money(
            payment
        ):
            raise ValueError("Cash or invoice is overallocated; preserve excess as unapplied cash")
    derived, rows = [], []
    for item in items.values():
        outstanding = money(item) - allocated_item[item["id"]]
        derived.append({**item, "amount": str(outstanding)})
        rows.append(
            {
                "id": "item:" + item["id"],
                "kind": "open_item",
                "item_id": item["id"],
                "account": item["account"],
                "counterparty": item["counterparty"],
                "side": item["side"],
                "currency": item["currency"],
                "invoice_amount": item["amount"],
                "allocated": str(allocated_item[item["id"]]),
                "remaining_balance": str(outstanding),
                "days_overdue": max(0, (data.as_of - date.fromisoformat(item["due_date"])).days),
                "allocation_ids": evidence[item["id"]],
                "state": "MATCHED",
            }
        )
    for payment in payments.values():
        residual = money(payment) - allocated_payment[payment["id"]]
        rows.append(
            {
                "id": "cash:" + payment["id"],
                "kind": "cash_movement",
                "payment_id": payment["id"],
                "currency": payment["currency"],
                "confirmed_amount": payment["amount"]
                if payment["confirmation_status"] == "confirmed"
                else None,
                "allocated": str(allocated_payment[payment["id"]]),
                "unapplied_cash": str(residual),
                "state": "UNCONFIRMED_CASH"
                if payment["confirmation_status"] != "confirmed"
                else "UNAPPLIED_CASH"
                if residual
                else "MATCHED",
            }
        )
    controls = control_rows(data, {"items": derived, "controls": tables["controls"]})
    rows += controls
    return {
        **result(
            rows,
            any(r["state"] != "MATCHED" for r in controls),
            [
                "Explicit confirmed-cash allocation only; unapplied cash is never forced against an invoice",
                "Credit-note application, foreign-currency settlement and advance release require separately approved bridges",
                "Payment confirmation is supplied evidence; this workflow issues no payment instruction or collection message",
            ],
        ),
        "remaining_open_items": derived,
        "execution_mode": "rules_baseline",
    }


OPERATION_CALCULATORS = {"open-item-allocations": allocations}
