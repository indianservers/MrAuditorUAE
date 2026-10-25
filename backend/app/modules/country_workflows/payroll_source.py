"""Published India payroll profiles bound to reviewed assessed wage bases."""

import calendar
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator

from app.db.models.platform import FinancialPeriod
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory import service as rules
from app.modules.regulatory.rule_spans import selection_over_span
from app.modules.regulatory.schemas import Rule
from app.modules.regulatory.source_documents import verify_rule_sources


class PayrollSourceInput(Strict):
    basis_source_id: UUID
    rule_version_ids: list[UUID] = Field(min_length=1, max_length=20)
    expected_basis_rows: int = Field(ge=1, le=5000)
    label: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def unique_profiles(self):
        if len(set(self.rule_version_ids)) != len(self.rule_version_ids):
            raise ValueError("Select each published payroll profile only once")
        if len(self.assessment.strip()) < 10:
            raise ValueError("Document the wage bases, jurisdiction and profile applicability")
        return self


def month_span(period):
    try:
        year, month = map(int, period.split("-"))
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    except (ValueError, OverflowError):
        raise HTTPException(422, "Payroll wage month must be a valid calendar month") from None


async def derive(db, ctx, eng, bases, data):
    from app.modules.intelligence import service as intelligence
    from app.modules.jurisdictions.workspace import resolved

    await rules.authorize_read(db, ctx)
    binding, context = await resolved(db, ctx, eng)
    if binding.country != "IN":
        raise HTTPException(422, "Published payroll sources require an India engagement")
    if (
        bases.kind != "workflow-source"
        or bases.body.get("table_type") != "payroll-bases"
        or bases.body.get("review_status") != "REVIEWED"
    ):
        raise HTTPException(409, "Select a current independently reviewed payroll basis source")
    population = bases.body["rows"]
    if len(population) != data.expected_basis_rows:
        raise HTTPException(422, "Payroll basis row-count control does not agree")
    if len({row["period"] for row in population}) > 100:
        raise HTTPException(422, "Split the population into at most one hundred wage months")
    period = await db.get(FinancialPeriod, eng.period_id)
    profiles = {}
    for identifier in data.rule_version_ids:
        obj = await rules.get(db, ctx, identifier)
        rule = Rule.model_validate(obj.body)
        if (
            rule.method != "payroll_profile"
            or rule.country != "IN"
            or rule.framework != context["framework"]
        ):
            raise HTTPException(
                422, "Select India payroll profiles matching the engagement framework"
            )
        profiles[str(obj.id)] = (obj, rule)
    contributors = {str(ctx.user_id), *bases.body.get("contributors", [str(bases.created_by)])}
    selected: dict[str, set[str]] = {}
    checked = {}
    receipts = [intelligence.event_receipt(bases)]
    for basis in population:
        start, end = month_span(basis["period"])
        candidates = []
        amount = Decimal(basis["amount"])
        for identifier, (obj, rule) in profiles.items():
            params = rule.payroll_parameters
            if not params or any(
                getattr(params, field) != basis[field]
                for field in ("rule_group", "component", "jurisdiction")
            ):
                continue
            if (
                amount < params.threshold_from
                or (params.threshold_to is not None and amount >= params.threshold_to)
                or start < rule.effective_from
                or (rule.effective_to and end > rule.effective_to)
            ):
                continue
            key = (obj.rule_key, basis["period"])
            if key not in checked:
                checked[key] = await selection_over_span(
                    db, ctx, obj.rule_key, period.start_date, period.end_date, start, end
                )
            current = checked[key]
            if current is not None and current.id == obj.id:
                candidates.append(identifier)
        if len(candidates) != 1:
            raise HTTPException(
                409,
                "Each assessed wage basis needs exactly one current published profile covering the entire wage month and slab",
            )
        selected.setdefault(candidates[0], set()).add(basis["period"])
    if set(selected) != set(profiles):
        raise HTTPException(422, "Every selected payroll profile must cover an assessed wage basis")
    rows = []
    for identifier, months in sorted(selected.items()):
        obj, rule = profiles[identifier]
        copies = await verify_rule_sources(db, ctx, rule)
        contributors.add(str(obj.created_by))
        contributors.update(copy["created_by"] for copy in copies if copy["created_by"])
        for month in sorted(months):
            start, end = month_span(month)
            receipts.append(
                {
                    "type": "regulatory",
                    "id": identifier,
                    "rule_key": obj.rule_key,
                    "sha256": obj.sha256,
                    "span_start": start.isoformat(),
                    "span_end": end.isoformat(),
                }
            )
        assert rule.payroll_parameters is not None
        rows.append(
            {
                **rule.payroll_parameters.model_dump(mode="json"),
                "id": identifier,
                "effective_from": rule.effective_from.isoformat(),
                "effective_to": rule.effective_to.isoformat()
                if rule.effective_to
                else date.max.isoformat(),
                "selected_wage_months": sorted(months),
                "evidence_reference": "Published rule " + identifier,
                "source_url": str(rule.citations[0].url),
                "source_version": obj.rule_key + "/" + str(obj.version),
                "source_sha256": copies[0]["sha256"],
                "source_evidence_version_id": None,
                "source_document_id": copies[0]["id"],
                "published_rule_version_id": identifier,
                "published_rule_sha256": obj.sha256,
                "source_copies": copies,
                "applicability_review": data.assessment.strip(),
            }
        )
    return rows, receipts, sorted(contributors)


async def prepare(db, ctx, eng, data, request_id):
    from app.modules.intelligence import service as intelligence

    bases = await intelligence.event(db, ctx, eng.id, data.basis_source_id, True)
    rows, dependencies, contributors = await derive(db, ctx, eng, bases, data)
    return await intelligence.append(
        db,
        ctx,
        eng,
        "workflow-source",
        {
            "table_type": "payroll-rules",
            "rows": rows,
            "row_count": len(rows),
            "control_totals": {},
            "title": data.label,
            "review_status": "UNVERIFIED",
            "parser_version": "published-payroll-profiles/1",
            "source_identity": "published-payroll:" + str(bases.root_id),
            "source_sha256": fingerprint(rows),
            "contributors": contributors,
            "population_completeness": "SELECTED_REVIEWED_WAGE_BASES_ONLY",
            "native_metadata": data.model_dump(mode="json"),
            "limitations": [
                "Profiles must be selected unchanged throughout each complete wage month",
                "Membership, eligibility, jurisdiction and wage bases remain professionally assessed source inputs",
                "Independently review the derived rules; contribution review does not establish payment or filing",
            ],
        },
        dependencies,
        request_id,
    )


async def verify(db, ctx, eng, sources, data, contributors):
    from app.modules.intelligence import service as intelligence

    source = sources["rules"]
    metadata = PayrollSourceInput.model_validate(source["native_metadata"])
    if metadata.basis_source_id != data.source_ids["bases"]:
        raise HTTPException(
            422, "Published payroll profiles are bound to their original reviewed wage bases"
        )
    bases = await intelligence.event(db, ctx, eng.id, metadata.basis_source_id, True)
    rows, receipts, authors = await derive(db, ctx, eng, bases, metadata)
    if rows != source["rows"] or fingerprint(rows) != source["source_sha256"]:
        raise HTTPException(409, "Published payroll source no longer agrees with current profiles")
    contributors.update(authors)
    return receipts
