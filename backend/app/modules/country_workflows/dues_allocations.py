"""Explicit obligation/return/bank links, without inferred statutory liabilities."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.modules.country_workflows.audit_calculations import result
from app.modules.country_workflows.bank_dates import date_details
from app.modules.country_workflows.obligation_scope import scope_key


def allocate(data, tables, country):
    def indexed(role):
        rows = tables[role]
        records = {row["id"]: row for row in rows}
        if len(records) != len(rows):
            raise ValueError("Duplicate obligation allocation source row ID")
        return records

    expected, reported, bank, allocations = (
        indexed(role) for role in ("expected", "reported", "bank", "allocations")
    )
    indexes = {}

    def identity(row):
        return tuple(
            row[field] for field in ("registration", "subject", "period", "component", "currency")
        ) + (scope_key(row),)

    for role, records in (("expected", expected), ("reported", reported)):
        by_key = {}
        for row in records.values():
            key = identity(row)
            if key in by_key:
                raise ValueError(
                    "Duplicate obligation identity; restate corrections before allocating"
                )
            by_key[key] = row
            if (
                row["currency"] != data.currency
                or not data.obligation_month_start <= row["period"] <= data.obligation_month_end
            ):
                raise ValueError("Obligation month or currency is outside the declared scope")
            if Decimal(row["amount"]) < 0:
                raise ValueError(
                    "Negative obligations require an assessed restated population before allocation"
                )
            if country == "AE" and row["component"].upper().split(":")[0] in {
                "PF",
                "ESI",
                "PT",
                "TDS",
                "TCS",
            }:
                raise ValueError("Indian domestic statutory component cannot run in a UAE workflow")
            scope = row.get("withholding_scope")
            savings = row.get("savings_scope")
            if savings is not None and (
                country != "AE"
                or row["currency"] != "AED"
                or row["component"] != "SAVINGS:EMPLOYER_BASIC"
                or row["period"] != savings["coverage_start"][:7]
            ):
                raise ValueError(
                    "Savings settlements require UAE/AED and an exact fund/enrolment/coverage scope"
                )
            benefit = row.get("benefit_scope")
            if benefit is not None and (
                country != "AE"
                or row["currency"] != "AED"
                or row["component"] != "BENEFIT:GRATUITY"
                or row["period"] != benefit["service_end"][:7]
            ):
                raise ValueError(
                    "Gratuity settlement scopes require UAE/AED and the service-end month"
                )
            if scope is not None and (
                country != "IN" or row["currency"] != "INR" or row["component"] != scope["tax_kind"]
            ):
                raise ValueError(
                    "Withholding settlement scopes require India and matching INR tax components"
                )
            if (
                scope is not None
                and scope["tax_kind"] == "TCS"
                and scope["rule_reference"].upper().replace(" ", "") == "206C(1H)"
                and row["period"] >= "2025-04"
            ):
                raise ValueError("Section206C(1H) is withdrawn for this obligation period")
            if row["component"].upper() == "TCS:206C(1H)" and row["period"] >= "2025-04":
                raise ValueError("Section206C(1H) is withdrawn for this obligation period")
            if row.get("payment_date"):
                raise ValueError(
                    "Expected/reported payment dates cannot replace independent allocated bank evidence"
                )
        indexes[role] = by_key
    for row in bank.values():
        if row["account"] != data.account or row["currency"] != data.currency:
            raise ValueError("Bank account or currency differs from the declared settlement scope")
        if not data.settlement_start <= date.fromisoformat(row["date"]) <= data.as_of:
            raise ValueError("Bank movement is outside the declared settlement window")

    used_expected: defaultdict[str, Decimal] = defaultdict(Decimal)
    used_reported: defaultdict[str, Decimal] = defaultdict(Decimal)
    used_bank: defaultdict[str, Decimal] = defaultdict(Decimal)
    links = defaultdict(list)
    seen = set()
    sign = Decimal(-1) if data.bank_payment_sign == "debit-negative" else Decimal(1)
    for allocation in allocations.values():
        e_id, r_id, b_id = (
            allocation[key] for key in ("expected_id", "reported_id", "transaction_id")
        )
        key = (e_id, r_id, b_id)
        if key in seen:
            raise ValueError("Duplicate obligation/reported/bank allocation")
        seen.add(key)
        e, r, b = expected.get(e_id), reported.get(r_id), bank.get(b_id)
        if e is None or r is None or b is None:
            raise ValueError("Allocation references a missing obligation, reported or bank row")
        if identity(e) != identity(r) or allocation["currency"] != data.currency:
            raise ValueError(
                "Allocation crosses registration, subject, component, month or currency; pension scope must also agree; withholding scopes must also agree; benefit service scopes must also agree"
            )
        if e.get("withholding_scope") and b["date"] < e["withholding_scope"]["transaction_date"]:
            raise ValueError(
                "Bank movement predates withholding transaction; assess advance challans separately"
            )
        if e.get("benefit_scope") and b["date"] < e["benefit_scope"]["service_end"]:
            raise ValueError(
                "Bank movement predates service end; assess gratuity advances separately"
            )
        if date_details(b)["booking_date_review_required"]:
            raise ValueError(
                "A value-date fallback cannot establish dated obligation settlement; retain explicit booking-date evidence"
            )
        amount = Decimal(allocation["amount"])
        outflow = Decimal(b["amount"]) * sign
        if amount <= 0 or outflow <= 0 or b.get("is_reversal"):
            raise ValueError(
                "Only positive allocations of unreversed bank outflows may settle obligations"
            )
        used_expected[e_id] += amount
        used_reported[r_id] += amount
        used_bank[b_id] += amount
        if (
            used_expected[e_id] > Decimal(e["amount"])
            or used_reported[r_id] > Decimal(r["amount"])
            or used_bank[b_id] > outflow
        ):
            raise ValueError("Obligation, reported amount or bank movement is overallocated")
        links[e_id].append(
            {
                "allocation_id": allocation["id"],
                "reported_id": r_id,
                "transaction_id": b_id,
                "amount": str(amount),
                "payment_date": b["date"],
                **date_details(b),
                "bank_reference": b["reference"],
                "evidence_reference": allocation["evidence_reference"],
                "rationale": allocation["rationale"],
            }
        )

    rows = []
    for e in expected.values():
        key = identity(e)
        r = indexes["reported"].get(key)
        original = Decimal(e["amount"])
        paid = used_expected[e["id"]]
        residual = original - paid
        due = date.fromisoformat(e["due_date"]) if e.get("due_date") else None
        conflict = bool(r and r.get("due_date") and r["due_date"] != e.get("due_date"))
        late = sum(
            (
                Decimal(link["amount"])
                for link in links[e["id"]]
                if due and date.fromisoformat(link["payment_date"]) > due
            ),
            Decimal(0),
        )
        reasons = []
        if r is None:
            reasons.append("MISSING_REPORTED_OBLIGATION")
        elif abs(original - Decimal(r["amount"])) > data.tolerance:
            reasons.append("REPORTED_AMOUNT_VARIANCE")
        if residual:
            reasons.append("PARTIALLY_SETTLED" if paid else "UNSETTLED")
        if original and not due:
            reasons.append("PENDING_DUE_DATE")
        if conflict:
            reasons.append("CONFLICTING_DUE_DATE")
        if late:
            reasons.append("LATE_PAYMENT")
        if due and due < data.as_of and residual:
            reasons.append("OVERDUE_RESIDUAL")
        rows.append(
            {
                "id": "obligation:" + e["id"],
                "kind": "obligation",
                "source_id": e["id"],
                **{
                    field: e[field]
                    for field in ("registration", "subject", "period", "component", "currency")
                },
                "expected_amount": str(original),
                **({"benefit_scope": e["benefit_scope"]} if e.get("benefit_scope") else {}),
                **({"pension_scope": e["pension_scope"]} if e.get("pension_scope") else {}),
                **({"savings_scope": e["savings_scope"]} if e.get("savings_scope") else {}),
                **(
                    {
                        field: e["savings_scope"][field]
                        for field in (
                            "fund_id",
                            "membership_reference",
                            "coverage_start",
                            "coverage_end",
                        )
                    }
                    if e.get("savings_scope")
                    else {}
                ),
                **(
                    {"withholding_scope": e["withholding_scope"]}
                    if e.get("withholding_scope")
                    else {}
                ),
                "reported_amount": r["amount"] if r else None,
                "reported_difference": str(Decimal(r["amount"]) - original) if r else None,
                "bank_settled": str(paid),
                "outstanding_amount": str(residual),
                "due_date": e.get("due_date"),
                "due_date_basis": "DECLARED_EXPECTED_SOURCE_NOT_LEGALLY_INFERRED",
                "late_settled_amount": str(late),
                "payment_allocations": links[e["id"]],
                "timing_status": "PENDING_DUE_DATE"
                if original and not due
                else "CONFLICTING_DUE_DATE"
                if conflict
                else "LATE_PAYMENT"
                if late
                else "OVERDUE_RESIDUAL"
                if due and due < data.as_of and residual
                else "NO_LATE_PAYMENT_IDENTIFIED_IN_DECLARED_SCOPE",
                "issues": reasons,
                "state": reasons[0] if reasons else "MATCHED",
            }
        )
    for r in reported.values():
        residual = Decimal(r["amount"]) - used_reported[r["id"]]
        rows.append(
            {
                "id": "reported:" + r["id"],
                "kind": "reported",
                "source_id": r["id"],
                **{
                    field: r[field]
                    for field in ("registration", "subject", "period", "component", "currency")
                },
                "reported_amount": r["amount"],
                **({"benefit_scope": r["benefit_scope"]} if r.get("benefit_scope") else {}),
                **({"pension_scope": r["pension_scope"]} if r.get("pension_scope") else {}),
                **({"savings_scope": r["savings_scope"]} if r.get("savings_scope") else {}),
                **(
                    {
                        field: r["savings_scope"][field]
                        for field in (
                            "fund_id",
                            "membership_reference",
                            "coverage_start",
                            "coverage_end",
                        )
                    }
                    if r.get("savings_scope")
                    else {}
                ),
                **(
                    {"withholding_scope": r["withholding_scope"]}
                    if r.get("withholding_scope")
                    else {}
                ),
                "bank_settled": str(used_reported[r["id"]]),
                "unsettled_reported_amount": str(residual),
                "state": "UNEXPECTED_REPORTED_OBLIGATION"
                if identity(r) not in indexes["expected"]
                else "UNSETTLED_REPORTED_AMOUNT"
                if residual
                else "MATCHED",
            }
        )
    for b in bank.values():
        outflow = Decimal(b["amount"]) * sign
        residual = abs(outflow) - used_bank[b["id"]]
        rows.append(
            {
                "id": "bank:" + b["id"],
                "kind": "bank",
                "source_id": b["id"],
                "account": b["account"],
                "reference": b["reference"],
                "date": b["date"],
                "currency": b["currency"],
                "bank_amount": b["amount"],
                "is_reversal": bool(b.get("is_reversal")),
                "bank_direction": "OUTFLOW" if outflow > 0 else "INFLOW" if outflow < 0 else "ZERO",
                "allocated": str(used_bank[b["id"]]),
                "unallocated_bank_amount": str(residual),
                "state": "REVERSAL_NOT_SETTLEMENT"
                if b.get("is_reversal")
                else "MATCHED"
                if not residual
                else "UNALLOCATED_BANK_MOVEMENT",
            }
        )
    first, last = data.obligation_month_start, data.obligation_month_end
    month = int(first[:4]) * 12 + int(first[5:]) - 1
    end = int(last[:4]) * 12 + int(last[5:]) - 1
    months_present = {row["period"] for row in expected.values()}
    for current in range(month, end + 1):
        period = f"{current // 12:04}-{current % 12 + 1:02}"
        if period not in months_present:
            rows.append(
                {
                    "id": "missing-month:" + period,
                    "kind": "coverage",
                    "period": period,
                    "state": "MISSING_EXPECTED_MONTH",
                    "currency": data.currency,
                }
            )

    def total(records):
        return sum((Decimal(row["amount"]) for row in records.values()), Decimal(0))

    allocated = sum(used_expected.values(), Decimal(0))
    outflows = sum(
        (
            Decimal(row["amount"]) * sign
            for row in bank.values()
            if Decimal(row["amount"]) * sign > 0
        ),
        Decimal(0),
    )
    inflows = sum(
        (
            -Decimal(row["amount"]) * sign
            for row in bank.values()
            if Decimal(row["amount"]) * sign < 0
        ),
        Decimal(0),
    )
    return {
        **result(
            rows,
            limitations=[
                "Explicit allocations only; no employee identity, payment purpose or bank ownership is inferred from matching amounts",
                *(
                    [
                        "Withholding allocations establish assessed bank cash links, not government challan posting, return filing or beneficiary tax credit"
                    ]
                    if any(row.get("withholding_scope") for row in expected.values())
                    else []
                ),
                "Due dates are assessed source inputs, not a legal deadline calculation; instruction/return files are not payment execution evidence",
                "Corrections and reversals require assessed restated populations; this workflow does not post journals or file returns",
                "Coverage tests declared months only; employee completeness, legal liability and general-ledger reconciliation remain separate procedures",
            ],
        ),
        "execution_mode": "rules_baseline",
        "allocation_controls": {
            "currency": data.currency,
            "expected_amount": str(total(expected)),
            "reported_amount": str(total(reported)),
            "allocated_amount": str(allocated),
            "outstanding_expected": str(total(expected) - allocated),
            "unsettled_reported": str(total(reported) - allocated),
            "bank_outflows": str(outflows),
            "unallocated_bank_outflows": str(outflows - allocated),
            "bank_inflows_not_netted": str(inflows),
        },
        "payment_scope": {
            "account": data.account,
            "currency": data.currency,
            "bank_payment_sign": data.bank_payment_sign,
            "settlement_start": data.settlement_start.isoformat(),
            "through": data.as_of.isoformat(),
            "obligation_month_start": first,
            "obligation_month_end": last,
        },
    }
