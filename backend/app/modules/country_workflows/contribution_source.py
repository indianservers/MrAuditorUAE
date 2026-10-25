"""Reviewed contribution amounts to controlled expected remittances, never payments."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from typing import Annotated
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator
from starlette.concurrency import run_in_threadpool

from app.modules.country_workflows.schemas import Obligation
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory.pension_profiles import Identifier, PensionScope

CONTRACT = "contribution-obligations/1"
AMOUNT = Annotated[Decimal, Field(ge=0, max_digits=36, decimal_places=8, allow_inf_nan=False)]


class ContributionControl(Strict):
    registration: Identifier
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    component: Identifier
    expected_rows: int = Field(ge=1, le=5000)
    amount: AMOUNT
    due_date: date
    due_date_reference: str = Field(min_length=3, max_length=200)

    @model_validator(mode="after")
    def referenced(self):
        if len(self.due_date_reference.strip()) < 3:
            raise ValueError("Reference the retained due-date evidence for each selected group")
        return self


class ContributionSourceInput(Strict):
    result_id: UUID
    due_date_evidence_version_id: UUID
    groups: list[ContributionControl] = Field(min_length=1, max_length=1000)
    pension_scope: PensionScope | None = None
    label: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def controlled(self):
        keys = [(item.registration, item.period, item.component) for item in self.groups]
        if len(keys) != len(set(keys)):
            raise ValueError("Select each registration, wage month and component only once")
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess remittance scope, payer and due-date evidence explicitly")
        return self


def source_rows(body, data):
    workflow = body.get("workflow")
    if workflow not in {"uae-pension-review", "india-payroll-rules"}:
        raise ValueError("Select a pension or India payroll contribution review")
    if body.get("blocked") or body.get("expected_total_complete") is not True:
        raise ValueError("Resolve the full contribution calculation before preparing remittances")
    pension = workflow == "uae-pension-review"
    currency = "AED" if pension else "INR"
    if body.get("currency") != currency:
        raise ValueError("Contribution result currency differs from its country workflow")
    if pension != (data.pension_scope is not None):
        raise ValueError("Select one explicit pension scope for UAE only")
    scope = data.pension_scope.model_dump(mode="json") if data.pension_scope else None
    allowed = (
        {"PENSION:EMPLOYEE", "PENSION:EMPLOYER"}
        if pension
        else {
            "PF:EMPLOYEE",
            "PF:EPS",
            "PF:EMPLOYER",
            "PF:ADVANCE_REFUND",
            "ESI:EMPLOYEE",
            "ESI:EMPLOYER",
            "PT",
        }
    )
    controls = {(item.registration, item.period, item.component): item for item in data.groups}
    if any(control.component not in allowed for control in data.groups):
        raise ValueError(
            "Select supported employer-remitted components; government support is a separate payer"
        )
    grouped = defaultdict(list)
    excluded = []
    for row in body["rows"]:
        key = tuple(row[field] for field in ("registration", "period", "component"))
        reason = (
            "SEPARATE_GOVERNMENT_PAYER"
            if row["component"] == "PENSION:GOVERNMENT"
            else "OUTSIDE_SELECTED_PENSION_SCOPE"
            if scope and any(row.get(field) != value for field, value in scope.items())
            else "UNSELECTED_REGISTRATION_MONTH_COMPONENT"
            if key not in controls
            else None
        )
        if reason:
            excluded.append({"source_result_row_id": row["id"], "reason": reason})
        else:
            grouped[key].append(row)
    rows = []
    identities = set()
    total = Decimal(0)
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for key, control in controls.items():
            selected = grouped[key]
            if len(selected) != control.expected_rows:
                raise ValueError(
                    "Independent contribution group row-count control does not agree; missing is not zero"
                )
            if any(
                row.get("expected_amount") is None
                or not row.get("basis_source_id")
                or row["currency"] != currency
                for row in selected
            ):
                raise ValueError(
                    "Every selected remittance needs a resolved assessed contribution basis"
                )
            if any(
                not Decimal(row["expected_amount"]).is_finite()
                or Decimal(row["expected_amount"]) < 0
                for row in selected
            ):
                raise ValueError(
                    "Expected remittances require finite non-negative assessed amounts"
                )
            amount = sum((Decimal(row["expected_amount"]) for row in selected), Decimal(0))
            if amount != control.amount:
                raise ValueError("Independent contribution group amount control does not agree")
            for row in selected:
                identity = tuple(
                    row[field]
                    for field in ("registration", "subject", "period", "component", "currency")
                )
                if identity in identities:
                    raise ValueError(
                        "Contribution rows collide in the settlement identity; split the scope explicitly"
                    )
                identities.add(identity)
                canonical = Obligation(
                    id="contribution:" + row["id"],
                    registration=row["registration"],
                    subject=row["subject"],
                    period=row["period"],
                    component=row["component"],
                    currency=currency,
                    amount=row["expected_amount"],
                    due_date=control.due_date,
                    pension_scope=scope,
                ).model_dump(mode="json")
                rows.append(
                    {
                        **canonical,
                        "source_result_row_id": row["id"],
                        "source_basis_row_id": row["basis_source_id"],
                        "due_date_reference": control.due_date_reference.strip(),
                        "due_date_basis": "EXPLICIT_RETAINED_DOCUMENT_ASSESSMENT_NOT_CALCULATED",
                        **({"pension_scope": scope} if scope else {}),
                    }
                )
            total += amount
    if len(rows) > 5000:
        raise ValueError("Split contribution remittances into at most 5,000 rows")
    return rows, {currency: str(total)}, excluded


async def derive(db, ctx, eng, data):
    from app.modules.country_workflows.service import payroll_rule_documents
    from app.modules.intelligence import service as intelligence
    from app.modules.jurisdictions.workspace import resolved

    parent = await intelligence.event(db, ctx, eng.id, data.result_id, True)
    if parent.kind != "country-workflow" or parent.body.get("review_status") != "REVIEWED":
        raise HTTPException(409, "Select a current independently reviewed contribution result")
    binding, _ = await resolved(db, ctx, eng)
    required_country = {"uae-pension-review": "AE", "india-payroll-rules": "IN"}.get(
        parent.body.get("workflow")
    )
    if not required_country or binding.country != required_country:
        raise HTTPException(422, "Contribution workflow does not match the engagement country")
    try:
        rows, totals, excluded = await run_in_threadpool(source_rows, parent.body, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    document, _ = await intelligence.evidence(db, ctx, eng, data.due_date_evidence_version_id)
    contributors = {str(ctx.user_id), *parent.body.get("contributors", [str(parent.created_by)])}
    if document.created_by is not None:
        contributors.add(str(document.created_by))
    receipts = await payroll_rule_documents(
        db,
        ctx,
        eng,
        [
            {
                "source_evidence_version_id": str(document.id),
                "source_sha256": document.sha256,
            }
        ],
        label="Contribution due-date",
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

    parent, rows, totals, excluded, dependencies, contributors = await derive(db, ctx, eng, data)
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
            "source_identity": "contribution:" + str(parent.root_id),
            "source_sha256": fingerprint(rows),
            "contributors": contributors,
            "population_completeness": "SELECTED_REVIEWED_CONTRIBUTION_GROUPS_ONLY",
            "native_metadata": data.model_dump(mode="json"),
            "excluded_rows": excluded,
            "limitations": [
                "Expected remittances only; cannot establish an independent authority return or bank payment",
                "Employee-level rows are preserved; registration, month, component and pension scope cannot be silently combined",
                "Government pension support is a separate payer and is excluded from employer-remitted expectations",
                "Due dates are explicitly assessed against retained evidence; no statutory deadline or payment is inferred",
            ],
        },
        dependencies,
        request_id,
    )


async def verify(db, ctx, eng, source, contributors):
    data = ContributionSourceInput.model_validate(source["native_metadata"])
    _, rows, totals, excluded, receipts, authors = await derive(db, ctx, eng, data)
    if (
        rows != source["rows"]
        or totals != source["control_totals"]
        or excluded != source["excluded_rows"]
        or fingerprint(rows) != source["source_sha256"]
    ):
        raise HTTPException(
            409, "Expected remittances no longer agree with the reviewed contribution result"
        )
    contributors.update(authors)
    return receipts
