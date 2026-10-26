"""Explicit recognition allocations and independently supplied ledger postings."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from app.modules.jurisdictions.profiles import Strict

ID = Annotated[str, Field(min_length=1, max_length=120)]
Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]


class CutoffIdentity(Strict):
    id: ID
    document_id: ID
    counterparty: ID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Money
    evidence_reference: ID

    @model_validator(mode="after")
    def exact_identifiers(self):
        for name in ("id", "document_id", "counterparty", "evidence_reference"):
            value = getattr(self, name)
            if not value.strip() or value != value.strip():
                raise ValueError("Cutoff links require exact nonblank identifiers and references")
        return self


class CutoffRecognition(CutoffIdentity):
    recognition_date: date
    recognition_basis: Literal["goods-received", "service-performed", "reviewed-accrual"]


class CutoffPosting(CutoffIdentity):
    allocation_id: ID
    account: ID
    posting_date: date
    journal_reference: ID

    @model_validator(mode="after")
    def posting_identifiers(self):
        for value in (self.allocation_id, self.account, self.journal_reference):
            if not value.strip() or value != value.strip():
                raise ValueError("Posting allocation and journal references must be exact")
        return self


def compare(data, tables, legacy):
    from app.modules.country_workflows.audit_calculations import result

    documents = {row["id"]: row for row in tables["documents"]}
    scheduled = {
        key: row
        for key, row in documents.items()
        if row.get("recognition_mode", "single-date") == "explicit-schedule"
    }
    rows = legacy(
        data,
        {
            "documents": [
                row
                for row in documents.values()
                if row.get("recognition_mode", "single-date") == "single-date"
            ]
        },
    )["rows"]
    controls: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    blocked = False
    if not {"recognitions", "postings"} <= set(tables):
        if {"recognitions", "postings"} & set(tables):
            raise ValueError(
                "Select both recognition and posting schedules, including an explicitly controlled nil posting source"
            )
        for identifier, document in scheduled.items():
            rows.append(
                {
                    "id": "cutoff-document:" + identifier,
                    "document_source_id": identifier,
                    "counterparty": document["counterparty"],
                    "currency": document["currency"],
                    "amount": document["amount"],
                    "state": "CUTOFF_ALLOCATION_SOURCES_MISSING",
                }
            )
        return {
            **result(rows, bool(scheduled)),
            "cutoff_schedule_contract": "explicit-cutoff-schedules/1",
            "cutoff_document_controls": controls,
            "cutoff_posting_links": links,
        }
    if any(
        date.fromisoformat(doc["invoice_date"]) > data.review_through for doc in scheduled.values()
    ):
        raise ValueError("Cutoff invoice evidence extends beyond the review window")
    identities = [
        (
            row["counterparty"],
            row["reference"],
            row["currency"],
            row.get("document_kind", "invoice"),
        )
        for row in documents.values()
    ]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate cutoff document identity in the supplied population")
    allocations = {row["id"]: row for row in tables["recognitions"]}
    by_document = defaultdict(list)
    postings = defaultdict(list)
    for allocation in allocations.values():
        document = scheduled.get(allocation["document_id"])
        if document is None or any(
            allocation[field] != document[field] for field in ("counterparty", "currency")
        ):
            raise ValueError(
                "Recognition allocation must match an explicit-schedule document, party and currency"
            )
        amount = Decimal(allocation["amount"])
        if (document["document_kind"] == "invoice" and amount < 0) or (
            document["document_kind"] == "credit-note" and amount > 0
        ):
            raise ValueError("Recognition allocation sign must match its invoice or credit note")
        by_document[allocation["document_id"]].append(allocation)
    for posting in tables["postings"]:
        allocation = allocations.get(posting["allocation_id"])
        if allocation is None or any(
            posting[field] != allocation[field]
            for field in ("document_id", "counterparty", "currency")
        ):
            raise ValueError(
                "Posting must identify its exact allocation, document, party and currency"
            )
        if date.fromisoformat(posting["posting_date"]) > data.review_through:
            raise ValueError("Cutoff ledger posting is after the review window")
        postings[posting["allocation_id"]].append(posting)
        links.append(
            {
                "posting_source_id": posting["id"],
                **{
                    field: posting[field]
                    for field in (
                        "allocation_id",
                        "document_id",
                        "counterparty",
                        "currency",
                        "amount",
                        "account",
                        "posting_date",
                        "journal_reference",
                        "evidence_reference",
                    )
                },
            }
        )
    for identifier, document in scheduled.items():
        declared = Decimal(document["amount"])
        allocated = sum((Decimal(row["amount"]) for row in by_document[identifier]), Decimal(0))
        complete = bool(by_document[identifier]) and allocated == declared
        blocked |= not complete
        controls.append(
            {
                "document_source_id": identifier,
                "counterparty": document["counterparty"],
                "reference": document["reference"],
                "currency": document["currency"],
                "document_kind": document["document_kind"],
                "document_amount": str(declared),
                "allocated_amount": str(allocated),
                "difference": str(allocated - declared),
                "allocation_rows": len(by_document[identifier]),
                "state": "MATCHED" if complete else "CUTOFF_ALLOCATION_CONTROL_DIFFERENCE",
            }
        )
        if not complete:
            rows.append({"id": "cutoff-document:" + identifier, **controls[-1]})
        for allocation in by_document[identifier]:
            recognition = date.fromisoformat(allocation["recognition_date"])
            amount = Decimal(allocation["amount"])
            expected = amount if data.period_start <= recognition <= data.as_of else Decimal(0)
            entries = postings[allocation["id"]]
            current = sum(
                (
                    Decimal(row["amount"])
                    for row in entries
                    if data.period_start <= date.fromisoformat(row["posting_date"]) <= data.as_of
                ),
                Decimal(0),
            )
            subsequent = sum(
                (
                    Decimal(row["amount"])
                    for row in entries
                    if data.as_of < date.fromisoformat(row["posting_date"]) <= data.review_through
                ),
                Decimal(0),
            )
            prior = sum(
                (
                    Decimal(row["amount"])
                    for row in entries
                    if date.fromisoformat(row["posting_date"]) < data.period_start
                ),
                Decimal(0),
            )
            delta = current - expected
            state = (
                "MATCHED"
                if delta == 0 or (current * expected > 0 and abs(delta) <= data.tolerance)
                else "WRONG_PERIOD"
                if expected == 0 or (current == 0 and prior != 0)
                else "LATE_RECOGNITION"
                if expected != 0 and current == 0 and subsequent == expected
                else "UNRECORDED_CREDIT"
                if expected < 0 and current == 0
                else "UNRECORDED_LIABILITY"
                if expected > 0 and current == 0
                else "CUTOFF_POSTING_DIFFERENCE"
            )
            rows.append(
                {
                    "id": "cutoff-allocation:" + allocation["id"],
                    "kind": "cutoff-allocation",
                    "document_source_id": identifier,
                    "allocation_source_id": allocation["id"],
                    "counterparty": document["counterparty"],
                    "reference": document["reference"],
                    "currency": document["currency"],
                    "amount": str(amount),
                    "recognition_date": allocation["recognition_date"],
                    "recognition_basis": allocation["recognition_basis"],
                    "recognition_evidence_reference": allocation["evidence_reference"],
                    "expected_period_amount": str(expected),
                    "posted_period_amount": str(current),
                    "subsequent_posted_amount": str(subsequent),
                    "prior_posted_amount": str(prior),
                    "difference": str(delta),
                    "posting_source_ids": [row["id"] for row in entries],
                    "allocation_control_complete": complete,
                    "recognition_timing": "AFTER_REVIEW_WINDOW_ASSESSED_SCHEDULE"
                    if recognition > data.review_through
                    else "WITHIN_OR_BEFORE_REVIEW_WINDOW",
                    "state": state,
                }
            )
    return {
        **result(
            rows,
            blocked,
            [
                "Recognition schedules are explicit professional assessments; no service-period proration, tax treatment or legal recognition is inferred",
                "Posting amounts and reversals are retained separately and compared in the declared reporting period; net agreement does not authenticate the ledger",
                "Future recognition allocations are assessed schedules, not evidence that future goods or services have occurred",
                "Supplied invoice and ledger populations do not establish completeness of liabilities or credits",
                "Only supplied expense-recognition postings are compared; prepayment, payable, tax and cash control accounts require separate reconciliation",
            ],
        ),
        "cutoff_schedule_contract": "explicit-cutoff-schedules/1",
        "cutoff_document_controls": controls,
        "cutoff_posting_links": links,
    }
