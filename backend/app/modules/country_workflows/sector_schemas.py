"""Bounded operational audit contracts; rates, tariffs and authority facts are source inputs."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.modules.country_workflows.audit_schemas import Currency, Identifier, Money
from app.modules.jurisdictions.profiles import Strict


class ImportVATLine(Strict):
    """Assessed import values, not a tariff or tax eligibility calculation."""

    id: Identifier
    registration: str = Field(pattern=r"^\d{15}$")
    customs_registration: Identifier
    authority: Identifier
    declaration: Identifier
    line_reference: Identifier
    entry_kind: Literal["declaration", "adjustment"]
    adjustment_reference: str = Field(default="", max_length=120)
    record_version: Identifier
    version_status: Literal["current", "superseded", "cancelled"]
    period_start: date
    period_end: date
    date: date
    currency: Literal["AED"] = "AED"
    net: Money
    tax: Money
    evidence_reference: Identifier
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator(
        "customs_registration",
        "authority",
        "declaration",
        "line_reference",
        "record_version",
        "evidence_reference",
    )
    @classmethod
    def explicit_identifiers(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError(
                "Import identifiers require nonblank exact values without surrounding whitespace"
            )
        return value

    @model_validator(mode="after")
    def scope_and_sign(self):
        if self.period_end < self.period_start:
            raise ValueError("Import VAT return period must be ordered")
        if self.entry_kind == "declaration":
            if self.net < 0 or self.tax < 0 or self.adjustment_reference:
                raise ValueError(
                    "Declaration values must be non-negative without an adjustment reference"
                )
        elif not self.adjustment_reference.strip():
            raise ValueError("Each import adjustment needs its own explicit reference")
        if (
            len(self.assessment.strip()) < 10
            or self.adjustment_reference != self.adjustment_reference.strip()
        ):
            raise ValueError("Import assessment and adjustment references must be explicit")
        return self


class TradeLine(Strict):
    id: Identifier
    shipment: Identifier
    product: Identifier
    counterparty: Identifier
    currency: Currency
    uom: Identifier
    date: date
    quantity: Money = Field(ge=0)
    amount: Money = Field(ge=0)
    valuation_adjustment: Money = Decimal(0)
    declared_duty: Money = Field(default=Decimal(0), ge=0)
    reviewed_duty_rate: Decimal | None = Field(default=None, ge=0, le=1, decimal_places=10)
    duty_rule_reference: str = Field(default="", max_length=120)
    evidence_reference: Identifier


class PriceBand(Strict):
    id: Identifier
    product: Identifier
    currency: Currency
    uom: Identifier
    effective_from: date
    effective_to: date
    minimum_unit_price: Money = Field(ge=0)
    maximum_unit_price: Money = Field(ge=0)
    evidence_reference: Identifier

    @model_validator(mode="after")
    def ordered(self):
        if (
            self.effective_to < self.effective_from
            or self.maximum_unit_price < self.minimum_unit_price
        ):
            raise ValueError("Price band dates and prices must be ordered")
        return self


class ExciseMovement(Strict):
    id: Identifier
    product: Identifier
    location: Identifier
    currency: Currency
    uom: Identifier
    date: date
    kind: Literal[
        "opening", "receipt", "taxable-release", "transfer-in", "transfer-out", "loss", "closing"
    ]
    quantity: Money = Field(ge=0)
    amount: Money = Field(ge=0)
    evidence_reference: Identifier


class ExciseRule(Strict):
    id: Identifier
    product: Identifier
    currency: Currency
    uom: Identifier
    effective_from: date
    effective_to: date
    basis: Literal["quantity", "value"]
    rate: Money = Field(ge=0)
    evidence_reference: Identifier

    @model_validator(mode="after")
    def ordered(self):
        if self.effective_to < self.effective_from:
            raise ValueError("Excise rule dates must be ordered")
        return self


class ExciseReturn(Strict):
    id: Identifier
    product: Identifier
    currency: Currency
    period_start: date
    period_end: date
    amount: Money = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.period_end < self.period_start:
            raise ValueError("Excise return period must be ordered")
        return self


class MetalLine(Strict):
    id: Identifier
    lot: Identifier
    location: Identifier
    date: date
    kind: Literal["opening", "receipt", "issue", "loss", "count"]
    gross_grams: Money = Field(ge=0)
    purity: Decimal = Field(ge=0, le=1, decimal_places=10)
    ownership: Literal["owned", "third-party", "unconfirmed"]
    evidence_reference: Identifier


class EscrowEntry(Strict):
    id: Identifier
    project: Identifier
    account: Identifier
    currency: Currency
    date: date
    reference: Identifier
    counterparty: Identifier
    amount: Money
    authorisation_id: str = Field(default="", max_length=120)
    evidence_reference: Identifier


class EscrowAuthorisation(Strict):
    id: Identifier
    project: Identifier
    account: Identifier
    currency: Currency
    beneficiary: Identifier
    valid_from: date
    valid_to: date
    maximum_amount: Money = Field(ge=0)
    authority_reference: Identifier
    evidence_reference: Identifier

    @model_validator(mode="after")
    def ordered(self):
        if self.valid_to < self.valid_from:
            raise ValueError("Escrow authorisation dates must be ordered")
        return self


class BillingLine(Strict):
    id: Identifier
    case_id: Identifier
    line_reference: Identifier
    party: Identifier
    currency: Currency
    date: date
    kind: Literal["service", "invoice", "settlement", "refund", "commission", "denial"]
    quantity: Money = Field(ge=0)
    amount: Money = Field(ge=0)
    unit_tariff: Money | None = Field(default=None, ge=0)
    approved: bool
    evidence_reference: Identifier


class ConstructionProject(Strict):
    id: Identifier
    currency: Currency
    reporting_date: date
    contract_price: Money = Field(gt=0)
    constrained_variations: Money = Field(ge=0)
    actual_cost: Money = Field(ge=0)
    cost_to_complete: Money = Field(ge=0)
    billed_to_date: Money = Field(ge=0)
    recorded_revenue: Money = Field(ge=0)
    recorded_retention: Money = Field(ge=0)
    certified_retention: Money = Field(ge=0)
    over_time_assessment: str = Field(min_length=10, max_length=2000)
    variation_evidence: Identifier
    certificate_evidence: Identifier


SECTOR_ROW_TYPES: dict[str, type[Strict]] = {
    "import-vat-lines": ImportVATLine,
    "trade-lines": TradeLine,
    "price-bands": PriceBand,
    "excise-movements": ExciseMovement,
    "excise-rules": ExciseRule,
    "excise-returns": ExciseReturn,
    "metal-lines": MetalLine,
    "escrow-entries": EscrowEntry,
    "escrow-authorisations": EscrowAuthorisation,
    "billing-lines": BillingLine,
    "construction-projects": ConstructionProject,
}
SECTOR_WORKFLOWS: dict[str, tuple[str, list[str], dict[str, str]]] = {
    "uae-import-vat": (
        "UAE import VAT declarations / portal / books review",
        ["AE"],
        {"customs": "import-vat-lines", "portal": "import-vat-lines", "books": "import-vat-lines"},
    ),
    "customs-reconciliation": (
        "Customs / invoice / goods receipt reconciliation",
        ["AE"],
        {"declarations": "trade-lines", "invoices": "trade-lines", "receipts": "trade-lines"},
    ),
    "trade-document-review": (
        "Trade shipment / invoice / payment and sourced price review",
        [],
        {
            "invoices": "trade-lines",
            "shipments": "trade-lines",
            "payments": "trade-lines",
            "prices": "price-bands",
        },
    ),
    "excise-reconciliation": (
        "Excise stock conservation and reviewed tax/return comparison",
        ["AE"],
        {"movements": "excise-movements", "rules": "excise-rules", "returns": "excise-returns"},
    ),
    "gold-reconciliation": (
        "Gold gross/fine gram movement to count comparison",
        [],
        {"books": "metal-lines", "counts": "metal-lines"},
    ),
    "escrow-disbursements": (
        "Project escrow bank matching and authorised payment limits",
        ["AE"],
        {
            "books": "escrow-entries",
            "bank": "escrow-entries",
            "authorisations": "escrow-authorisations",
        },
    ),
    "hospitality-revenue": (
        "Hospitality service / invoice / net settlement bridge",
        [],
        {"services": "billing-lines", "invoices": "billing-lines", "settlements": "billing-lines"},
    ),
    "healthcare-billing": (
        "Healthcare service / tariff / invoice / remittance bridge",
        [],
        {"services": "billing-lines", "invoices": "billing-lines", "settlements": "billing-lines"},
    ),
    "construction-contracts": (
        "Construction cost-to-cost revenue and retention review",
        [],
        {"projects": "construction-projects"},
    ),
}
