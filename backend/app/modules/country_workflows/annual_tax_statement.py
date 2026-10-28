"""Declared Indian annual-statement headers, separate from native-format qualification."""

from datetime import date
from typing import Any, Literal

from pydantic import Field, model_validator

from app.modules.jurisdictions.profiles import Strict

TRANSITION = date(2026, 4, 1)
CONTRACT = "india-annual-statement-scope/1"


class AnnualTaxStatement(Strict):
    form: Literal["26AS", "168"]
    pan: str = Field(pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    period_start: date
    period_end: date
    displayed_year_basis: Literal["ASSESSMENT_YEAR", "TAX_YEAR"]
    displayed_year: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    generated_on: date

    @model_validator(mode="after")
    def form_and_year(self):
        start = self.period_start
        if (
            start.month != 4
            or start.day != 1
            or start.year == 9999
            or self.period_end != date(start.year + 1, 3, 31)
        ):
            raise ValueError("Annual statement scope requires one complete April-March tax year")
        modern = start >= TRANSITION
        if self.form != ("168" if modern else "26AS"):
            raise ValueError(
                "Form 26AS ends with previous year 2025-26; Form 168 starts in 2026-27"
            )
        basis = "TAX_YEAR" if modern else "ASSESSMENT_YEAR"
        year = start.year if modern else start.year + 1
        label = f"{year:04d}-{(year + 1) % 100:02d}"
        if self.displayed_year_basis != basis or self.displayed_year != label:
            raise ValueError("Statement displayed year and assessment/tax-year basis disagree")
        if self.generated_on < start:
            raise ValueError("Statement snapshot cannot predate its underlying tax year")
        return self

    def check_record(self, record):
        if record["legal_role"] not in {"deductee", "collectee"}:
            raise ValueError("Annual tax statements support beneficiary credit observations only")
        if (
            record["registration"] != self.pan
            or str(record["tax_year_start"]) != self.period_start.isoformat()
            or str(record["tax_year_end"]) != self.period_end.isoformat()
        ):
            raise ValueError("Annual statement PAN and underlying tax year differ from the record")
        transaction = date.fromisoformat(str(record["transaction_date"]))
        if not self.period_start <= transaction <= self.period_end:
            raise ValueError("Transaction is outside the annual statement underlying year")
        if transaction > self.generated_on:
            raise ValueError("Transaction postdates the declared annual statement snapshot")
        if record["period"] > self.generated_on.strftime("%Y-%m"):
            raise ValueError("Reporting month postdates the declared annual statement snapshot")


def validate_population(tables):
    """Preserve amendment snapshots; never label an unscoped row as a stated form."""
    scopes: list[dict[str, Any]] = []
    for role, rows in tables.items():
        declared = [row for row in rows if row.get("annual_statement") is not None]
        if not declared:
            continue
        if role != "statement":
            raise ValueError("Annual tax statement headers apply only to the statement source")
        if len(declared) != len(rows):
            raise ValueError("A scoped statement source cannot mix declared and unscoped rows")
        identity = None
        versions: dict[str, dict[str, Any]] = {}
        for row in declared:
            scope = AnnualTaxStatement.model_validate(row["annual_statement"])
            scope.check_record(row)
            header = scope.model_dump(mode="json")
            key = tuple(value for field, value in header.items() if field != "generated_on")
            if identity is not None and identity != key:
                raise ValueError("One statement source must use one PAN, form and underlying year")
            identity = key
            version = row["source_version"]
            if version in versions and versions[version] != header:
                raise ValueError("One statement source version has conflicting snapshot headers")
            versions[version] = header
        scopes.extend(
            {"source_version": version, **header} for version, header in sorted(versions.items())
        )
    return scopes
