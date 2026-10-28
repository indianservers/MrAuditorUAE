"""MSMED section 2(b)/15 day counts on reviewed facts, not a tax/interest computation."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from app.modules.country_workflows.bank_dates import date_details

CONTRACT = "india-msme-payment-timing/1"
SOURCE = "https://www.indiacode.nic.in/bitstream/123456789/5872/1/a2006-27.pdf"
TEXT_REFERENCE = "https://www.wipo.int/wipolex/en/legislation/details/15841"


def day(value):
    return date.fromisoformat(value) if value else None


def due_dates(invoice, as_of):
    """Missing supporting facts stay pending; no invoice-date acceptance inference."""
    delivery = day(invoice.get("delivery_date"))
    if not delivery or not invoice.get("acceptance_evidence_reference", "").strip():
        return None, None, ["PENDING_ACCEPTANCE_EVIDENCE"], []
    if delivery < date(2006, 10, 2):
        return None, None, ["PENDING_LEGAL_PERIOD_SCOPE"], []
    if delivery > as_of or delivery > date.max - timedelta(days=46):
        raise ValueError(
            "MSE delivery must be observed by the cutoff and permit bounded day counts"
        )
    objection = day(invoice.get("written_objection_date"))
    removed = day(invoice.get("objection_removed_date"))
    if any(value and value > as_of for value in (objection, removed)):
        raise ValueError("Future objection/removal facts cannot support current payment timing")
    warnings = []
    acceptance = delivery
    if objection:
        if not invoice.get("objection_evidence_reference", "").strip():
            return None, None, ["PENDING_WRITTEN_OBJECTION_EVIDENCE"], []
        if objection <= delivery + timedelta(days=15):
            if not removed:
                return None, None, ["PENDING_OBJECTION_REMOVAL"], []
            acceptance = removed
        else:
            warnings.append("LATE_OBJECTION_RETAINED_WITHOUT_ACCEPTANCE_DEFERRAL")
    if acceptance > date.max - timedelta(days=46):
        raise ValueError("MSE acceptance date cannot overflow the bounded payment calendar")
    if invoice["terms_written"]:
        agreed = day(invoice.get("agreed_due_date"))
        if not agreed or not invoice.get("agreement_evidence_reference", "").strip():
            return acceptance, None, ["PENDING_WRITTEN_PAYMENT_TERMS"], warnings
        if agreed < acceptance:
            return acceptance, None, ["PRE_ACCEPTANCE_TERMS_REQUIRE_SEPARATE_ASSESSMENT"], warnings
        cap = acceptance + timedelta(days=45)
        if agreed > cap:
            warnings.append("WRITTEN_TERMS_EXCEED_45_DAY_CAP")
        return acceptance, min(agreed, cap), [], warnings
    return acceptance, acceptance + timedelta(days=15), [], warnings


def calculate(data, tables):
    def index(role):
        rows = {r["id"]: r for r in tables[role]}
        if len(rows) != len(tables[role]):
            raise ValueError("Duplicate MSE source row identity")
        return rows

    assessments, invoices, bank, allocations = [
        index(r) for r in ("assessments", "invoices", "bank", "allocations")
    ]
    for row in [*assessments.values(), *invoices.values()]:
        if row["buyer_id"] != data.msme_buyer_id:
            raise ValueError("MSE source buyer must match the explicit request scope")
    identities = [(r["supplier_id"], r["reference"]) for r in invoices.values()]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate supplier invoice reference in the MSE population")
    for row in invoices.values():
        issued = day(row["invoice_date"])
        if (
            not data.obligation_month_start <= row["invoice_date"][:7] <= data.obligation_month_end
            or issued > data.as_of
        ):
            raise ValueError("MSE invoice date is outside the declared issue-month/cutoff scope")
    for row in bank.values():
        if row["account"] != data.account or row["currency"] != "INR":
            raise ValueError("MSE bank account/currency differs from the explicit INR scope")
        if not data.settlement_start <= day(row["date"]) <= data.as_of:
            raise ValueError("MSE bank movement is outside the declared settlement window")

    used_invoice: defaultdict[str, Decimal] = defaultdict(Decimal)
    used_bank: defaultdict[str, Decimal] = defaultdict(Decimal)
    links = defaultdict(list)
    seen = set()
    sign = Decimal(-1) if data.bank_payment_sign == "debit-negative" else Decimal(1)
    for row in allocations.values():
        key = (row["item_id"], row["payment_id"])
        if key in seen:
            raise ValueError("Duplicate MSE invoice/bank allocation")
        seen.add(key)
        invoice, movement = invoices.get(key[0]), bank.get(key[1])
        if not invoice or not movement or row["currency"] != "INR":
            raise ValueError("MSE allocation requires an existing invoice, bank row and INR")
        details = date_details(movement)
        if movement.get("is_reversal") or details["booking_date_review_required"]:
            raise ValueError(
                "MSE settlement requires unreversed booked-date evidence, not value-date fallback"
            )
        amount, outflow = Decimal(row["amount"]), Decimal(movement["amount"]) * sign
        if amount <= 0 or outflow <= 0:
            raise ValueError("MSE settlement requires positive allocated bank outflows")
        used_invoice[key[0]] += amount
        used_bank[key[1]] += amount
        if used_invoice[key[0]] > Decimal(invoice["amount"]) or used_bank[key[1]] > outflow:
            raise ValueError("MSE invoice or bank movement is overallocated")
        links[key[0]].append(
            {
                "allocation_id": row["id"],
                "transaction_id": key[1],
                "amount": str(amount),
                "payment_date": movement["date"],
                "evidence_reference": row["evidence_reference"],
                "rationale": row["rationale"],
                **details,
            }
        )

    rows, used_assessments = [], set()
    for invoice in invoices.values():
        basis = assessments.get(invoice.get("assessment_id"))
        reasons, warnings = [], []
        acceptance, due = None, None
        if basis:
            used_assessments.add(basis["id"])
            if basis["supplier_id"] != invoice["supplier_id"]:
                raise ValueError("MSE assessment belongs to a different supplier")
        if not basis or basis["eligibility"] == "UNRESOLVED":
            reasons.append("PENDING_SUPPLIER_QUALIFICATION")
        else:
            relevant = [
                invoice["invoice_date"],
                invoice.get("delivery_date") or invoice["invoice_date"],
            ]
            if min(relevant) < basis["scope_start"] or max(relevant) > basis["scope_end"]:
                reasons.append("PENDING_QUALIFICATION_SCOPE")
            elif basis["eligibility"] == "ELIGIBLE":
                acceptance, due, pending, warnings = due_dates(invoice, data.as_of)
                reasons.extend(pending)
        amount = Decimal(invoice["amount"])
        paid = used_invoice[invoice["id"]]
        residual = amount - paid
        late = (
            sum(
                (
                    Decimal(link["amount"])
                    for link in links[invoice["id"]]
                    if due and day(link["payment_date"]) > due
                ),
                Decimal(0),
            )
            if due
            else None
        )
        overdue = residual if due and data.as_of > due else Decimal(0) if due else None
        if "WRITTEN_TERMS_EXCEED_45_DAY_CAP" in warnings:
            reasons.append("WRITTEN_TERMS_EXCEED_CAP")
        if late:
            reasons.append("LATE_PAYMENT")
        if overdue:
            reasons.append("OVERDUE_UNPAID")
        rows.append(
            {
                "id": invoice["id"],
                "buyer_id": invoice["buyer_id"],
                "supplier_id": invoice["supplier_id"],
                "reference": invoice["reference"],
                "invoice_date": invoice["invoice_date"],
                "currency": "INR",
                "amount": str(amount),
                "assessment_source_id": basis["id"] if basis else None,
                "eligibility": basis["eligibility"] if basis else "UNRESOLVED",
                "acceptance_date": acceptance.isoformat() if acceptance else None,
                "due_date": due.isoformat() if due else None,
                "allocated_paid": str(paid),
                "on_time_paid_amount": str(paid - late) if late is not None else None,
                "pre_acceptance_payment_amount": str(
                    sum(
                        (
                            Decimal(link["amount"])
                            for link in links[invoice["id"]]
                            if day(link["payment_date"]) < acceptance
                        ),
                        Decimal(0),
                    )
                )
                if acceptance
                else None,
                "unpaid_amount": str(residual),
                "late_paid_amount": str(late) if late is not None else None,
                "overdue_unpaid_amount": str(overdue) if overdue is not None else None,
                "state": "REVIEW_REQUIRED" if reasons else "MATCHED" if due else "NOT-APPLICABLE",
                "timing_state": "REVIEW_REQUIRED"
                if reasons
                else "NOT_YET_DUE"
                if due and residual
                else "PAID_WITHIN_TIME"
                if due
                else "OUTSIDE_ASSESSED_MSE_SCOPE",
                "reasons": reasons,
                "warnings": warnings,
                "allocations": links[invoice["id"]],
                "retained_invoice_facts": invoice,
                "retained_supplier_assessment": basis,
            }
        )
    return {
        "msme_payment_contract": CONTRACT,
        "msme_source": SOURCE,
        "msme_text_reference": TEXT_REFERENCE,
        "rows": rows,
        "exception_count": sum(bool(r["reasons"]) for r in rows),
        "blocked": any(
            any(
                reason.startswith("PENDING_")
                or reason == "PRE_ACCEPTANCE_TERMS_REQUIRE_SEPARATE_ASSESSMENT"
                for reason in r["reasons"]
            )
            for r in rows
        ),
        "unreferenced_assessment_ids": sorted(set(assessments) - used_assessments),
        "unallocated_bank_rows": [
            {
                "transaction_id": r["id"],
                "original_amount": r["amount"],
                "allocated": str(used_bank[r["id"]]),
                "unallocated_outflow": str(
                    (
                        Decimal(0)
                        if r.get("is_reversal")
                        else max(Decimal(r["amount"]) * sign, Decimal(0))
                    )
                    - used_bank[r["id"]]
                ),
                "is_reversal": r.get("is_reversal", False),
            }
            for r in bank.values()
        ],
        "unassessed_invoice_ids": [
            r["id"] for r in rows if r["due_date"] is None and r["state"] == "REVIEW_REQUIRED"
        ],
        "statutory_calculation_qualified": False,
        "limitations": [
            "Supplier classification, registration, trade eligibility and applicability are independently assessed source facts, not live registry verification",
            "MSMED section 2(b)/15 day counts only; no automatic Section 43B(h)/37(2)(g) tax deduction, Section 16 interest or Section 22 disclosure pack",
            "No invoice-date acceptance inference, unknown-to-zero conversion, cross-invoice netting or automatic credit-note setoff; source scope is explicitly declared",
            "Bank allocations are analytical links within this review, not global cash reservations, accounting postings or payment execution",
        ],
    }
