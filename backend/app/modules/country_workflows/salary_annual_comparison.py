"""Compare original quarterly salary parties to recorded annual current-employer tax."""

from decimal import Decimal, localcontext
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator
from starlette.concurrency import run_in_threadpool

from app.modules.country_workflows.india_salary_annual import PROFILE
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "india-salary-four-quarter-current-employer/1"
Quarter = Literal["Q1", "Q2", "Q3", "Q4"]
MISSING = {"PANNOTAVBL", "PANAPPLIED", "PANINVALID"}


class SalaryPartyLink(Strict):
    quarter: Quarter
    party_key: str = Field(pattern=r"^[1-9][0-9]*/[1-9][0-9]*/[1-9][0-9]*$")


class SalaryEmployeeMap(Strict):
    annual_key: str = Field(pattern=r"^SD/[1-9][0-9]*/[1-9][0-9]*$")
    parties: list[SalaryPartyLink] = Field(default_factory=list, max_length=20000)
    identity_status: Literal["assessed_same_employee", "unresolved"]
    assessment: str = Field(min_length=10, max_length=2000)


class SalaryAnnualComparisonInput(Strict):
    label: str = Field(min_length=1, max_length=200)
    quarter_source_ids: dict[Quarter, UUID | None]
    nil_quarter_assessments: dict[Quarter, str] = Field(default_factory=dict)
    crosswalk_document_version_id: UUID
    crosswalk_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    employees: list[SalaryEmployeeMap] = Field(min_length=1, max_length=5000)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def complete(self):
        if set(self.quarter_source_ids) != {"Q1", "Q2", "Q3", "Q4"}:
            raise ValueError("Declare all four quarters; absence is not nil")
        ids = [v for v in self.quarter_source_ids.values() if v is not None]
        if self.quarter_source_ids["Q4"] is None or len(ids) != len(set(ids)):
            raise ValueError("Retain distinct quarter sources and an original annual Q4 source")
        nil = {q for q, value in self.quarter_source_ids.items() if value is None}
        if set(self.nil_quarter_assessments) != nil or any(
            not 10 <= len(v.strip()) <= 2000 for v in self.nil_quarter_assessments.values()
        ):
            raise ValueError("Every nil quarter requires its own retained meaningful assessment")
        keys = [e.annual_key for e in self.employees]
        links = [(p.quarter, p.party_key) for e in self.employees for p in e.parties]
        if len(keys) != len(set(keys)) or len(links) != len(set(links)) or len(links) > 20000:
            raise ValueError("Annual employees and quarterly parties cannot be assigned twice")
        if any(
            len(v.strip()) < 10 for v in [self.assessment, *(e.assessment for e in self.employees)]
        ):
            raise ValueError("Retain meaningful employee identity and full-population assessments")
        return self


def compare(data, bodies):
    """Every original DD party is assigned or disclosed, never silently filtered."""
    if set(bodies) != {
        q for q, identifier in data.quarter_source_ids.items() if identifier is not None
    }:
        raise ValueError("Every declared non-nil quarter must have its complete selected source")
    q4 = bodies["Q4"]
    meta = q4["native_metadata"]
    fy, tan = meta["financial_year"], meta["tan"]
    year = int(fy[:4])
    if not 2013 <= year <= 2025:
        raise ValueError("Four-quarter current-employer comparison covers FY2013-14 to FY2025-26")
    annual = meta.get("salary_annual") or {}
    if annual.get("contract") != "historical-salary-annual-observations/1":
        raise ValueError("Retain the complete controlled Q4 annual population")
    parents = {
        f"SD/{r['batch']}/{r['record_number']}": r
        for r in annual["records"]
        if r["record_type"] == "SD"
    }
    if set(parents) != {e.annual_key for e in data.employees}:
        raise ValueError("Map the complete original annual SD population exactly once")
    parties: dict[tuple[str, str], dict[str, Any]] = {}
    quarter_totals = {}
    for quarter, body in bodies.items():
        m = body["native_metadata"]
        expected = PROFILE if quarter == "Q4" else "india-24q-regular-q1q3-v6.3"
        if (
            body.get("native_format") != expected
            or body.get("table_type") != "withholding-records"
            or body.get("allowed_source_roles") != ["reported"]
            or m.get("form") != "24Q"
            or m.get("quarter") != quarter
            or (m.get("financial_year"), m.get("tan")) != (fy, tan)
            or m.get("controls", {}).get("record_status") != "current"
        ):
            raise ValueError(
                "Use current regular salary sources for one TAN, year and exact quarter"
            )
        links = m["party_links"]
        if len(links) != m["party_count"]:
            raise ValueError("Quarterly native party population is incomplete")
        keys = [(quarter, p["party_key"]) for p in links]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate original quarterly party identities")
        parties.update(zip(keys, links, strict=True))
        quarter_totals[quarter] = str(sum((Decimal(p["total_tax"]) for p in links), Decimal(0)))
    if len(parties) > 20000:
        raise ValueError("Quarterly comparison exceeds the 20,000 original-party bound")
    assigned = set()
    rows, retained_links = [], []
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for employee in data.employees:
            parent = parents[employee.annual_key]
            fields = parent["fields"]
            if not fields[35]:
                raise ValueError("Annual current-employer tax field 36 is missing, not zero")
            recorded = Decimal(fields[35])
            amounts = {q: Decimal(0) for q in ("Q1", "Q2", "Q3", "Q4")}
            for link in employee.parties:
                key = (link.quarter, link.party_key)
                if key not in parties:
                    raise ValueError("Employee crosswalk refers to a missing quarterly party")
                party = parties[key]
                if party["native_section_code"] == "94P":
                    raise ValueError(
                        "Specified-senior parties cannot be merged into annual salary SD"
                    )
                if party["pan"] != parent["pan"] and not (
                    party["pan"] in MISSING or parent["pan"] in MISSING
                ):
                    raise ValueError(
                        "Different valid PANs require corrected source evidence, not a crosswalk"
                    )
                assigned.add(key)
                amounts[link.quarter] += Decimal(party["total_tax"])
                retained_links.append(
                    {
                        "annual_key": employee.annual_key,
                        "quarter": link.quarter,
                        "source_event_id": str(data.quarter_source_ids[link.quarter]),
                        **party,
                        "identity_status": employee.identity_status,
                        "identity_assessment": employee.assessment,
                    }
                )
            total = sum(amounts.values(), Decimal(0))
            difference = recorded - total
            state = (
                "IDENTITY_UNRESOLVED"
                if employee.identity_status == "unresolved"
                else "DIFFERENCE"
                if difference
                else "AGREES"
            )
            rows.append(
                {
                    "id": employee.annual_key,
                    "annual_key": employee.annual_key,
                    "annual_source_line": parent["source_line"],
                    "pan": parent["pan"],
                    "currency": "INR",
                    "annual_current_employer_tax": str(recorded),
                    **{q.lower() + "_tax": str(amount) for q, amount in amounts.items()},
                    "quarterly_tax": str(total),
                    "difference": str(difference),
                    "party_count": len(employee.parties),
                    "identity_status": employee.identity_status,
                    "identity_assessment": employee.assessment,
                    "comparison_state": state,
                    "state": "MATCHED" if state == "AGREES" else "EXCEPTION",
                    "exceptions": [] if state == "AGREES" else [state],
                }
            )
    unassigned = [
        {"quarter": q, "source_event_id": str(data.quarter_source_ids[q]), **party}
        for (q, key), party in parties.items()
        if (q, key) not in assigned
    ]
    employee_count = len(rows)
    for party in unassigned:
        rows.append(
            {
                "id": f"unassigned:{party['quarter']}:{party['party_key']}",
                "pan": party["pan"],
                "currency": "INR",
                "quarter": party["quarter"],
                "quarterly_tax": party["total_tax"],
                "annual_key": None,
                "annual_current_employer_tax": None,
                "difference": None,
                "comparison_state": "UNASSIGNED_QUARTERLY_PARTY",
                "state": "EXCEPTION",
                "exceptions": ["UNASSIGNED_QUARTERLY_PARTY"],
            }
        )
    return {
        "workflow": "india-salary-annual-reconciliation",
        "contract": CONTRACT,
        "title": data.label,
        "parameters": data.model_dump(mode="json"),
        "tan": tan,
        "financial_year": fy,
        "rows": rows,
        "row_count": len(rows),
        "salary_employee_count": employee_count,
        "salary_quarterly_links": retained_links,
        "unassigned_quarterly_parties": unassigned,
        "specified_senior_annual_record_count": sum(
            r["record_type"] == "94P" for r in annual["records"]
        ),
        "quarter_tax_totals": quarter_totals,
        "nil_quarter_assessments": data.nil_quarter_assessments,
        "exception_count": sum(bool(r["exceptions"]) for r in rows),
        "comparison_complete": not unassigned
        and all(r.get("identity_status") != "unresolved" for r in rows),
        "population_completeness": "FOUR_ASSESSED_QUARTERS_AND_COMPLETE_ANNUAL_SD_POPULATION",
        "statutory_calculation_qualified": False,
        "professional_conclusion": "NOT_DETERMINED",
        "review_status": "UNVERIFIED",
        "limitations": [
            "Recorded SD field36 current-employer tax only; previous employers, superannuation, other TDS/TCS and annual net tax are not substituted",
            "Nil quarters are independent retained assessments, not portal or filing evidence",
            "Unassigned quarterly parties remain explicit exceptions; specified-senior annual records are outside this salary comparison",
            "Employee identity is explicitly assessed, never inferred from names or missing-PAN sentinels",
            "No recomputed salary tax, deduction entitlement, FVU/CSI, government filing, bank payment or tax credit qualification",
        ],
    }


async def prepare(db, ctx, eng, data, request_id):
    from sqlalchemy import select

    from app.db.models.platform import FinancialPeriod
    from app.modules.country_workflows.service import payroll_rule_documents
    from app.modules.intelligence import service
    from app.modules.jurisdictions.workspace import resolved

    package, context = await resolved(db, ctx, eng)
    if package.country != "IN":
        raise HTTPException(422, "Annual salary comparison requires an India engagement")
    sources, roots, hashes, contributors = {}, set(), set(), {str(ctx.user_id)}
    dependencies = [
        {"type": "context", "version": context["version"], "sha256": package.package_sha256}
    ]
    for q, identifier in data.quarter_source_ids.items():
        if identifier is None:
            continue
        source = await service.event(db, ctx, eng.id, identifier, True)
        if source.kind != "workflow-source" or source.body.get("review_status") != "REVIEWED":
            raise HTTPException(409, "Independently review every current native quarter first")
        if source.root_id in roots:
            raise HTTPException(422, "Versions of one source cannot establish multiple quarters")
        roots.add(source.root_id)
        sources[q] = source.body
        meta = source.body.get("native_metadata") or {}
        hashes.add(meta.get("source_sha256"))
        crosswalk_id = meta.get("controls", {}).get("crosswalk_document_version_id")
        if crosswalk_id == str(data.crosswalk_document_version_id):
            raise HTTPException(422, "Retain a separate annual employee/nil-quarter crosswalk")
        if crosswalk_id:
            original_crosswalk, _ = await service.evidence(db, ctx, eng, UUID(crosswalk_id))
            if original_crosswalk.sha256 == data.crosswalk_sha256:
                raise HTTPException(
                    422, "A cloned quarterly crosswalk is not independent annual mapping"
                )
        dependencies.append(service.event_receipt(source))
        contributors.update(source.body.get("contributors", [str(source.created_by)]))
    if data.crosswalk_sha256 in hashes:
        raise HTTPException(
            422, "Annual crosswalk cannot reuse the original native statement bytes"
        )
    try:
        result = await run_in_threadpool(compare, data, sources)
    except (ValueError, KeyError, TypeError, IndexError) as error:
        raise HTTPException(422, f"Annual salary comparison: {error}") from None
    period = await db.scalar(select(FinancialPeriod).where(FinancialPeriod.id == eng.period_id))
    year = int(result["financial_year"][:4])
    if (
        period is None
        or str(period.start_date) > f"{year}-04-01"
        or str(period.end_date) < f"{year + 1}-03-31"
    ):
        raise HTTPException(
            422, "Engagement period must cover the complete assessed financial year"
        )
    dependencies.extend(
        await payroll_rule_documents(
            db,
            ctx,
            eng,
            [
                {
                    "source_evidence_version_id": str(data.crosswalk_document_version_id),
                    "source_sha256": data.crosswalk_sha256,
                }
            ],
            label="Annual salary employee and nil-quarter crosswalk",
            contributors=contributors,
        )
    )
    result["contributors"] = sorted(contributors)
    result["salary_crosswalk_document_binding"] = "RETAINED_DOCUMENT_BYTES_VERIFIED"
    return await service.append(db, ctx, eng, "country-workflow", result, dependencies, request_id)
