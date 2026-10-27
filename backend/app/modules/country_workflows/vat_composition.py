"""Compose disjoint reviewed VAT201 book schedules without inferring absent boxes."""

import uuid
from decimal import Decimal, localcontext

from fastapi import HTTPException
from pydantic import Field, field_validator, model_validator

from app.modules.country_workflows.schemas import Money, ReturnBox
from app.modules.country_workflows.vat201_layouts import EMIRATES, LAYOUTS, VAT201Layout
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "uae-vat201-composition/1"


class VATCompositionInput(Strict):
    source_ids: list[uuid.UUID] = Field(min_length=2, max_length=20)
    layout: VAT201Layout = "aggregate-14"
    taxable_amount: Money
    tax: Money
    adjustment: Money
    label: str = Field(min_length=1, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("assessment")
    @classmethod
    def meaningful(cls, value):
        if len(value.strip()) < 10:
            raise ValueError("Assess composition scope and disjoint source populations")
        return value.strip()

    @model_validator(mode="after")
    def distinct(self):
        if len(self.source_ids) > len(LAYOUTS[self.layout]["boxes"]):
            raise ValueError("Too many component schedules for the selected VAT201 layout")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Select distinct reviewed VAT201 source versions")
        return self


def source_rows(sources, data):
    rows, seen, scopes, identities = [], set(), set(), set()
    required = LAYOUTS[data.layout]["boxes"]
    word = "fourteen" if data.layout == "aggregate-14" else "twenty"
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        totals = {field: Decimal(0) for field in ("taxable_amount", "tax", "adjustment")}
        for identifier in data.source_ids:
            body = sources[str(identifier)]
            if body.get("table_type") != "return-boxes" or not body.get("rows"):
                raise ValueError("Every component must contain explicit return-box rows")
            if len(body["rows"]) > len(required):
                raise ValueError(f"A component may contain at most {word} distinct boxes")
            identity = body.get("source_identity") or body.get("evidence_version_id")
            if not identity or identity in identities:
                raise ValueError(
                    "The same underlying schedule cannot establish multiple components"
                )
            identities.add(identity)
            for original in body["rows"]:
                row = ReturnBox.model_validate(
                    {k: original[k] for k in ReturnBox.model_fields}
                ).model_dump(mode="json")
                box = row["box"]
                if data.layout == "emirate-20" and any(
                    Decimal(row[field]) != Decimal(row[field]).quantize(Decimal("0.01"))
                    for field in ("taxable_amount", "tax", "adjustment")
                ):
                    raise ValueError(
                        "Emirate VAT201 row amounts must be stated to the nearest fils"
                    )
                if box not in required or box in seen:
                    raise ValueError(
                        "VAT201 composition requires disjoint boxes from the selected layout; overlap is not additive"
                    )
                if (
                    row["currency"] != "AED"
                    or not row["registration"].isascii()
                    or not row["registration"].isdigit()
                    or len(row["registration"]) != 15
                ):
                    raise ValueError("VAT201 composition requires one 15-digit UAE TRN and AED")
                seen.add(box)
                scopes.add((row["registration"], row["period_start"], row["period_end"]))
                for field in totals:
                    totals[field] += Decimal(row[field])
                rows.append(
                    {
                        **row,
                        "id": "composed-box-" + box,
                        **({"emirate": EMIRATES[box]} if box in EMIRATES else {}),
                        "source_component_event_id": str(identifier),
                        "source_component_row_id": original["id"],
                    }
                )
        if seen != set(required):
            raise ValueError(
                f"Retain all {word} explicit boxes; absent boxes cannot be inferred as nil"
            )
        if len(scopes) != 1:
            raise ValueError("All composed VAT201 boxes must share one TRN and return period")
        if any(totals[field] != getattr(data, field) for field in totals):
            raise ValueError(
                "Independent whole-schedule taxable, tax and adjustment controls do not agree"
            )
    return sorted(rows, key=lambda row: required.index(row["box"])), {"AED": str(totals["tax"])}


async def derive(db, ctx, eng, data):
    from app.modules.intelligence import service
    from app.modules.jurisdictions.workspace import resolved

    package, _ = await resolved(db, ctx, eng)
    if package.country != "AE":
        raise HTTPException(422, "VAT201 composition requires a UAE engagement")
    bodies, dependencies, contributors, roots = {}, [], set(), set()
    for identifier in data.source_ids:
        source = await service.event(db, ctx, eng.id, identifier, True)
        if source.kind != "workflow-source" or source.body.get("table_type") != "return-boxes":
            raise HTTPException(422, "Select canonical VAT201 return-box sources")
        if source.body.get("review_status") != "REVIEWED":
            raise HTTPException(
                409, "Independently review every component before VAT201 composition"
            )
        if source.body.get("parser_version") == CONTRACT:
            raise HTTPException(422, "Compose original schedules, not another composed schedule")
        if source.root_id in roots:
            raise HTTPException(
                422, "Versions of one schedule cannot establish multiple components"
            )
        roots.add(source.root_id)
        bodies[str(identifier)] = source.body
        dependencies.append(service.event_receipt(source))
        contributors.update(source.body.get("contributors", [str(source.created_by)]))
    try:
        rows, totals = source_rows(bodies, data)
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
            "table_type": "return-boxes",
            "rows": rows,
            "row_count": len(rows),
            "control_totals": totals,
            "title": data.label,
            "review_status": "UNVERIFIED",
            "parser_version": CONTRACT,
            "allowed_source_roles": ["books"],
            "source_identity": "vat201-composition:"
            + fingerprint({"source_ids": sorted(str(i) for i in data.source_ids)}),
            "source_sha256": fingerprint({"rows": rows}),
            "contributors": sorted(contributors | {str(ctx.user_id)}),
            "native_metadata": data.model_dump(mode="json"),
            "population_completeness": "DECLARED_DISJOINT_TWENTY_BOX_EMIRATE_BOOK_SCHEDULES"
            if data.layout == "emirate-20"
            else "DECLARED_DISJOINT_FOURTEEN_BOX_BOOK_SCHEDULES",
            "statutory_calculation_qualified": False,
            "limitations": [
                f"All {len(LAYOUTS[data.layout]['boxes'])} explicit assessed book boxes are retained; composition does not establish whole-return legal completeness",
                "No missing box, tax rate, summary equation, recovery eligibility or filed-return evidence is inferred",
                "Taxable, tax and adjustment controls sum every canonical box including summaries; they are not net tax payable",
                "Separately retained filed evidence and independent review of this composed source are required",
            ],
        },
        dependencies,
        request_id,
    )


async def origins(db, ctx, eng, identifier):
    """Bounded retained-origin graph; reviews do not create independent evidence."""
    from app.modules.intelligence import service

    pending = [identifier]
    visited: set[uuid.UUID] = set()
    result: set[tuple[str, str]] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        if len(visited) >= 100:
            raise HTTPException(
                409, "VAT201 source-origin verification exceeds its 100-event bound"
            )
        visited.add(current)
        event = await service.event(db, ctx, eng.id, current, True)
        result.add(("event-root", str(event.root_id)))
        for dependency in event.dependencies:
            if dependency["type"] == "event":
                pending.append(uuid.UUID(dependency["id"]))
            elif dependency["type"] in {"evidence", "calculation", "snapshot"}:
                if dependency.get("sha256"):
                    result.add((dependency["type"], dependency["sha256"]))
    return result


async def verify(db, ctx, eng, body, contributors, filed_id):
    data = VATCompositionInput.model_validate(body["native_metadata"])
    rows, totals, dependencies, authors = await derive(db, ctx, eng, data)
    if (
        rows != body["rows"]
        or totals != body["control_totals"]
        or fingerprint({"rows": rows}) != body["source_sha256"]
    ):
        raise HTTPException(
            409, "Composed VAT201 boxes no longer agree with their reviewed components"
        )
    contributors.update(authors)
    book_origins = set()
    for identifier in data.source_ids:
        book_origins.update(await origins(db, ctx, eng, identifier))
    if book_origins & await origins(db, ctx, eng, filed_id):
        raise HTTPException(
            422,
            "Composed books and filed return share underlying source evidence; retain independent filed evidence",
        )
    return dependencies
