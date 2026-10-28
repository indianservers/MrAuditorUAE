"""Reviewed gratuity to expected settlement rows; never a payment instruction."""

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from typing import Annotated
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator
from starlette.concurrency import run_in_threadpool

from app.modules.country_workflows.benefit_settlement_scope import (
    BenefitSettlementScope,
    Identifier,
)
from app.modules.country_workflows.schemas import Obligation
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "benefit-settlement-obligations/1"
Amount = Annotated[Decimal, Field(ge=0, max_digits=36, decimal_places=8, allow_inf_nan=False)]


class BenefitSettlementSelection(Strict):
    result_row_id: Identifier
    due_date: date
    due_date_reference: str = Field(min_length=3, max_length=200)

    @model_validator(mode="after")
    def reference(self):
        if len(self.due_date_reference.strip()) < 3:
            raise ValueError("Reference the retained settlement due-date evidence")
        return self


class BenefitSettlementInput(Strict):
    result_id: UUID
    employer_registration: Identifier
    settlement_evidence_version_id: UUID
    selections: list[BenefitSettlementSelection] = Field(min_length=1, max_length=5000)
    expected_rows: int = Field(ge=1, le=5000)
    control_total: Amount
    label: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def controlled(self):
        ids = [item.result_row_id for item in self.selections]
        if len(ids) != len(set(ids)) or len(ids) != self.expected_rows:
            raise ValueError(
                "Select distinct benefit rows matching the independent row-count control"
            )
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess employer, employee identities, settlement scope and due dates")
        return self


def source_rows(body, data):
    if body.get("workflow") != "uae-benefit-review" or body.get("blocked"):
        raise ValueError("Select a resolved UAE benefit review")
    original = body.get("rows", [])
    indexed = {row["id"]: row for row in original}
    if not original or len(indexed) != len(original) or len(original) > 5000:
        raise ValueError("Benefit result must contain a bounded, uniquely identified population")
    rows = []
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        total = Decimal(0)
        for selection in data.selections:
            row = indexed.get(selection.result_row_id)
            if row is None:
                raise ValueError("Selected employee is missing from the reviewed benefit result")
            if (
                row.get("state") not in {"MATCHED", "BENEFIT_DIFFERENCE"}
                or row.get("expected_benefit") is None
                or row.get("currency") != "AED"
                or row.get("work_model_constant_for_service") is not True
                or not row.get("rule_source_id")
                or not row.get("rule_document_version_id")
                or not row.get("rule_document_sha256")
            ):
                raise ValueError(
                    "Every selected benefit needs a resolved AED computation and retained rule provenance"
                )
            try:
                scope = BenefitSettlementScope.model_validate(
                    {field: row.get(field) for field in BenefitSettlementScope.model_fields}
                )
                amount = Decimal(row["expected_benefit"])
            except (ValueError, TypeError, InvalidOperation):
                raise ValueError(
                    "Retain dated gratuity scope; regenerate older undated benefit results"
                ) from None
            if not amount.is_finite() or amount < 0:
                raise ValueError("Expected gratuity must be a finite non-negative amount")
            canonical = Obligation(
                id="benefit:" + fingerprint({"result": str(data.result_id), "row": row["id"]})[:32],
                registration=data.employer_registration,
                subject=row["id"],
                period=scope.service_end.strftime("%Y-%m"),
                component="BENEFIT:GRATUITY",
                currency="AED",
                amount=amount,
                due_date=selection.due_date,
                benefit_scope=scope,
            ).model_dump(mode="json")
            rows.append(
                {
                    **canonical,
                    "source_result_row_id": row["id"],
                    "rule_source_id": row["rule_source_id"],
                    "rule_document_version_id": row["rule_document_version_id"],
                    "rule_document_sha256": row["rule_document_sha256"],
                    "due_date_reference": selection.due_date_reference.strip(),
                    "settlement_scope_basis": "DECLARED_RETAINED_DOCUMENT_ASSESSMENT",
                    "amount_basis": "REVIEWED_EXPECTED_BENEFIT_NOT_DECLARED_PAID_AMOUNT",
                }
            )
            total += amount
    if total != data.control_total:
        raise ValueError("Independent expected gratuity amount control does not agree")
    selected = {item.result_row_id for item in data.selections}
    excluded = [
        {"source_result_row_id": row["id"], "reason": "UNSELECTED_BENEFIT_ROW"}
        for row in original
        if row["id"] not in selected
    ]
    return rows, {"AED": str(total)}, excluded


async def derive(db, ctx, eng, data):
    from app.modules.country_workflows.service import payroll_rule_documents
    from app.modules.intelligence import service as intelligence
    from app.modules.jurisdictions.workspace import resolved

    parent = await intelligence.event(db, ctx, eng.id, data.result_id, True)
    if parent.kind != "country-workflow" or parent.body.get("review_status") != "REVIEWED":
        raise HTTPException(409, "Select a current independently reviewed gratuity result")
    binding, _ = await resolved(db, ctx, eng)
    if binding.country != "AE" or parent.body.get("workflow") != "uae-benefit-review":
        raise HTTPException(
            422, "Gratuity settlement sources require a UAE benefit result and engagement"
        )
    try:
        rows, totals, excluded = await run_in_threadpool(source_rows, parent.body, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    document, _ = await intelligence.evidence(db, ctx, eng, data.settlement_evidence_version_id)
    contributors = {str(ctx.user_id), *parent.body.get("contributors", [str(parent.created_by)])}
    if document.created_by is not None:
        contributors.add(str(document.created_by))
    receipts = await payroll_rule_documents(
        db,
        ctx,
        eng,
        [{"source_evidence_version_id": str(document.id), "source_sha256": document.sha256}],
        label="Gratuity settlement scope and due-date",
        contributors=contributors,
    )
    return (
        parent,
        rows,
        totals,
        excluded,
        [intelligence.event_receipt(parent), *receipts],
        sorted(contributors),
    )


async def prepare(db, ctx, eng, data, request_id):
    from app.modules.intelligence import service as intelligence

    parent, rows, totals, excluded, receipts, contributors = await derive(db, ctx, eng, data)
    return await intelligence.append(
        db,
        ctx,
        eng,
        "workflow-source",
        {
            "table_type": "obligations",
            "rows": rows,
            "row_count": len(rows),
            "control_totals": totals,
            "title": data.label,
            "review_status": "UNVERIFIED",
            "parser_version": CONTRACT,
            "allowed_source_roles": ["expected"],
            "allowed_workflows": ["obligation-bank-allocations"],
            "source_identity": "benefit-settlement:" + str(parent.root_id),
            "source_sha256": fingerprint(rows),
            "contributors": contributors,
            "population_completeness": "SELECTED_REVIEWED_GRATUITY_ROWS_ONLY",
            "native_metadata": data.model_dump(mode="json"),
            "excluded_rows": excluded,
            "limitations": [
                "Expected final gratuity only; declared paid benefit is not bank evidence or deducted from the expectation",
                "Employer, employee/service identity and due dates require independent retained-document assessment",
                "Only selected constant-model gratuity spans are covered; no alternative scheme or transition qualification",
                "Use independent reported settlement and allocated bank evidence; no payment instruction or global cash reservation is created",
            ],
        },
        receipts,
        request_id,
    )


async def verify(db, ctx, eng, source, contributors):
    data = BenefitSettlementInput.model_validate(source["native_metadata"])
    _, rows, totals, excluded, receipts, authors = await derive(db, ctx, eng, data)
    if (
        rows != source["rows"]
        or len(rows) != source["row_count"]
        or totals != source["control_totals"]
        or excluded != source["excluded_rows"]
        or fingerprint(rows) != source["source_sha256"]
    ):
        raise HTTPException(
            409, "Expected gratuity no longer agrees with the reviewed benefit result"
        )
    contributors.update(authors)
    return receipts
