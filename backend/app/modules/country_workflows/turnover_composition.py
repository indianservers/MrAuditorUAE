"""Combine reviewed turnover books without erasing scope or source provenance."""

import re
import uuid
from datetime import date
from decimal import Decimal, localcontext

from fastapi import HTTPException
from pydantic import Field, model_validator

from app.modules.country_workflows.turnover import Money, TurnoverAmount, key
from app.modules.country_workflows.turnover_ledger import CONTRACT as LEDGER
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "turnover-books-composition/1"


class TurnoverCompositionInput(Strict):
    source_ids: list[uuid.UUID] = Field(min_length=2, max_length=50)
    expected_rows: int = Field(ge=2, le=5000, strict=True)
    currency: str = Field(pattern="^(AED|INR)$")
    expected_amount: Money
    label: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def assessed(self):
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Select distinct reviewed turnover source versions")
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess the complete selected book population and disjoint sources")
        return self


def source_rows(bodies, data, country):
    currency = "AED" if country == "AE" else "INR"
    pattern = r"[0-9]{15}" if country == "AE" else r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]"
    if country not in {"AE", "IN"} or data.currency != currency:
        raise ValueError("Turnover books must use the engagement country's return currency")
    rows: list[dict] = []
    ledger_selections: list[tuple[str, dict]] = []
    references, identities, ledger_lines = set(), set(), set()
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        total = Decimal(0)
        for identifier in data.source_ids:
            body = bodies[str(identifier)]
            if body.get("table_type") != "turnover-amounts" or not body.get("rows"):
                raise ValueError("Every component must contain explicit turnover amount rows")
            if (
                body.get("allowed_source_roles") is not None
                and "books" not in body["allowed_source_roles"]
            ):
                raise ValueError("A return-only population cannot establish composed books")
            if (
                body.get("allowed_workflows")
                and "tax-turnover-bridge" not in body["allowed_workflows"]
            ):
                raise ValueError("Component is restricted to a different workflow")
            if body.get("parser_version") == CONTRACT:
                raise ValueError("Select original sources, not already composed books")
            identity = body.get("source_identity") or body.get("evidence_version_id")
            if not identity:
                raise ValueError("Every component needs retained underlying source identity")
            if body.get("parser_version") == LEDGER:
                scope = body["native_metadata"]
                for previous_identity, previous in ledger_selections:
                    if (
                        identity == previous_identity
                        and set(scope["account_ids"]) & set(previous["account_ids"])
                        and max(scope["period_start"], previous["period_start"])
                        <= min(scope["period_end"], previous["period_end"])
                    ):
                        raise ValueError(
                            "Overlapping ledger accounts and dates cannot establish separate book components"
                        )
                ledger_selections.append((identity, scope))
            elif identity in identities:
                raise ValueError(
                    "One underlying schedule cannot establish multiple book components"
                )
            identities.add(identity)
            for original in body["rows"]:
                if len(rows) >= 5000:
                    raise ValueError(
                        "Composed turnover books exceed 5,000 rows; partition the population"
                    )
                row = TurnoverAmount.model_validate(
                    {k: original[k] for k in TurnoverAmount.model_fields}
                ).model_dump(mode="json")
                if row["currency"] != currency or not re.fullmatch(pattern, row["registration"]):
                    raise ValueError(
                        "Every component must use the country registration syntax and return currency"
                    )
                reference = (key(row), row["reference"])
                if reference in references:
                    raise ValueError(
                        "Duplicate turnover reference in the same registration and period"
                    )
                references.add(reference)
                if body.get("parser_version") == LEDGER and not body.get("generated_nil_row"):
                    line = (identity, original["id"])
                    if line in ledger_lines:
                        raise ValueError("A committed journal line cannot be allocated twice")
                    ledger_lines.add(line)
                rows.append(
                    {
                        **original,
                        **row,
                        "id": fingerprint({"event": str(identifier), "row": original["id"]}),
                        "source_component_event_id": str(identifier),
                        "source_component_row_id": original["id"],
                    }
                )
                total += Decimal(row["amount"])
        if len(rows) != data.expected_rows or total != data.expected_amount:
            raise ValueError(
                "Independent composed row count and signed amount controls must agree exactly"
            )
    return rows, {currency: str(total)}


async def derive(db, ctx, eng, data):
    from app.db.models.platform import FinancialPeriod
    from app.modules.intelligence import service
    from app.modules.jurisdictions.workspace import resolved

    package, _ = await resolved(db, ctx, eng)
    period = await db.get(FinancialPeriod, eng.period_id)
    bodies, dependencies, contributors, roots = {}, [], {str(ctx.user_id)}, set()
    for identifier in data.source_ids:
        source = await service.event(db, ctx, eng.id, identifier, True)
        if source.kind != "workflow-source" or source.body.get("review_status") != "REVIEWED":
            raise HTTPException(409, "Independently review every current turnover book component")
        if source.root_id in roots:
            raise HTTPException(422, "Versions of one source cannot establish multiple components")
        roots.add(source.root_id)
        bodies[str(identifier)] = source.body
        dependencies.append(service.event_receipt(source))
        contributors.update(source.body.get("contributors") or [str(source.created_by)])
    try:
        rows, totals = source_rows(bodies, data, package.country)
        if not period or any(
            not period.start_date
            <= date.fromisoformat(row["period_start"])
            <= date.fromisoformat(row["period_end"])
            <= period.end_date
            for row in rows
        ):
            raise ValueError(
                "Composed turnover periods must be inside the engagement financial period"
            )
    except (ValueError, KeyError) as error:
        raise HTTPException(422, str(error)) from None
    return rows, totals, dependencies, contributors


async def prepare(db, ctx, eng, data, request_id):
    from app.modules.intelligence import service

    rows, totals, dependencies, contributors = await derive(db, ctx, eng, data)
    return await service.append(
        db,
        ctx,
        eng,
        "workflow-source",
        {
            "table_type": "turnover-amounts",
            "rows": rows,
            "row_count": len(rows),
            "control_totals": totals,
            "title": data.label,
            "review_status": "UNVERIFIED",
            "parser_version": CONTRACT,
            "allowed_source_roles": ["books"],
            "allowed_workflows": ["tax-turnover-bridge"],
            "source_identity": "turnover-books:"
            + fingerprint({"sources": sorted(str(i) for i in data.source_ids)}),
            "source_sha256": fingerprint({"rows": rows}),
            "contributors": sorted(contributors),
            "native_metadata": data.model_dump(mode="json"),
            "population_completeness": "DECLARED_REVIEWED_COMPONENTS_ONLY",
            "statutory_calculation_qualified": False,
            "limitations": [
                "All selected book rows and registration periods are retained; this does not establish whole-entity completeness",
                "No registration allocation, revenue classification, FX conversion or filed-return evidence is inferred",
                "Independent review, separate expected scope, return and signed adjustment populations remain required",
            ],
        },
        dependencies,
        request_id,
    )


async def verify(db, ctx, eng, body, contributors):
    data = TurnoverCompositionInput.model_validate(body["native_metadata"])
    rows, totals, dependencies, authors = await derive(db, ctx, eng, data)
    if (
        rows != body["rows"]
        or totals != body["control_totals"]
        or fingerprint({"rows": rows}) != body["source_sha256"]
    ):
        raise HTTPException(409, "Composed turnover books no longer agree with reviewed components")
    contributors.update(authors)
    return dependencies


async def origins(db, ctx, eng, identifier):
    """Compare retained event roots and actual evidence, excluding shared context."""
    from app.modules.intelligence import service

    pending = [identifier]
    visited: set[uuid.UUID] = set()
    result: set[tuple[str, str]] = set()
    while pending:
        identifier = pending.pop()
        if identifier in visited:
            continue
        if len(visited) >= 200:
            raise HTTPException(
                409, "Turnover source-origin verification exceeds its 200-event bound"
            )
        visited.add(identifier)
        event = await service.event(db, ctx, eng.id, identifier, True)
        result.add(("event-root", str(event.root_id)))
        for dependency in event.dependencies:
            if dependency["type"] == "event":
                pending.append(uuid.UUID(dependency["id"]))
            elif dependency["type"] in {"evidence", "calculation", "snapshot"} and dependency.get(
                "sha256"
            ):
                result.add((dependency["type"], dependency["sha256"]))
    return result
