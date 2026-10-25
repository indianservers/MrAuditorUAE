"""Published benefit profiles bound to a reviewed employee population."""

from datetime import date
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator

from app.db.models.platform import FinancialPeriod
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory import service as rules
from app.modules.regulatory.schemas import Rule
from app.modules.regulatory.source_documents import verify_rule_sources


class BenefitSourceInput(Strict):
    employee_source_id: UUID
    rule_version_ids: list[UUID] = Field(min_length=1, max_length=20)
    expected_employee_rows: int = Field(ge=1, le=5000)
    label: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def unique_profiles(self):
        if len(set(self.rule_version_ids)) != len(self.rule_version_ids):
            raise ValueError("Select each published benefit profile only once")
        if len(self.assessment.strip()) < 10:
            raise ValueError("Document the employee population and profile applicability")
        return self


async def derive(db, ctx, eng, employees, data):
    from app.modules.intelligence import service as intelligence
    from app.modules.jurisdictions.workspace import resolved

    await rules.authorize_read(db, ctx)
    binding, context = await resolved(db, ctx, eng)
    if binding.country != "AE":
        raise HTTPException(422, "Published benefit sources require a UAE engagement")
    if (
        employees.kind != "workflow-source"
        or employees.body.get("table_type") != "benefit-employees"
        or employees.body.get("review_status") != "REVIEWED"
    ):
        raise HTTPException(409, "Select a current independently reviewed employee source")
    population = employees.body["rows"]
    if len(population) != data.expected_employee_rows:
        raise HTTPException(422, "Employee row-count control does not agree")
    ends = {row["service_end"] for row in population}
    if len(ends) > 100:
        raise HTTPException(422, "Split the population into at most one hundred service-end dates")
    period = await db.get(FinancialPeriod, eng.period_id)
    profiles = {}
    for identifier in data.rule_version_ids:
        obj = await rules.get(db, ctx, identifier)
        rule = Rule.model_validate(obj.body)
        if (
            rule.method != "benefit_profile"
            or rule.country != "AE"
            or rule.framework != context["framework"]
        ):
            raise HTTPException(
                422, "Select UAE benefit profiles matching the engagement framework"
            )
        profiles[str(obj.id)] = (obj, rule)
    contributors = {
        str(ctx.user_id),
        *employees.body.get("contributors", [str(employees.created_by)]),
    }
    selected: dict[str, set[str]] = {}
    receipts = [intelligence.event_receipt(employees)]
    checked = {}
    for employee in population:
        # Unsupported cohorts remain explicitly blocked by the employee calculator.
        if (
            employee["scheme"] != "gratuity"
            or employee["work_model"] == "other"
            or not employee["work_model_constant_for_service"]
        ):
            continue
        end = date.fromisoformat(employee["service_end"])
        candidates = []
        for identifier, (obj, rule) in profiles.items():
            params = rule.benefit_parameters
            if not params or any(
                getattr(params, field) != employee[field]
                for field in ("regime", "cohort", "work_model")
            ):
                continue
            if end < rule.effective_from or (rule.effective_to and end > rule.effective_to):
                continue
            key = (obj.rule_key, employee["service_end"])
            if key not in checked:
                checked[key] = await rules.selection(
                    db, ctx, obj.rule_key, period.start_date, period.end_date, end
                )
            current = checked[key]
            if current is not None and current.id == obj.id:
                candidates.append(identifier)
        if len(candidates) != 1:
            raise HTTPException(
                409,
                "Each supported employee needs exactly one current published benefit profile at service end",
            )
        selected.setdefault(candidates[0], set()).add(employee["service_end"])
    if set(selected) != set(profiles):
        raise HTTPException(422, "Every selected benefit profile must cover a supported employee")
    rows = []
    for identifier, dates in sorted(selected.items()):
        obj, rule = profiles[identifier]
        copies = await verify_rule_sources(db, ctx, rule)
        contributors.add(str(obj.created_by))
        contributors.update(copy["created_by"] for copy in copies if copy["created_by"])
        for selected_end in sorted(dates):
            receipts.append(
                {
                    "type": "regulatory",
                    "id": identifier,
                    "rule_key": obj.rule_key,
                    "sha256": obj.sha256,
                    "transaction_date": selected_end,
                }
            )
        assert rule.benefit_parameters is not None
        rows.append(
            {
                **rule.benefit_parameters.model_dump(mode="json"),
                "id": identifier,
                "effective_from": rule.effective_from.isoformat(),
                "effective_to": rule.effective_to.isoformat()
                if rule.effective_to
                else date.max.isoformat(),
                "selected_service_end_dates": sorted(dates),
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

    employees = await intelligence.event(db, ctx, eng.id, data.employee_source_id, True)
    rows, dependencies, contributors = await derive(db, ctx, eng, employees, data)
    return await intelligence.append(
        db,
        ctx,
        eng,
        "workflow-source",
        {
            "table_type": "benefit-rules",
            "rows": rows,
            "row_count": len(rows),
            "control_totals": {},
            "title": data.label,
            "review_status": "UNVERIFIED",
            "parser_version": "published-benefit-profiles/1",
            "source_identity": "published-benefits:" + str(employees.root_id),
            "source_sha256": fingerprint(rows),
            "contributors": contributors,
            "population_completeness": "SELECTED_REVIEWED_EMPLOYEE_POPULATION_ONLY",
            "native_metadata": data.model_dump(mode="json"),
            "limitations": [
                "Published profiles are selected separately at each employee service-end date",
                "Alternative schemes and work-model changes still require separate assessment",
                "Independently review this derived rule source before calculating benefits",
            ],
        },
        dependencies,
        request_id,
    )


async def verify(db, ctx, eng, sources, data, contributors):
    from app.modules.intelligence import service as intelligence

    source = sources["rules"]
    metadata = BenefitSourceInput.model_validate(source["native_metadata"])
    if metadata.employee_source_id != data.source_ids["employees"]:
        raise HTTPException(
            422, "Published profiles are bound to their original reviewed employee population"
        )
    employees = await intelligence.event(db, ctx, eng.id, metadata.employee_source_id, True)
    rows, receipts, authors = await derive(db, ctx, eng, employees, metadata)
    if rows != source["rows"] or fingerprint(rows) != source["source_sha256"]:
        raise HTTPException(409, "Published benefit source no longer agrees with current profiles")
    contributors.update(authors)
    return receipts
