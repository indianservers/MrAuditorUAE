"""MSE interest on reviewed facts, dates, conventions and bank allocations.

Reuses the original timing sources and control engine. Principal bank portions
must be explicitly mapped, including zeros; interest payments consume only the
bank outflow left after the original gross principal allocations. Non-cash
principal reductions retain their own supporting document, never a bank receipt.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext

from app.modules.country_workflows.bank_dates import date_details
from app.modules.country_workflows.interest_accrual import MissingRate, RateWindow, accrue
from app.modules.country_workflows.msme_interest_schemas import (
    CONTRACT,
    MSMEBankRate,
    MSMEInterestAllocation,
    MSMEInterestPolicy,
    MSMEPrincipalChange,
    MSMEReportedInterest,
)
from app.modules.country_workflows.msme_payments import calculate as payment_timing

TRACE_LIMIT = 100_000


def supporting_documents(tables):
    return [
        *tables["interest_policies"],
        *tables["bank_rates"],
        *(
            row
            for row in tables["principal_changes"]
            if row["mode"] == "DOCUMENTED_PRINCIPAL_REDUCTION"
        ),
    ]


def calculate(data, tables):
    if data.currency != "INR" or data.tolerance != 0 or data.date_tolerance != 0:
        raise ValueError("MSE interest requires INR and exact source controls")
    with localcontext() as context:
        context.prec = 80
        return _calculate(data, tables)


def _calculate(data, tables):
    core = payment_timing(
        data, {key: tables[key] for key in ("assessments", "invoices", "bank", "allocations")}
    )
    invoices = {row["id"]: row for row in core["rows"]}
    policy_rows = [
        MSMEInterestPolicy.model_validate(row).model_dump(mode="json")
        for row in tables["interest_policies"]
    ]
    rates = [
        MSMEBankRate.model_validate(row).model_dump(mode="json") for row in tables["bank_rates"]
    ]
    changes = [
        MSMEPrincipalChange.model_validate(row).model_dump(mode="json")
        for row in tables["principal_changes"]
    ]
    settlements = [
        MSMEInterestAllocation.model_validate(row).model_dump(mode="json")
        for row in tables["interest_allocations"]
    ]
    observed = [
        MSMEReportedInterest.model_validate(row).model_dump(mode="json")
        for row in tables["reported"]
    ]
    for population in (policy_rows, rates, changes, settlements, observed):
        if len(population) > 5000 or len({row["id"] for row in population}) != len(population):
            raise ValueError("Interest source identities must be unique within bounded populations")
    for row in [*policy_rows, *changes, *settlements, *observed]:
        invoice = invoices.get(row["invoice_id"])
        if invoice is None or any(
            row[key] != invoice[key] for key in ("buyer_id", "supplier_id", "currency")
        ):
            raise ValueError(
                "Interest source belongs to a different invoice, buyer, supplier or currency"
            )
    policies, reports = {}, {}
    for row in policy_rows:
        if row["invoice_id"] in policies:
            raise ValueError(
                "Select one assessed accrual convention per invoice; split conventions are not inferred"
            )
        policies[row["invoice_id"]] = row
    for row in observed:
        if row["as_of"] != data.as_of.isoformat() or row["invoice_id"] in reports:
            raise ValueError(
                "Reported interest needs one independent closing amount per invoice at this cutoff"
            )
        reports[row["invoice_id"]] = row
    grouped_rates = defaultdict(list)
    for row in rates:
        grouped_rates[row["rate_group"]].append(
            RateWindow.model_validate(
                {key: row[key] for key in ("id", "effective_from", "effective_to", "annual_rate")}
            )
        )
    for timeline in grouped_rates.values():
        timeline.sort(key=lambda row: row.effective_from)
        if any(
            left.effective_to >= right.effective_from for left, right in zip(timeline, timeline[1:])
        ):
            raise ValueError("Competing bank-rate windows must be resolved within each rate group")
    original_links = {
        link["allocation_id"]: {**link, "invoice_id": invoice["id"]}
        for invoice in core["rows"]
        for link in invoice["allocations"]
    }
    principal_portions, events, provenance = {}, defaultdict(list), {}
    for row in changes:
        invoice = invoices[row["invoice_id"]]
        if row["mode"] == "BANK_PRINCIPAL_PORTION":
            link = original_links.get(row["principal_allocation_id"])
            if (
                link is None
                or link["invoice_id"] != row["invoice_id"]
                or row["principal_allocation_id"] in principal_portions
            ):
                raise ValueError(
                    "Each original principal allocation needs its own unique invoice-bound portion"
                )
            if Decimal(row["amount"]) > Decimal(link["amount"]):
                raise ValueError(
                    "Assessed interest-principal portion exceeds the original bank allocation"
                )
            principal_portions[row["principal_allocation_id"]] = row
            day, origin = link["payment_date"], "BANK"
        else:
            day, origin = row["day"], "DOCUMENT_ADJUSTMENT"
            if not invoice["invoice_date"] <= day <= data.as_of.isoformat():
                raise ValueError(
                    "A documented principal reduction needs an observed date no earlier than its invoice"
                )
        identifier = "principal:" + row["id"]
        events[row["invoice_id"]].append(
            {
                "id": identifier,
                "day": day,
                "category": "PRINCIPAL",
                "origin": origin,
                "amount": row["amount"],
            }
        )
        provenance[identifier] = row
    bank = {row["id"]: row for row in tables["bank"]}
    sign = Decimal(-1) if data.bank_payment_sign == "debit-negative" else Decimal(1)
    bank_used: defaultdict[str, Decimal] = defaultdict(Decimal)
    for link in original_links.values():
        bank_used[link["transaction_id"]] += Decimal(link["amount"])
    principal_bank_used = dict(bank_used)
    allocation_keys = set()
    for row in settlements:
        key = (row["invoice_id"], row["payment_id"], row["bucket"])
        if key in allocation_keys:
            raise ValueError("Duplicate interest invoice, bank and unpaid-bucket allocation")
        allocation_keys.add(key)
        movement = bank.get(row["payment_id"])
        if movement is None:
            raise ValueError("Interest payment requires a retained scoped bank movement")
        details = date_details(movement)
        if movement.get("is_reversal") or details["booking_date_review_required"]:
            raise ValueError("Interest settlement requires unreversed booked-date evidence")
        outflow = Decimal(movement["amount"]) * sign
        bank_used[row["payment_id"]] += Decimal(row["amount"])
        if outflow <= 0 or bank_used[row["payment_id"]] > outflow:
            raise ValueError(
                "Combined gross principal and interest allocations exceed the bank outflow"
            )
        identifier = "interest:" + row["id"]
        events[row["invoice_id"]].append(
            {
                "id": identifier,
                "day": movement["date"],
                "category": row["bucket"],
                "origin": "BANK",
                "amount": row["amount"],
            }
        )
        provenance[identifier] = {**row, **details, "payment_date": movement["date"]}
    rows, trace_count = [], 0
    for invoice in core["rows"]:
        identifier = invoice["id"]
        policy, report = policies.get(identifier), reports.get(identifier)
        issue, result = None, None
        missing = [
            link["allocation_id"]
            for link in invoice["allocations"]
            if link["allocation_id"] not in principal_portions
        ]
        if invoice["eligibility"] == "UNRESOLVED" or any(
            reason.startswith("PENDING_")
            or reason == "PRE_ACCEPTANCE_TERMS_REQUIRE_SEPARATE_ASSESSMENT"
            for reason in invoice["reasons"]
        ):
            issue = "TIMING_OR_ELIGIBILITY_UNRESOLVED"
        elif policy is None:
            issue = "INTEREST_POLICY_MISSING"
        elif policy["eligible"] != (invoice["eligibility"] == "ELIGIBLE"):
            raise ValueError(
                "Interest policy eligibility differs from the separately assessed supplier population"
            )
        elif missing:
            issue = "PRINCIPAL_PORTIONS_MISSING"
        elif (
            data.settlement_start.isoformat() > policy["history_from"]
            or policy["history_from"] > invoice["invoice_date"]
        ):
            issue = "PAYMENT_HISTORY_SCOPE_INCOMPLETE"
        else:
            basis = Decimal(policy["amount"])
            if basis > Decimal(invoice["amount"]):
                raise ValueError("Assessed interest principal exceeds the retained invoice amount")
            if (
                sum(
                    (
                        Decimal(row["amount"])
                        for row in events[identifier]
                        if row["category"] == "PRINCIPAL"
                    ),
                    Decimal(0),
                )
                > basis
            ):
                raise ValueError(
                    "Principal bank portions and document reductions exceed the assessed interest principal"
                )
            first = policy["interest_start"] if policy["eligible"] else invoice["invoice_date"]
            if (
                not policy["effective_from"]
                <= min(first, data.as_of.isoformat())
                <= max(first, data.as_of.isoformat())
                <= policy["effective_to"]
            ):
                issue = "INTEREST_POLICY_VALIDITY_INCOMPLETE"
            elif not policy["eligible"]:
                if any(row["category"] != "PRINCIPAL" for row in events[identifier]):
                    raise ValueError(
                        "MSE interest payments cannot be allocated to an assessed outside-scope invoice"
                    )
                result = _no_accrual(basis, events[identifier])
            elif invoice["due_date"] is None:
                issue = "TIMING_DUE_DATE_UNRESOLVED"
            else:
                start = date.fromisoformat(first)
                if start < date.fromisoformat(invoice["invoice_date"]):
                    raise ValueError("Assessed first interest day cannot predate its invoice")
                if (
                    policy["start_basis"] == "TIMING_DUE_PLUS_ONE"
                    and start.toordinal() != date.fromisoformat(invoice["due_date"]).toordinal() + 1
                ):
                    raise ValueError(
                        "Timing-based first interest day must immediately follow the retained due date"
                    )
                if start > data.as_of:
                    if any(row["category"] != "PRINCIPAL" for row in events[identifier]):
                        raise ValueError(
                            "Interest settlement cannot precede the assessed first interest day"
                        )
                    result = _no_accrual(basis, events[identifier])
                else:
                    try:
                        result = accrue(
                            basis,
                            {
                                "start": start,
                                "cutoff": data.as_of,
                                **{
                                    key: policy[key]
                                    for key in (
                                        "rest_basis",
                                        "day_basis",
                                        "event_timing",
                                        "rest_rounding",
                                        "rounding",
                                    )
                                },
                                "multiplier": policy["bank_rate_multiplier"],
                                "currency_scale": 2,
                            },
                            grouped_rates[policy["rate_group"]],
                            events[identifier],
                        )
                    except MissingRate as error:
                        issue = "BANK_RATE_COVERAGE_MISSING:" + error.day.isoformat()
        if result:
            trace_count += sum(
                len(result[key]) for key in ("segments", "balance_events", "monthly_rests")
            )
            if trace_count > TRACE_LIMIT:
                raise ValueError(
                    "Interest trace exceeds 100,000 records; select independently controlled smaller populations"
                )
            for event in result["balance_events"]:
                event["source_record"] = provenance[event["id"]]
        expected = result["expected_amount"] if result else None
        difference = (
            Decimal(report["amount"]) - Decimal(expected)
            if report and expected is not None
            else None
        )
        state = issue or (
            "NOT-APPLICABLE"
            if policy
            and not policy["eligible"]
            and (report is None or Decimal(report["amount"]) == 0)
            else "REPORTED_INTEREST_MISSING"
            if report is None
            else "MATCHED"
            if difference == 0
            else "INTEREST_DIFFERENCE"
        )
        rows.append(
            {
                **invoice,
                "timing_state": invoice["timing_state"],
                "timing_reasons": invoice["reasons"],
                "state": state,
                "interest_policy_id": policy["id"] if policy else None,
                "interest_policy": policy,
                "assessed_interest_principal": policy["amount"] if policy else None,
                "missing_principal_allocation_ids": missing,
                "interest_resolution_issue": issue,
                **(result or {}),
                "expected_amount": expected,
                "reported_amount": report["amount"] if report else None,
                "reported_source_id": report["id"] if report else None,
                "difference": str(difference) if difference is not None else None,
                "allocated_bank_interest": str(
                    sum(
                        (
                            Decimal(item["amount"])
                            for item in settlements
                            if item["invoice_id"] == identifier
                        ),
                        Decimal(0),
                    )
                ),
            }
        )
    blocked = any(row["expected_amount"] is None for row in rows)
    return {
        "rows": rows,
        "blocked": blocked,
        "expected_total_complete": not blocked,
        "expected_total": str(
            sum(
                (
                    Decimal(row["expected_amount"])
                    for row in rows
                    if row["expected_amount"] is not None
                ),
                Decimal(0),
            )
        ),
        "exception_count": sum(row["state"] not in {"MATCHED", "NOT-APPLICABLE"} for row in rows),
        "principal_timing_exception_count": core["exception_count"],
        "msme_interest_contract": CONTRACT,
        "msme_payment_contract": core["msme_payment_contract"],
        "msme_source": core["msme_source"],
        "currency": "INR",
        "trace_record_count": trace_count,
        "interest_bank_controls": [
            {
                "transaction_id": identifier,
                "date": movement["date"],
                "account": movement["account"],
                "currency": "INR",
                "original_amount": movement["amount"],
                "gross_principal_allocated": str(principal_bank_used.get(identifier, Decimal(0))),
                "interest_allocated": str(
                    bank_used[identifier] - principal_bank_used.get(identifier, Decimal(0))
                ),
                "total_allocated": str(bank_used[identifier]),
                "unallocated_outflow": str(
                    (
                        Decimal(0)
                        if movement.get("is_reversal")
                        else max(Decimal(movement["amount"]) * sign, Decimal(0))
                    )
                    - bank_used[identifier]
                ),
            }
            for identifier, movement in bank.items()
        ],
        "retained_interest_rate_rows": rates,
        "unreferenced_interest_rate_ids": sorted(
            {row["id"] for row in rates}
            - {segment["rate_source_id"] for row in rows for segment in row.get("segments", [])}
        ),
        "limitations": [
            "Source-assessed MSE principal, supplier eligibility, first interest day, bank rates and accrual conventions only; no current legal or registry qualification is inferred",
            "Monthly rests and explicit three-times bank-rate policy are assessed inputs; calendar/anniversary, day count, payment-day treatment and rounding require retained interpretation",
            "Principal portions and dated non-cash reductions remain separate from gross invoice payments; interest allocations cannot reuse principal-consumed bank cash within this calculation",
            "Interest comparison does not clear retained principal-timing exceptions or establish global cash reservations, Section 22 disclosures, tax deductibility, filings or payment execution",
        ],
    }


def _no_accrual(principal, events):
    return {
        "expected_amount": "0.00",
        "principal_remaining": str(
            principal - sum((Decimal(row["amount"]) for row in events), Decimal(0))
        ),
        "interest_cash_paid": "0",
        "interest_charged_rounded": "0.00",
        "segments": [],
        "balance_events": [{**row, "source_record": {}} for row in events],
        "monthly_rests": [],
    }
