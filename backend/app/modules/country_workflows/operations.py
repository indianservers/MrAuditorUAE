"""Reconciled operational schedules extending the existing country workflow engine."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.modules.country_workflows.bank_clearance import clearances


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


def credit_applications(data, tables):
    from app.modules.country_workflows.audit_calculations import control_rows, money, result

    items = {row["id"]: row for row in tables["items"]}
    document_keys = set()
    for item in items.values():
        identity = tuple(
            item[k]
            for k in (
                "account",
                "side",
                "counterparty",
                "currency",
                "document_type",
                "reference",
                "document_date",
            )
        )
        if identity in document_keys:
            raise ValueError(
                "Duplicate open-item document identity; aggregate or resolve source versions"
            )
        document_keys.add(identity)
    applied: defaultdict[str, Decimal] = defaultdict(Decimal)
    links = defaultdict(list)
    seen = set()
    rows = []
    for application in tables["applications"]:
        identity = (application["evidence_reference"], application["allocation_reference"])
        if identity in seen:
            raise ValueError("Duplicate credit application evidence/allocation reference")
        seen.add(identity)
        credit = items.get(application["credit_item_id"])
        invoice = items.get(application["invoice_item_id"])
        if not credit or not invoice:
            raise ValueError("Credit application references a missing open item")
        if credit["document_type"] != "credit-note" or money(credit) >= 0:
            raise ValueError("Application requires a negative credit-note balance")
        if invoice["document_type"] not in {"invoice", "debit-note"} or money(invoice) <= 0:
            raise ValueError("Application requires a positive invoice/debit-note balance")
        if any(credit[k] != invoice[k] for k in ("account", "side", "counterparty", "currency")):
            raise ValueError("Credit application account/side/party/currency mismatch")
        if application["currency"] != credit["currency"]:
            raise ValueError("Credit application currency differs from open items")
        when = date.fromisoformat(application["date"])
        if when > data.as_of or any(
            date.fromisoformat(item["document_date"]) > when for item in (credit, invoice)
        ):
            raise ValueError(
                "Credit application date must follow both documents and precede cutoff"
            )
        amount = money(application)
        applied[credit["id"]] += amount
        applied[invoice["id"]] += amount
        if applied[credit["id"]] > -money(credit) or applied[invoice["id"]] > money(invoice):
            raise ValueError("Credit or invoice is overapplied; retain residual balances")
        for item in (credit, invoice):
            links[item["id"]].append(application["id"])
        rows.append(
            {
                **application,
                "id": "application:" + application["id"],
                "application_id": application["id"],
                "kind": "credit_application",
                "state": "MATCHED",
            }
        )
    derived = []
    for item in items.values():
        original = money(item)
        remaining = (
            original + applied[item["id"]] if original < 0 else original - applied[item["id"]]
        )
        derived.append({**item, "amount": str(remaining)})
        rows.append(
            {
                "id": "item:" + item["id"],
                "kind": "open_item",
                "item_id": item["id"],
                "account": item["account"],
                "counterparty": item["counterparty"],
                "side": item["side"],
                "currency": item["currency"],
                "document_type": item["document_type"],
                "original_balance": str(original),
                "applied": str(applied[item["id"]]),
                "remaining_balance": str(remaining),
                "application_ids": links[item["id"]],
                "state": "UNAPPLIED_CREDIT" if remaining < 0 else "MATCHED",
            }
        )
    controls = control_rows(data, {"items": derived, "controls": tables["controls"]})
    rows += controls
    return {
        **result(
            rows,
            any(row["state"] != "MATCHED" for row in controls),
            [
                "Explicit pre-application balances and evidenced applications only; no automatic netting",
                "Same account, subledger side, party and currency only; residual credits remain visible",
                "Applications preserve total signed balances; independent GL controls remain required",
                "This schedule does not determine VAT/GST adjustment eligibility or post journals",
            ],
        ),
        "remaining_open_items": derived,
        "execution_mode": "rules_baseline",
    }


OPERATION_CALCULATORS = {
    "bank-subsequent-clearance": clearances,
    "open-item-allocations": allocations,
    "credit-note-applications": credit_applications,
}
