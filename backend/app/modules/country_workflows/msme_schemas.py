"""Assessed India MSE facts; no inferred registration, eligibility or tax deduction."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.jurisdictions.profiles import Strict

ID = Annotated[str, Field(min_length=1, max_length=120)]
Money = Annotated[Decimal, Field(ge=0, max_digits=28, decimal_places=8, allow_inf_nan=False)]


class MSMEFacts(Strict):
    @model_validator(mode="before")
    @classmethod
    def literal_calendar(cls, value):
        from app.modules.country_workflows.grant_utilisation import calendar_day

        if isinstance(value, dict):
            for key in (
                "scope_start",
                "scope_end",
                "invoice_date",
                "delivery_date",
                "written_objection_date",
                "objection_removed_date",
                "agreed_due_date",
            ):
                if value.get(key) is not None:
                    calendar_day(value[key])
        return value


class MSMESupplierAssessment(MSMEFacts):
    id: ID
    buyer_id: ID
    supplier_id: ID
    classification: Literal["MICRO", "SMALL", "MEDIUM", "OTHER", "UNRESOLVED"]
    eligibility: Literal["ELIGIBLE", "INELIGIBLE", "UNRESOLVED"]
    scope_start: date
    scope_end: date
    evidence_reference: str = Field(default="", max_length=120)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def assessed_scope(self):
        if self.scope_end < self.scope_start or len(self.assessment.strip()) < 10:
            raise ValueError("MSE eligibility needs an ordered assessed scope and meaningful basis")
        if self.eligibility != "UNRESOLVED" and not self.evidence_reference.strip():
            raise ValueError("Resolved MSE eligibility requires a retained evidence reference")
        if self.eligibility == "ELIGIBLE" and self.classification not in {"MICRO", "SMALL"}:
            raise ValueError(
                "Only assessed micro/small suppliers may be eligible for this workflow"
            )
        return self


class MSMEInvoice(MSMEFacts):
    id: ID
    buyer_id: ID
    supplier_id: ID
    reference: ID
    invoice_date: date
    currency: Literal["INR"]
    amount: Money
    assessment_id: ID | None = None
    delivery_date: date | None = None
    acceptance_evidence_reference: str = Field(default="", max_length=120)
    written_objection_date: date | None = None
    objection_removed_date: date | None = None
    objection_evidence_reference: str = Field(default="", max_length=120)
    terms_written: bool
    agreed_due_date: date | None = None
    agreement_evidence_reference: str = Field(default="", max_length=120)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def chronological_facts(self):
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess invoice, acceptance, objection and written-term facts")
        if self.written_objection_date and self.delivery_date:
            if self.written_objection_date < self.delivery_date:
                raise ValueError("Written acceptance objection cannot precede delivery")
        if self.objection_removed_date and (
            not self.written_objection_date
            or self.objection_removed_date < self.written_objection_date
        ):
            raise ValueError("Objection removal requires an ordered written objection")
        if not self.terms_written and (self.agreed_due_date or self.agreement_evidence_reference):
            raise ValueError("No-written-agreement scope cannot supply written payment terms")
        return self


MSME_ROW_TYPES: dict[str, type[BaseModel]] = {
    "msme-supplier-assessments": MSMESupplierAssessment,
    "msme-invoices": MSMEInvoice,
}
MSME_WORKFLOWS: dict[str, tuple[str, list[str], dict[str, str]]] = {
    "india-msme-payment-timing": (
        "India assessed micro/small supplier invoice and bank payment timing",
        ["IN"],
        {
            "assessments": "msme-supplier-assessments",
            "invoices": "msme-invoices",
            "bank": "transactions",
            "allocations": "item-allocations",
        },
    )
}
