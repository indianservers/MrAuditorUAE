"""Reviewed item-to-section/source declarations; no semantic/legal sufficiency inferred."""

import uuid
from datetime import date
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, ValidationError, model_validator

from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory.form26_index import manifest
from app.modules.regulatory.tax_forms import INDIA_TRANSITION


class SupportingSource(Strict):
    kind: Literal["record", "finding", "journal", "snapshot", "sample", "intelligence", "ml"]
    id: uuid.UUID


class ItemMapping(Strict):
    key: str = Field(min_length=1, max_length=100)
    disposition: Literal["REQUIRED", "NOT_APPLICABLE"]
    section_index: int = Field(ge=0, le=29, strict=True)
    supporting_sources: list[SupportingSource] = Field(min_length=1, max_length=100)
    assessment: str = Field(min_length=10, max_length=2000)


class WorkpaperReportScope(Strict):
    preset_id: str = Field(max_length=100)
    period_start: date
    period_end: date
    items: list[ItemMapping] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def declared(self):
        pack = manifest(self.preset_id)
        closing_year = self.period_start.year + (self.period_start.month >= 4)
        if (
            self.period_start < INDIA_TRANSITION
            or self.period_end < self.period_start
            or closing_year > 9999
            or self.period_end > date(closing_year, 3, 31)
        ):
            raise ValueError(
                "Form 26 workpaper scope requires one ordered modern Indian tax period"
            )
        keys = [item.key for item in self.items]
        if len(set(keys)) != len(keys) or not set(keys) <= {r["key"] for r in pack["requirements"]}:
            raise ValueError(
                "Workpaper item references must be distinct members of the selected preset"
            )
        for item in self.items:
            refs = [(source.kind, source.id) for source in item.supporting_sources]
            if len(item.assessment.strip()) < 10 or len(set(refs)) != len(refs):
                raise ValueError(
                    "Every item needs a meaningful assessment and distinct supporting links"
                )
            if item.disposition == "NOT_APPLICABLE" and item.key not in pack["not_applicable_keys"]:
                raise ValueError("This preset item cannot be declared not-applicable")
        return self


def validate_bindings(scope, sections, sources):
    links = {(source.kind, source.id) for source in sources}
    for item in scope.items:
        if (
            item.section_index >= len(sections)
            or len(sections[item.section_index].text.strip()) < 10
        ):
            raise ValueError(
                "Report item mappings require an existing substantive workpaper section"
            )
        if not {(source.kind, source.id) for source in item.supporting_sources} <= links:
            raise ValueError(
                "Every mapped support must already be a protected workpaper source link"
            )


def require_mapping(config, block, body):
    from app.modules.audit_execution.schemas import Section, Source

    try:
        scope = WorkpaperReportScope.model_validate(body.get("report_requirement_scope"))
        validate_bindings(
            scope,
            [Section.model_validate(s) for s in body.get("sections", [])],
            [Source.model_validate(s) for s in body.get("sources", [])],
        )
    except (ValidationError, ValueError):
        raise HTTPException(
            409,
            "Declare item coverage in the workpaper and independently review its section/source mappings",
        ) from None
    tax_scope = config.tax_audit_scope
    if (
        scope.preset_id != config.requirements_pack
        or not tax_scope
        or (scope.period_start, scope.period_end)
        != (tax_scope.tax_period_start, tax_scope.tax_period_end)
    ):
        raise HTTPException(
            409, "Workpaper report preset and tax period must match this exact report scope"
        )
    mappings = {item.key: item for item in scope.items}
    requirements = {item.key: item for item in config.requirements}
    for key in block.requirement_keys:
        if key not in mappings or mappings[key].disposition != requirements[key].disposition:
            raise HTTPException(
                409,
                "Report item coverage/applicability must agree with its reviewed workpaper declaration",
            )
