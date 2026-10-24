import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.modules.audit_execution.schemas import Body, Strict
from app.modules.ifrs.schemas import Money, Nonnegative, Positive, Rate
from app.modules.jurisdictions.ae.registration import RegistrationPolicy


class Rule(Body):
    registration_parameters: RegistrationPolicy | None = None
    rule_key: str = Field(min_length=1, max_length=100)
    rule_version: int = Field(ge=1)
    category: Literal[
        "output",
        "input",
        "invoice",
        "return",
        "einvoice",
        "integrity",
        "employee",
        "adjustment",
        "registration",
    ]
    source_id: str
    article: str = Field(default="", max_length=100)
    effective_from: date
    effective_to: date | None = None
    known_from: date
    source_document_version: str = Field(min_length=1, max_length=300)
    technical_review: str = Field(min_length=1, max_length=6000)
    conditions: str = Field(min_length=1, max_length=6000)
    exceptions: str = Field(min_length=1, max_length=6000)
    standard_rate: Rate = Decimal("0.05")
    simplified_limit: Nonnegative = Decimal("10000")
    active: bool = True


class Profile(Body):
    trn: str = Field(pattern=r"^\d{15}$")
    registration_status: Literal["REGISTERED", "PENDING", "DEREGISTERED", "NOT_REGISTERED"]
    registered_from: date
    filing_frequency: Literal["monthly", "quarterly", "assigned"]
    period_start: date
    period_end: date
    legal_as_of: date
    accounting_basis: Literal["accrual", "cash_assessed"] = "accrual"
    vat_group_reference: str = Field(default="", max_length=300)
    vat_group_approval_evidence_id: uuid.UUID | None = None
    activities: str = Field(min_length=1, max_length=4000)
    input_recovery_assessment: str = Field(min_length=1, max_length=4000)
    jurisdictions: list[str] = Field(min_length=1, max_length=30)
    rules: dict[str, uuid.UUID] = Field(max_length=15)
    output_control_codes: list[str] = Field(min_length=1, max_length=30)
    input_control_codes: list[str] = Field(min_length=1, max_length=30)
    filing_obligations: str = Field(min_length=1, max_length=4000)
    holidays: list[date] = Field(default_factory=list, max_length=100)
    calendar_review: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def dates(self):
        if self.period_end < self.period_start:
            raise ValueError("Invalid VAT period")
        return self


class PropertyFacts(Strict):
    property_type: Literal[
        "residential", "commercial", "bare_land", "mixed", "serviced_accommodation", "other"
    ]
    transaction_nature: Literal["sale", "lease", "other"]
    location: str = Field(min_length=1, max_length=1000)
    completion_date: date | None = None
    first_supply_date: date | None = None
    contractual_facts: str = Field(min_length=10, max_length=4000)
    legal_conditions_assessment: str = Field(min_length=10, max_length=4000)
    unresolved_facts: list[str] = Field(default_factory=list, max_length=30)


class Invoice(Body):
    supply_context: Literal["ordinary", "property"] = "ordinary"
    property_facts: PropertyFacts | None = None
    profile_id: uuid.UUID
    rule_id: uuid.UUID
    invoice_rule_id: uuid.UUID
    direction: Literal["sale", "purchase"]
    invoice_number: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=1)
    issue_date: date
    supply_date: date
    tax_point: date
    tax_point_basis: str = Field(min_length=1, max_length=3000)
    document_type: Literal["invoice", "credit_note", "debit_note"] = "invoice"
    invoice_type: Literal["full", "simplified"] = "full"
    document_label: str = Field(default="Tax Invoice", max_length=100)
    original_invoice_id: uuid.UUID | None = None
    supply_reference: str | None = Field(default=None, max_length=200)
    supply_stage: Literal["ordinary", "advance", "final", "cancellation"] = "ordinary"
    supply_type: Literal["goods", "services", "mixed"] | None = None
    supplier_name: str = Field(min_length=1, max_length=300)
    supplier_address: str = Field(default="", max_length=1000)
    supplier_trn: str = Field(default="", pattern=r"^(\d{15})?$")
    supplier_jurisdiction: str = Field(min_length=2, max_length=2)
    customer_name: str = Field(default="", max_length=300)
    customer_address: str = Field(default="", max_length=1000)
    customer_trn: str = Field(default="", pattern=r"^(\d{15})?$")
    customer_registered: bool
    customer_jurisdiction: str = Field(min_length=2, max_length=2)
    description: str = Field(min_length=1, max_length=4000)
    quantity: Positive = Decimal(1)
    unit_price: Nonnegative
    amount: Nonnegative
    discount: Nonnegative = Decimal(0)
    tax_inclusive: bool = False
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    exchange_rate: Positive = Decimal(1)
    exchange_rate_source: str = Field(min_length=1, max_length=1000)
    treatment: Literal[
        "standard",
        "zero",
        "exempt",
        "outside",
        "reverse_services",
        "import_goods",
        "deemed",
        "unresolved",
    ]
    tax_rate: Rate
    declared_net: Money
    declared_tax: Money
    declared_gross: Money
    emirate: Literal[
        "Abu Dhabi", "Dubai", "Sharjah", "Ajman", "Umm Al Quwain", "Ras Al Khaimah", "Fujairah"
    ]
    place_of_supply_assessment: str = Field(min_length=1, max_length=4000)
    treatment_facts_complete: bool
    reverse_charge_statement: str = Field(default="", max_length=1000)
    recovery_treatment: Literal["full", "blocked", "partial", "review"] = "review"
    recovery_percentage: Rate = Decimal(0)
    recovery_basis: str = Field(min_length=1, max_length=4000)
    recovery_evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    employee_expense: bool = False
    employee_rule_id: uuid.UUID | None = None
    employee_conditions_confirmed: bool = False
    integrity_review_evidence_id: uuid.UUID | None = None
    supplier_annual_past: Nonnegative | None = None
    supplier_annual_expected: Nonnegative | None = None
    related_party: bool = False
    paid_amount: Nonnegative = Decimal(0)
    net_line_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    output_tax_line_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    input_tax_line_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    evidence_record_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)
    ocr_state: Literal["NOT_PROCESSED", "HUMAN_TRANSCRIBED", "EXTRACTED_UNVERIFIED", "VERIFIED"] = (
        "HUMAN_TRANSCRIBED"
    )
    ocr_evidence_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def property_context(self):
        if self.supply_context == "property" and self.property_facts is None:
            raise ValueError(
                "Property VAT review requires property type, nature, location and contractual/condition facts"
            )
        if (
            self.property_facts
            and self.property_facts.unresolved_facts
            and self.treatment_facts_complete
        ):
            raise ValueError(
                "Unresolved property facts cannot be marked complete for VAT treatment"
            )
        return self


class Adjustment(Body):
    profile_id: uuid.UUID
    rule_id: uuid.UUID
    box: Literal["1", "2", "3", "4", "5", "6", "7", "9", "10"]
    category: Literal[
        "bad_debt", "import_adjustment", "recovery_adjustment", "voluntary_disclosure", "other"
    ]
    net_amount: Money
    tax_amount: Money
    rationale: str = Field(min_length=1, max_length=6000)
    statutory_conditions_confirmed: bool
    evidence_record_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)
    ledger_line_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class Recovery(Body):
    profile_id: uuid.UUID
    rule_id: uuid.UUID
    method: Literal["partial_exemption", "capital_asset_scheme", "annual_adjustment"]
    total_input: Nonnegative
    approved_recovery_percentage: Rate
    previously_recovered: Nonnegative
    statutory_conditions_confirmed: bool
    methodology: str = Field(min_length=1, max_length=6000)
    evidence_record_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)


class EInvoicing(Body):
    amendment_review_evidence_id: uuid.UUID | None = None
    amendment_scope_assessment: str = Field(default="", max_length=4000)
    profile_id: uuid.UUID
    rule_id: uuid.UUID
    annual_revenue: Nonnegative
    government_entity: bool
    in_scope_b2b_b2g: bool
    scope_assessment: str = Field(min_length=1, max_length=6000)
    asp_name: str = Field(default="", max_length=300)
    asp_appointed_on: date | None = None
    asp_appointment_evidence_id: uuid.UUID | None = None
    accreditation_checked_on: date | None = None
    identifiers_complete: bool
    source_mapping_complete: bool
    sandbox_tested: bool
    evidence_record_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)


class Return(Body):
    run_id: uuid.UUID
    filing_state: Literal[
        "DRAFT",
        "PREPARED",
        "REVIEW_REQUIRED",
        "APPROVED",
        "READY_FOR_EXTERNAL_FILING",
        "FILED_EXTERNALLY",
    ]
    checklist_complete: bool
    filing_evidence_id: uuid.UUID | None = None
    external_reference: str = Field(default="", max_length=300)
    rationale: str = Field(min_length=1, max_length=6000)


class SandboxRequest(Strict):
    invoice_id: uuid.UUID
    idempotency_key: str = Field(min_length=8, max_length=100)
    buyer_endpoint_id: str = Field(min_length=1, max_length=100)
    supplier_endpoint_id: str = Field(min_length=1, max_length=100)
    schema_version: Literal["auditos-pint-ae-subset/1.0"]
    simulate: Literal["accept", "reject", "timeout"] = "accept"


BODIES: dict[str, type[Body]] = {
    "rule": Rule,
    "profile": Profile,
    "invoice": Invoice,
    "adjustment": Adjustment,
    "recovery": Recovery,
    "einvoicing": EInvoicing,
    "return": Return,
}
