"""Bounded audit procedures; source comparison never asserts an audit opinion."""

from collections import defaultdict
from datetime import date
from decimal import Decimal


def money(row, field="amount"):
    return Decimal(str(row[field]))


def key(row):
    return row["account"], row["side"], row["currency"]


def control_rows(data, tables):
    totals: defaultdict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    controls = {}
    for item in tables["items"]:
        if date.fromisoformat(item["balance_date"]) != data.as_of:
            raise ValueError("Open-item balance date must equal the reporting date")
        totals[key(item)] += money(item)
    for control in tables["controls"]:
        if date.fromisoformat(control["as_of"]) != data.as_of:
            raise ValueError("GL controls must use the reporting date")
        k = key(control)
        if k in controls:
            raise ValueError("Duplicate account/side/currency control")
        controls[k] = control
    rows = []
    for index, k in enumerate(sorted(totals.keys() | controls.keys()), 1):
        control = controls.get(k)
        delta = totals.get(k, Decimal(0)) - money(control) if control else None
        rows.append(
            {
                "id": f"control-{index}",
                "kind": "control",
                "account": k[0],
                "side": k[1],
                "currency": k[2],
                "subledger_amount": str(totals.get(k, 0)),
                "control_amount": str(money(control)) if control else None,
                "difference": str(delta) if delta is not None else None,
                "control_source_id": control["id"] if control else None,
                "state": "MISSING_CONTROL"
                if control is None
                else "CONTROL_DIFFERENCE"
                if delta is not None and abs(delta) > data.tolerance
                else "MATCHED",
            }
        )
    return rows


def result(rows, blocked=False, limitations=()):
    return {
        "rows": rows,
        "exception_count": sum(r["state"] != "MATCHED" for r in rows),
        "blocked": blocked,
        "limitations": list(limitations),
    }


def subledger(data, tables):
    rows = control_rows(data, tables)
    return result(
        rows,
        any(r["state"] != "MATCHED" for r in rows),
        [
            "Balances use each subledger's normal sign; payable GL credits require an explicit sign bridge",
            "Uploaded controls require independent GL provenance; a matching total is not extraction completeness",
        ],
    )


def settlements(data, tables):
    rows = control_rows(data, tables)
    blocked = any(r["state"] != "MATCHED" for r in rows)
    items = {i["id"]: i for i in tables["items"]}
    allocations = defaultdict(list)
    seen = set()
    for s in tables["settlements"]:
        identity = (s["evidence_reference"], s["allocation_reference"])
        if identity in seen:
            raise ValueError("Duplicate settlement evidence/allocation reference")
        seen.add(identity)
        when = date.fromisoformat(s["date"])
        item = items.get(s["item_id"])
        mismatch = item is not None and any(
            s[f] != item[f] for f in ("account", "counterparty", "currency")
        )
        sign_error = item is not None and money(s) * money(item) < 0
        state = (
            "UNKNOWN_ITEM"
            if item is None
            else "SETTLEMENT_IDENTITY_MISMATCH"
            if mismatch
            else "SETTLEMENT_SIGN_MISMATCH"
            if sign_error
            else "OUTSIDE_REVIEW_WINDOW"
            if not data.as_of < when <= data.review_through
            else "MATCHED"
        )
        if state != "MATCHED":
            rows.append(
                {
                    "id": "settlement:" + s["id"],
                    "kind": "settlement",
                    "source_id": s["id"],
                    "state": state,
                }
            )
            blocked = True
        else:
            allocations[s["item_id"]].append(s)
    for item in tables["items"]:
        allocated = allocations[item["id"]]
        paid = sum((money(s) for s in allocated), Decimal(0))
        outstanding = money(item) - paid
        over = abs(paid) > abs(money(item)) + data.tolerance
        blocked |= over
        rows.append(
            {
                "id": "item:" + item["id"],
                "kind": "item",
                "item_id": item["id"],
                "account": item["account"],
                "counterparty": item["counterparty"],
                "currency": item["currency"],
                "reporting_date_balance": item["amount"],
                "subsequent_settled": str(paid),
                "remaining_balance": str(outstanding),
                "overdue_days_at_reporting": max(
                    0, (data.as_of - date.fromisoformat(item["due_date"])).days
                ),
                "settlement_source_ids": [s["id"] for s in allocated],
                "state": "OVERALLOCATED"
                if over
                else "MATCHED"
                if abs(outstanding) <= data.tolerance
                else "PARTIALLY_SETTLED"
                if allocated
                else "NO_SUBSEQUENT_SETTLEMENT",
            }
        )
    return result(
        rows,
        blocked,
        [
            "Reporting-date balances are preserved; subsequent settlements are separate evidence",
            "Explicit item allocation and bank evidence references require review; no fuzzy allocation is accepted",
            "Unsettled balances require further procedures; they are not automatically bad debts",
        ],
    )


def confirmations(data, tables):
    rows = control_rows(data, tables)
    blocked = any(r["state"] != "MATCHED" for r in rows)
    items = {i["id"]: i for i in tables["items"]}
    responses = {}
    for response in tables["responses"]:
        item_id = response["item_id"]
        if item_id in responses:
            raise ValueError("Select one current confirmation version per item")
        responses[item_id] = response
        if item_id not in items:
            rows.append(
                {
                    "id": "response:" + response["id"],
                    "kind": "confirmation",
                    "state": "UNKNOWN_ITEM",
                }
            )
            blocked = True
    for item in tables["items"]:
        response = responses.get(item["id"])
        state, delta = "NOT_REQUESTED", None
        if response:
            if (
                response["as_of"] != data.as_of.isoformat()
                or any(response[f] != item[f] for f in ("currency", "counterparty"))
                or abs(money(response, "requested_amount") - money(item)) > data.tolerance
            ):
                state, blocked = "CONFIRMATION_SCOPE_MISMATCH", True
            elif any(
                response.get(f) and date.fromisoformat(response[f]) > data.review_through
                for f in ("requested_on", "responded_on")
            ):
                state, blocked = "OUTSIDE_REVIEW_WINDOW", True
            elif response["status"] in {"received", "disputed"}:
                delta = money(response, "response_amount") - money(item)
                if not all(
                    response.get(f)
                    for f in ("contact_verified", "independently_received", "evidence_reference")
                ):
                    state, blocked = "INDEPENDENCE_EVIDENCE_MISSING", True
                else:
                    state = (
                        "DISPUTED"
                        if response["status"] == "disputed"
                        else ("MATCHED" if abs(delta) <= data.tolerance else "RESPONSE_DIFFERENCE")
                    )
            else:
                state = response["status"].upper().replace("-", "_")
        rows.append(
            {
                "id": "item:" + item["id"],
                "kind": "confirmation",
                "item_id": item["id"],
                "counterparty": item["counterparty"],
                "currency": item["currency"],
                "book_balance": item["amount"],
                "response_source_id": response["id"] if response else None,
                "difference": str(delta) if delta is not None else None,
                "state": state,
            }
        )
    return result(
        rows,
        blocked,
        [
            "This evaluates uploaded request/response evidence; no external request is dispatched",
            "Contact verification and independent receipt are reviewed declarations, not automatic authentication",
            "Non-responses and disputes need documented alternative procedures before approval",
        ],
    )


def single_date_cutoff(data, tables):
    rows = []
    for document in tables["documents"]:
        recognition = date.fromisoformat(document["recognition_date"])
        posted = (
            date.fromisoformat(document["posting_date"]) if document.get("posting_date") else None
        )
        if any(
            date.fromisoformat(document[f]) > data.review_through
            for f in ("invoice_date", "recognition_date")
        ) or (posted and posted > data.review_through):
            raise ValueError("Cutoff population extends beyond the declared review window")
        belongs = data.period_start <= recognition <= data.as_of
        recorded = posted is not None and data.period_start <= posted <= data.as_of
        state = (
            ("UNRECORDED_CREDIT" if money(document) < 0 else "UNRECORDED_LIABILITY")
            if belongs and posted is None
            else "LATE_RECOGNITION"
            if belongs and posted > data.as_of
            else "WRONG_PERIOD"
            if belongs != recorded
            else "MATCHED"
        )
        rows.append(
            {
                "id": document["id"],
                "counterparty": document["counterparty"],
                "reference": document["reference"],
                "currency": document["currency"],
                "amount": document["amount"],
                "recognition_date": document["recognition_date"],
                "posting_date": document.get("posting_date"),
                "state": state,
                "evidence_reference": document["evidence_reference"],
            }
        )
    return result(
        rows,
        limitations=[
            "Recognition dates/bases require professional validation against service and receipt evidence",
            "The uploaded population does not establish completeness of subsequent invoices or liabilities",
        ],
    )


def cutoff(data, tables):
    if any(row.get("recognition_mode") == "explicit-schedule" for row in tables["documents"]) or {
        "recognitions",
        "postings",
    } & set(tables):
        from app.modules.country_workflows.cutoff_schedules import compare

        return compare(data, tables, single_date_cutoff)
    return single_date_cutoff(data, tables)


AUDIT_CALCULATORS = {
    "subledger-control": subledger,
    "subsequent-settlements": settlements,
    "balance-confirmations": confirmations,
    "expense-cutoff": cutoff,
}
