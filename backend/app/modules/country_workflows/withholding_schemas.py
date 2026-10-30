"""Assessed withholding records; no statutory rate or entitlement inference."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.modules.country_workflows.annual_tax_statement import AnnualTaxStatement
from app.modules.country_workflows.withholding_pan import MissingPANTreatment, marker
from app.modules.jurisdictions.profiles import Strict

Identifier = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^\S(?:.*\S)?$")]
WithholdingRole = Literal["deductor", "deductee", "collector", "collectee"]


class WithholdingRecord(Strict):
    id: Identifier
    registration: Identifier
    counterparty: Identifier
    legal_role: WithholdingRole
    tax_kind: Literal["TDS", "TCS"]
    rule_reference: Identifier
    tax_year_start: date
    tax_year_end: date
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    transaction_reference: Identifier
    transaction_date: date
    currency: Literal["INR"]
    amount: Decimal = Field(ge=0, max_digits=28, decimal_places=8, allow_inf_nan=False)
    record_status: Literal["current", "superseded", "cancelled"]
    source_reference: Identifier
    source_version: Identifier
    due_date: date | None = None
    payment_date: date | None = None
    pan_treatment: MissingPANTreatment | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    annual_statement: AnnualTaxStatement | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    assessment_evidence_version_id: UUID | None = None
    assessment_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    assessment_kind: Literal["rule", "certificate"] | None = None
    assessment_period_start: date | None = None
    assessment_period_end: date | None = None
    assessment_amount_limit: Decimal | None = Field(
        default=None, ge=0, max_digits=28, decimal_places=8, allow_inf_nan=False
    )

    @field_validator("annual_statement", "pan_treatment", mode="before")
    @classmethod
    def statement_csv(cls, value, info):
        if isinstance(value, str):
            import json

            try:
                decoded = json.loads(value)
            except ValueError:
                label = (
                    "PAN treatment"
                    if info.field_name == "pan_treatment"
                    else "Annual statement CSV scope"
                )
                raise ValueError(f"{label} requires a JSON object") from None
            if not isinstance(decoded, dict):
                label = (
                    "PAN treatment"
                    if info.field_name == "pan_treatment"
                    else "Annual statement CSV scope"
                )
                raise ValueError(f"{label} requires a JSON object")
            return decoded
        return value

    @model_validator(mode="after")
    def assessed_scope(self):
        if self.pan_treatment is not None and (
            marker(self.counterparty) != self.pan_treatment.marker
            or self.pan_treatment.treatment_reference != self.rule_reference
            or self.assessment_kind is None
        ):
            raise ValueError(
                "Missing-PAN treatment must match its source marker, rule reference and explicit retained rule/certificate assessment kind"
            )
        if self.annual_statement is not None:
            self.annual_statement.check_record(self.model_dump(mode="json"))
        binding = (self.assessment_evidence_version_id, self.assessment_sha256)
        if any(value is not None for value in binding) and not all(binding):
            raise ValueError("Assessment evidence ID and SHA-256 must be provided together")
        if self.assessment_kind is not None:
            if self.assessment_period_start is None or self.assessment_period_end is None:
                raise ValueError("Declare the assessment coverage dates")
            if self.assessment_period_end < self.assessment_period_start:
                raise ValueError("Assessment coverage ends before it starts")
            if self.assessment_kind == "certificate" and self.assessment_amount_limit is None:
                raise ValueError("Certificate assessment requires an explicit shared amount limit")
            if self.assessment_kind == "rule" and self.assessment_amount_limit is not None:
                raise ValueError(
                    "An assessment amount limit is a certificate cap, not a tax threshold"
                )
        elif any(
            value is not None
            for value in (
                self.assessment_period_start,
                self.assessment_period_end,
                self.assessment_amount_limit,
                *binding,
            )
        ):
            raise ValueError(
                "Declare whether the retained assessment supports a rule or certificate"
            )
        expected = "TDS" if self.legal_role in {"deductor", "deductee"} else "TCS"
        if self.tax_kind != expected:
            raise ValueError("Legal role and TDS/TCS scheme disagree")
        if not self.tax_year_start <= self.transaction_date <= self.tax_year_end:
            raise ValueError("Transaction must fall within the explicitly assessed tax year")
        month_start = date.fromisoformat(self.period + "-01")
        if not (
            self.tax_year_start.strftime("%Y-%m")
            <= month_start.strftime("%Y-%m")
            <= self.tax_year_end.strftime("%Y-%m")
        ):
            raise ValueError("Reporting month must fall within the assessed tax year")
        return self


WITHHOLDING_WORKFLOWS = {
    "india-withholding-liability": (
        "India deductor / collector liability evidence reconciliation",
        ["IN"],
        {
            "expected": "withholding-records",
            "withheld": "withholding-records",
            "reported": "withholding-records",
            "deposited": "withholding-records",
        },
    ),
    "india-withholding-credit": (
        "India deductee / collectee tax-credit evidence reconciliation",
        ["IN"],
        {
            "books": "withholding-records",
            "statement": "withholding-records",
            "certificate": "withholding-records",
        },
    ),
}
