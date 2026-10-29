"""Annual MSE tax bridge on reviewed expense, opening-tax and settlement facts.

Never substitute closing interest for the P&L charge, count a prior allowed
amount twice, or use the return-filing date to rescue an overdue MSE expense.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from types import SimpleNamespace
from typing import Any, TypedDict

from app.modules.country_workflows.msme_payments import calculate as payment_timing
from app.modules.country_workflows.msme_tax_schemas import CONTRACT, METRICS, ROLES, ROW_TYPES

ZERO = Decimal(0)


class MetricTotal(TypedDict):
    expected_amount: str
    expected_complete: bool
    reported_amount: str
    reported_complete: bool


def supporting_documents(tables):
    return [
        *tables["tax_bases"],
        *tables["interest_pnl"],
        *(row for row in tables["tax_settlements"] if row["mode"] != "BANK_ALLOCATION_PORTION"),
    ]


def period(data):
    start, end, observed = data.tax_year_start, data.as_of, data.tax_observed_through
    if type(start) is not date or type(observed) is not date or type(end) is not date:
        raise ValueError("Declare explicit annual tax and settlement observation dates")
    if (
        start.year < 2023
        or start.year >= 9999
        or (start.month, start.day) != (4, 1)
        or end != date(start.year + 1, 3, 31)
    ):
        raise ValueError("MSE annual tax needs one April-to-March year from 2023-24 onward")
    if observed < end or (observed - start).days > 36600:
        raise ValueError("Observation must reach year end within the bounded evidence window")
    return start, end, observed, "2025:37(2)(g)" if start >= date(2026, 4, 1) else "1961:43B(h)"


def calculate(data, tables):
    if data.currency != "INR" or data.tolerance != 0 or data.date_tolerance != 0:
        raise ValueError("MSE annual tax requires exact INR monetary and date controls")
    with localcontext() as context:
        context.prec = 80
        return _calculate(data, tables)


def _calculate(data, tables):
    start, end, observed, reference = period(data)
    core = payment_timing(
        SimpleNamespace(**{**vars(data), "as_of": observed}),
        {role: tables[role] for role in ("assessments", "invoices", "bank", "allocations")},
    )
    invoices = {row["id"]: row for row in core["rows"]}
    for row in invoices.values():
        if row["invoice_date"] > end.isoformat():
            raise ValueError(
                "Select the year-end invoice population, not later observation-period invoices"
            )
    populations = {}
    for role in ("tax_bases", "tax_settlements", "interest_pnl", "reported"):
        rows = [
            ROW_TYPES[ROLES[role]].model_validate(row).model_dump(mode="json")
            for row in tables[role]
        ]
        if len(rows) > 5000 or len({row["id"] for row in rows}) != len(rows):
            raise ValueError("Tax source identities must be unique within bounded populations")
        for row in rows:
            invoice = invoices.get(row["invoice_id"])
            if invoice is None or any(
                row[key] != invoice[key] for key in ("buyer_id", "supplier_id", "currency")
            ):
                raise ValueError(
                    "Tax record belongs to another invoice, buyer, supplier or currency"
                )
        populations[role] = rows
    bases: dict[str, Any] = {}
    pnl: dict[str, Any] = {}
    reported = {}
    for role, target in (("tax_bases", bases), ("interest_pnl", pnl)):
        for row in populations[role]:
            if row["invoice_id"] in target:
                raise ValueError("Select one assessed tax basis and P&L record per invoice")
            if role == "interest_pnl" and row["tax_year_start"] != start.isoformat():
                raise ValueError("P&L interest belongs to a different tax year")
            target[row["invoice_id"]] = row
    for row in populations["reported"]:
        key = (row["invoice_id"], row["metric"])
        if (
            key in reported
            or row["tax_year_start"] != start.isoformat()
            or row["as_of"] != end.isoformat()
        ):
            raise ValueError(
                "Select one reported amount per invoice/metric at the exact tax-year cutoff"
            )
        reported[key] = row
    original = {
        link["allocation_id"]: {**link, "invoice_id": invoice["id"]}
        for invoice in core["rows"]
        for link in invoice["allocations"]
    }
    portions, events = {}, defaultdict(list)
    other_identities = set()
    for row in populations["tax_settlements"]:
        if row["mode"] in {"BANK_ALLOCATION_PORTION", "ASSESSED_BANK_ADVANCE_APPLICATION"}:
            link = original.get(row["principal_allocation_id"])
            if (
                link is None
                or link["invoice_id"] != row["invoice_id"]
                or row["principal_allocation_id"] in portions
            ):
                raise ValueError("Each tax portion needs its own original invoice-bound allocation")
            if Decimal(row["amount"]) > Decimal(link["amount"]):
                raise ValueError("Tax-basis portion exceeds the original gross bank allocation")
            portions[row["principal_allocation_id"]] = row
            day = (
                row["day"]
                if row["mode"] == "ASSESSED_BANK_ADVANCE_APPLICATION"
                else link["payment_date"]
            )
            if not link["payment_date"] <= day <= observed.isoformat():
                raise ValueError(
                    "Assessed advance application cannot precede its original bank movement or follow the observation cutoff"
                )
            source = {**row, "original_bank_allocation": link}
        else:
            identity = (
                row["invoice_id"],
                row["day"],
                row["source_evidence_version_id"],
                row["evidence_reference"],
            )
            if identity in other_identities:
                raise ValueError("Duplicate independently evidenced other settlement")
            other_identities.add(identity)
            day, source = row["day"], row
            if not data.settlement_start.isoformat() <= day <= observed.isoformat():
                raise ValueError(
                    "Other settlements must belong to the declared observed history window"
                )
        events[row["invoice_id"]].append(
            {
                **source,
                "payment_day": day,
                "observation_phase": "BEFORE_YEAR"
                if day < start.isoformat()
                else "DURING_YEAR"
                if day <= end.isoformat()
                else "AFTER_YEAR",
            }
        )
    rows, invoice_details = [], []
    for identifier, invoice in invoices.items():
        basis, interest = bases.get(identifier), pnl.get(identifier)
        trace = sorted(events[identifier], key=lambda row: (row["payment_day"], row["id"]))
        issue = None
        current_disallowed = prior_release = closing_carry = None
        missing = [
            link["allocation_id"]
            for link in invoice["allocations"]
            if link["allocation_id"] not in portions
        ]
        unresolved_timing = any(
            reason.startswith("PENDING_")
            or reason == "PRE_ACCEPTANCE_TERMS_REQUIRE_SEPARATE_ASSESSMENT"
            for reason in invoice["reasons"]
        )
        if invoice["eligibility"] == "UNRESOLVED" or unresolved_timing:
            issue = "SUPPLIER_OR_TIMING_FACTS_UNRESOLVED"
        elif basis is None:
            issue = "ASSESSED_TAX_BASIS_MISSING"
        elif missing:
            issue = "EXPLICIT_BANK_TAX_PORTIONS_MISSING"
        elif basis["otherwise_allowable"] is None:
            issue = "OTHERWISE_ALLOWABLE_ASSESSMENT_UNRESOLVED"
        elif basis["tax_reference"] != reference:
            raise ValueError(
                "Tax reference differs from the selected legacy/current Indian tax year"
            )
        elif (
            not basis["effective_from"]
            <= start.isoformat()
            <= end.isoformat()
            <= basis["effective_to"]
        ):
            issue = "TAX_POLICY_COVERAGE_INCOMPLETE"
        elif (
            not data.settlement_start.isoformat()
            <= basis["history_from"]
            <= invoice["invoice_date"]
        ):
            issue = "COMPLETE_SETTLEMENT_HISTORY_NOT_ESTABLISHED"
        else:
            amount = Decimal(basis["amount"])
            opening = [
                Decimal(basis[key])
                for key in (
                    "opening_paid_basis",
                    "opening_disallowed_basis",
                    "opening_previously_allowed_unpaid",
                )
            ]
            if amount > Decimal(invoice["amount"]):
                raise ValueError("Assessed tax basis exceeds gross original invoice value")
            excluded_bank_portions = sum(
                (
                    Decimal(link["amount"]) - Decimal(portions[link["allocation_id"]]["amount"])
                    for link in invoice["allocations"]
                ),
                ZERO,
            )
            if excluded_bank_portions > Decimal(invoice["amount"]) - amount:
                raise ValueError(
                    "Excluded bank payment portions exceed the invoice amount outside its assessed tax basis"
                )
            if basis["liability_tax_year_start"] > start.isoformat():
                raise ValueError(
                    "Future liability years need a separate expense-recognition assessment"
                )
            current = basis["liability_tax_year_start"] == start.isoformat()
            if current and any(opening) or not current and sum(opening, ZERO) != amount:
                raise ValueError(
                    "Opening paid, disallowed and previously allowed balances must reconcile independently to the prior tax basis; current expenses have zero opening balances"
                )
            if basis["liability_tax_year_start"] < "2023-04-01" and opening[1]:
                raise ValueError(
                    "This procedure cannot create a pre-2023-24 MSE disallowance carry"
                )
            if opening[1]:
                prior_reference = (
                    "2025:37(2)(g)"
                    if basis["liability_tax_year_start"] >= "2026-04-01"
                    else "1961:43B(h)"
                )
                if basis["prior_disallowance_reference"] != prior_reference:
                    raise ValueError(
                        "Prior disallowance reference must match its original liability tax year"
                    )
            elif basis["prior_disallowance_reference"] is not None:
                raise ValueError(
                    "Do not claim a prior disallowance reference without an opening disallowed balance"
                )
            if any(row["qualifies_as_payment"] is None for row in trace):
                issue = "OTHER_SETTLEMENT_TAX_TREATMENT_UNRESOLVED"
            qualified = [row for row in trace if row["qualifies_as_payment"] is True]
            if sum((Decimal(row["amount"]) for row in qualified), ZERO) > amount:
                raise ValueError("Qualifying settlements exceed the assessed tax principal basis")
            if current:
                if any(row["bucket"] != "CURRENT_EXPENSE" for row in qualified):
                    raise ValueError(
                        "Current-year expenses cannot use prior-year allocation buckets"
                    )
                if any(
                    row["payment_day"] < start.isoformat()
                    and row["mode"] == "BANK_ALLOCATION_PORTION"
                    for row in qualified
                ):
                    issue = "EARLIER_ADVANCE_REQUIRES_APPROPRIATION_ASSESSMENT"
                due = invoice["due_date"]
                if invoice["eligibility"] == "ELIGIBLE" and due is None:
                    issue = "PAYMENT_DEADLINE_UNRESOLVED"
                allowed = sum(
                    (
                        Decimal(row["amount"])
                        for row in qualified
                        if row["payment_day"] <= end.isoformat()
                        or due
                        and row["payment_day"] <= due
                    ),
                    ZERO,
                )
                unpaid = amount - sum((Decimal(row["amount"]) for row in qualified), ZERO)
                if due and observed.isoformat() <= due and due > end.isoformat() and unpaid:
                    issue = "OBSERVATION_DOES_NOT_RESOLVE_POST_YEAR_DEADLINE"
                if issue is None:
                    current_disallowed = (
                        amount - allowed
                        if invoice["eligibility"] == "ELIGIBLE" and basis["otherwise_allowable"]
                        else ZERO
                    )
                    prior_release, closing_carry = ZERO, current_disallowed
            else:
                historical = sum(
                    (
                        Decimal(row["amount"])
                        for row in qualified
                        if row["payment_day"] < start.isoformat()
                    ),
                    ZERO,
                )
                if historical != opening[0]:
                    issue = "OPENING_PAID_BASIS_DOES_NOT_MATCH_OBSERVED_HISTORY"
                if any(
                    (row["payment_day"] < start.isoformat()) != (row["bucket"] == "HISTORICAL_PAID")
                    or row["bucket"] == "CURRENT_EXPENSE"
                    for row in qualified
                ):
                    raise ValueError(
                        "Prior-year expenses need explicit historical/disallowed/already-allowed buckets tied to actual dates"
                    )
                for bucket, balance in (
                    ("PRIOR_DISALLOWED", opening[1]),
                    ("PRIOR_ALREADY_ALLOWED", opening[2]),
                ):
                    if (
                        sum(
                            (
                                Decimal(row["amount"])
                                for row in qualified
                                if row["bucket"] == bucket
                            ),
                            ZERO,
                        )
                        > balance
                    ):
                        raise ValueError(
                            "A settlement bucket exceeds its independently assessed opening balance"
                        )
                if invoice["eligibility"] != "ELIGIBLE" and opening[1]:
                    issue = "PRIOR_DISALLOWANCE_ELIGIBILITY_REQUIRES_REVIEW"
                if basis["liability_tax_year_start"] >= "2023-04-01" and opening[2]:
                    already_allowed = [
                        row for row in qualified if row["bucket"] == "PRIOR_ALREADY_ALLOWED"
                    ]
                    due = invoice["due_date"]
                    unresolved_allowed = opening[2] - sum(
                        (Decimal(row["amount"]) for row in already_allowed), ZERO
                    )
                    if (
                        not due
                        or any(row["payment_day"] > due for row in already_allowed)
                        or (unresolved_allowed and observed.isoformat() > due)
                    ):
                        issue = "PRIOR_ALLOWANCE_WITHOUT_TIMELY_SETTLEMENT_REQUIRES_TAX_REVIEW"
                if issue is None:
                    current_disallowed = ZERO
                    prior_release = sum(
                        (
                            Decimal(row["amount"])
                            for row in qualified
                            if row["bucket"] == "PRIOR_DISALLOWED"
                            and row["payment_day"] <= end.isoformat()
                        ),
                        ZERO,
                    )
                    closing_carry = opening[1] - prior_release
        interest_issue, expected_interest = None, None
        if interest is None:
            interest_issue = "CURRENT_PNL_INTEREST_ASSESSMENT_MISSING"
        elif interest["section23_applies"] is None:
            interest_issue = "SECTION23_PNL_TREATMENT_UNRESOLVED"
        elif interest["section23_applies"] and Decimal(interest["amount"]) < 0:
            interest_issue = "INTEREST_NET_CREDIT_REQUIRES_SEPARATE_TAX_TREATMENT"
        elif interest["section23_applies"] and (
            invoice["eligibility"] != "ELIGIBLE" or unresolved_timing or not invoice["due_date"]
        ):
            interest_issue = "STATUTORY_INTEREST_SCOPE_REQUIRES_REVIEW"
        elif (
            interest["section23_applies"]
            and Decimal(interest["amount"]) > 0
            and (
                invoice["due_date"] >= end.isoformat()
                or sum(
                    (
                        Decimal(link["amount"])
                        for link in invoice["allocations"]
                        if link["payment_date"] <= invoice["due_date"]
                    ),
                    ZERO,
                )
                == Decimal(invoice["amount"])
            )
        ):
            interest_issue = "PNL_INTEREST_SCOPE_CONTRADICTS_PRINCIPAL_TIMING"
        else:
            expected_interest = (
                Decimal(interest["amount"]) if interest["section23_applies"] else ZERO
            )
        expected = dict(
            zip(METRICS, (expected_interest, current_disallowed, prior_release), strict=True)
        )
        for metric, value in expected.items():
            report = reported.get((identifier, metric))
            difference = Decimal(report["amount"]) - value if report and value is not None else None
            problem = interest_issue if metric == METRICS[0] else issue
            rows.append(
                {
                    "id": identifier + ":" + metric,
                    "invoice_id": identifier,
                    "supplier_id": invoice["supplier_id"],
                    "reference": invoice["reference"],
                    "metric": metric,
                    "currency": "INR",
                    "tax_year_start": start.isoformat(),
                    "as_of": end.isoformat(),
                    "expected_amount": str(value) if value is not None else None,
                    "reported_amount": report["amount"] if report else None,
                    "difference": str(difference) if difference is not None else None,
                    "state": problem
                    or (
                        "REPORTED_TAX_AMOUNT_MISSING"
                        if report is None
                        else "MATCHED"
                        if difference == 0
                        else "TAX_DIFFERENCE"
                    ),
                }
            )
        invoice_details.append(
            {
                **invoice,
                "tax_basis": basis,
                "interest_pnl_assessment": interest,
                "tax_settlements": trace,
                "missing_bank_tax_portions": missing,
                "principal_tax_issue": issue,
                "interest_pnl_issue": interest_issue,
                "closing_disallowed_carry": str(closing_carry)
                if closing_carry is not None
                else None,
            }
        )
    totals: dict[str, MetricTotal] = {}
    for metric in METRICS:
        selected = [row for row in rows if row["metric"] == metric]
        complete = all(row["expected_amount"] is not None for row in selected)
        totals[metric] = {
            "expected_amount": str(
                sum(
                    (
                        Decimal(row["expected_amount"])
                        for row in selected
                        if row["expected_amount"] is not None
                    ),
                    ZERO,
                )
            ),
            "expected_complete": complete,
            "reported_amount": str(
                sum(
                    (
                        Decimal(row["reported_amount"])
                        for row in selected
                        if row["reported_amount"] is not None
                    ),
                    ZERO,
                )
            ),
            "reported_complete": all(row["reported_amount"] is not None for row in selected),
        }
    complete = all(value["expected_complete"] for value in totals.values())
    net = (
        Decimal(totals[METRICS[0]]["expected_amount"])
        + Decimal(totals[METRICS[1]]["expected_amount"])
        - Decimal(totals[METRICS[2]]["expected_amount"])
        if complete
        else None
    )
    return {
        "rows": rows,
        "blocked": not complete,
        "exception_count": sum(row["state"] != "MATCHED" for row in rows),
        "msme_tax_contract": CONTRACT,
        "msme_payment_contract": core["msme_payment_contract"],
        "tax_reference": reference,
        "tax_year_start": start.isoformat(),
        "as_of": end.isoformat(),
        "tax_observed_through": observed.isoformat(),
        "timing_observed_through": observed.isoformat(),
        "currency": "INR",
        "tax_totals": totals,
        "expected_total_complete": complete,
        "net_expected_tax_adjustment": str(net) if net is not None else None,
        "invoice_tax_details": invoice_details,
        "principal_timing_exception_count": core["exception_count"],
        "unallocated_bank_rows": core["unallocated_bank_rows"],
        "form26_targets": {METRICS[0]: "33(a)", METRICS[1]: "33(b)", METRICS[2]: "33(c)"}
        if reference.startswith("2025:")
        else None,
        "limitations": [
            "Source-assessed otherwise-allowable expense and signed P&L interest bases only; original gross invoices and closing interest are not substituted",
            "Net P&L interest credits are retained for separate tax treatment, not a negative Form 26 interest disallowance",
            "Current-year late amounts use actual payment timing; the return-filing date is not a rescue deadline for this MSE rule",
            "Prior disallowed and previously allowed buckets are separate; an already allowed sum is never deducted twice",
            "Other settlements, including withholding, netting and advances, require explicit retained tax-treatment assessment; no cash equivalence is inferred",
            "Post-year observations do not change the annual cutoff; an unobserved post-year deadline remains unresolved",
            "A zero MSE adjustment does not establish deductibility under other provisions, supplier authenticity, global cash reservation, complete disclosures, signing or filing",
        ],
    }
