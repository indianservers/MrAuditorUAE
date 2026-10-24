import uuid
from datetime import date
from decimal import Decimal, localcontext
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.modules.audit_execution.schemas import Body, Strict

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]
Positive = Annotated[Money, Field(gt=0)]
Nonnegative = Annotated[Money, Field(ge=0)]
Rate = Annotated[Decimal, Field(ge=0, le=1, decimal_places=10, allow_inf_nan=False)]


class AccountingInput(Body):
    profile_id: uuid.UUID | None = None


class ReportingProfile(Body):
    snapshot_id: uuid.UUID
    comparative_snapshot_id: uuid.UUID | None = None
    comparative_profile_id: uuid.UUID | None = None
    comparative_engagement_id: uuid.UUID | None = None
    framework: Literal["full_ifrs"] = "full_ifrs"
    presentation_currency: str = Field(pattern=r"^[A-Z]{3}$")
    rounding_precision: int = Field(default=2, ge=0, le=8)
    presentation_materiality: Nonnegative = Decimal(0)
    suppress_zero: bool = True
    early_ifrs18: bool = False
    early_ifrs19: bool = False
    election_rationale: str = Field(default="", max_length=4000)
    ifrs19_elected: bool = False
    is_subsidiary: bool = False
    public_accountability: bool = True
    parent_public_ifrs_consolidated: bool = False
    technical_validation: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def elections(self):
        if (self.early_ifrs18 or self.early_ifrs19) and not self.election_rationale.strip():
            raise ValueError("Early adoption requires a documented election")
        if self.ifrs19_elected and (
            not self.is_subsidiary
            or self.public_accountability
            or not self.parent_public_ifrs_consolidated
        ):
            raise ValueError("IFRS 19 eligibility criteria are not satisfied")
        return self


class Allocation(Strict):
    line_code: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    section: Literal["assets", "liabilities", "equity", "income", "expenses", "oci"]
    weight: Positive = Decimal(1)
    note: str = Field(min_length=1, max_length=100)
    category: Literal["operating", "investing", "financing", "tax", "discontinued"] = "operating"
    is_cash: bool = False
    cash_flow_role: Literal["none", "working_capital_asset", "working_capital_liability"] = "none"
    current_noncurrent: Literal["current", "noncurrent", "equity", "not_applicable"] = (
        "not_applicable"
    )
    related_party_category: str = Field(default="", max_length=200)
    disaggregation: str = Field(default="", max_length=1000)
    netting_rationale: str = Field(default="", max_length=4000)


class AccountMapping(Strict):
    account_code: str = Field(min_length=1, max_length=100)
    allocations: list[Allocation] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def weights(self):
        if sum((a.weight for a in self.allocations), Decimal(0)) != 1:
            raise ValueError("Account allocation weights must total exactly one")
        return self


class Mapping(Body):
    profile_id: uuid.UUID
    accounts: list[AccountMapping] = Field(min_length=1, max_length=20000)
    rationale: str = Field(min_length=1, max_length=4000)


class JournalLeg(Strict):
    account_code: str = Field(min_length=1, max_length=100)
    debit: Nonnegative = Decimal(0)
    credit: Nonnegative = Decimal(0)

    @model_validator(mode="after")
    def one_side(self):
        if (self.debit > 0) == (self.credit > 0):
            raise ValueError("Exactly one debit/credit amount must be positive")
        return self


class Adjustment(Body):
    profile_id: uuid.UUID
    adjustment_date: date
    adjustment_type: Literal[
        "journal",
        "reclassification",
        "prior_period",
        "reversal",
        "disclosure_only",
        "consolidation",
    ] = "journal"
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    standard: str = Field(min_length=1, max_length=30)
    narration: str = Field(min_length=1, max_length=4000)
    legs: list[JournalLeg] = Field(default_factory=list, max_length=200)
    calculation_run_id: uuid.UUID | None = None
    calculation_component: Literal["primary", "oci", "current_tax"] | None = None
    reversal_of: uuid.UUID | None = None

    @model_validator(mode="after")
    def balanced(self):
        if self.calculation_component and not self.calculation_run_id:
            raise ValueError("A generated journal component requires its calculation run")
        with localcontext() as precision:
            precision.prec = 48
            imbalance = sum((leg.debit - leg.credit for leg in self.legs), Decimal(0))
        if self.adjustment_type == "disclosure_only":
            if self.legs:
                raise ValueError("Disclosure-only observations cannot post balances")
        elif len(self.legs) < 2 or imbalance != 0:
            raise ValueError("Adjustment journal must balance exactly")
        return self


class Payment(Strict):
    date: date
    amount: Nonnegative


class Lease(AccountingInput):
    commencement: date
    end_date: date
    annual_discount_rate: Rate
    payments: list[Payment] = Field(min_length=1, max_length=1200)
    initial_direct_costs: Nonnegative = Decimal(0)
    incentive_received: Nonnegative = Decimal(0)
    restoration_obligation: Nonnegative = Decimal(0)
    variable_payments_excluded: Nonnegative = Decimal(0)
    recognition_assessment: str = Field(min_length=1, max_length=4000)
    options_assessment: str = Field(min_length=1, max_length=4000)
    previous_run_id: uuid.UUID | None = None
    remeasurement_reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def dates(self):
        if self.end_date <= self.commencement or any(
            p.date < self.commencement or p.date > self.end_date for p in self.payments
        ):
            raise ValueError("Lease dates/payment dates are inconsistent")
        if self.previous_run_id and not self.remeasurement_reason.strip():
            raise ValueError("Remeasurement requires a documented reason")
        return self


class CreditScenario(Strict):
    name: str = Field(min_length=1, max_length=100)
    probability: Rate
    pd_12_month: Rate
    pd_lifetime: Rate
    lgd: Rate
    forward_multiplier: Annotated[Decimal, Field(ge=0, le=10)] = Decimal(1)
    cash_shortfall: Nonnegative | None = None


class Exposure(Strict):
    reference: str = Field(min_length=1, max_length=200)
    amount: Nonnegative
    stage: Literal[1, 2, 3]
    years_to_shortfall: Nonnegative = Decimal(1)
    segment: str = Field(default="default", max_length=100)


class ECL(AccountingInput):
    approach: Literal["general", "simplified", "provision_matrix"]
    exposures: list[Exposure] = Field(min_length=1, max_length=20000)
    scenarios: list[CreditScenario] = Field(min_length=1, max_length=20)
    effective_interest_rate: Rate
    historical_data_source: str = Field(min_length=1, max_length=4000)
    sicr_methodology: str = Field(min_length=1, max_length=4000)
    default_definition: str = Field(min_length=1, max_length=4000)
    write_off_policy: str = Field(min_length=1, max_length=4000)
    segment_loss_rates: dict[str, Rate] = Field(default_factory=dict, max_length=100)

    @model_validator(mode="after")
    def probabilities(self):
        if len({e.reference for e in self.exposures}) != len(self.exposures):
            raise ValueError("Duplicate receivable exposure reference")
        if len({s.name for s in self.scenarios}) != len(self.scenarios):
            raise ValueError("Duplicate ECL scenario name")
        if any(s.pd_lifetime < s.pd_12_month for s in self.scenarios):
            raise ValueError("Lifetime PD cannot be below 12-month PD")
        if sum((s.probability for s in self.scenarios), Decimal(0)) != 1:
            raise ValueError("Scenario probabilities must total exactly one")
        if self.approach == "provision_matrix" and any(
            e.segment not in self.segment_loss_rates for e in self.exposures
        ):
            raise ValueError("Every segment requires an approved historical loss rate")
        return self


class Instrument(AccountingInput):
    initial_amount: Positive
    initial_date: date
    cash_flows: list[Payment] = Field(min_length=1, max_length=1200)
    classification: Literal["amortised_cost", "fvoci", "fvtpl"]
    business_model_and_sppi: str = Field(min_length=1, max_length=4000)
    asset_or_liability: Literal["asset", "liability"]


class Obligation(Strict):
    reference: str = Field(min_length=1, max_length=100)
    standalone_price: Positive
    recognition: Literal["point_in_time", "over_time"]
    satisfied_on: date | None = None
    progress: Rate = Decimal(0)
    over_time_justification: str = Field(default="", max_length=4000)


class Revenue(AccountingInput):
    contract_reference: str = Field(min_length=1, max_length=200)
    contract_assessment: str = Field(min_length=1, max_length=4000)
    reporting_date: date
    fixed_price: Nonnegative
    constrained_variable_consideration: Nonnegative = Decimal(0)
    constraint_rationale: str = Field(min_length=1, max_length=4000)
    billed_to_date: Nonnegative
    obligations: list[Obligation] = Field(min_length=1, max_length=100)
    modification_analysis: str = Field(default="No modification documented", max_length=4000)


class TaxDifference(Strict):
    reference: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=1, max_length=100)
    rate_source: str = Field(min_length=1, max_length=1000)
    rate_effective_date: date
    carrying_amount: Money
    tax_base: Money
    item_type: Literal["asset", "liability", "tax_loss"]
    tax_rate: Rate
    previous_deferred_balance: Money = Decimal(0)
    recognise_dta: bool = False
    recognition_rationale: str = Field(min_length=1, max_length=4000)
    exception_applied: bool = False
    exception_rationale: str = Field(default="", max_length=4000)
    allocation: Literal["profit_loss", "oci", "equity", "business_combination"] = "profit_loss"
    expected_recovery_or_settlement: str = Field(default="", max_length=4000)
    recoverability_evidence: str = Field(default="", max_length=1000)


class DeferredTax(AccountingInput):
    differences: list[TaxDifference] = Field(min_length=1, max_length=10000)
    current_tax: Nonnegative = Decimal(0)
    current_tax_source: str = Field(min_length=1, max_length=4000)
    current_tax_run_id: uuid.UUID | None = None


class Asset(Strict):
    reference: str = Field(min_length=1, max_length=100)
    asset_class: Literal["ppe", "investment_property", "held_for_sale", "intangible"] = "ppe"
    component_of: str = Field(default="", max_length=100)
    cost: Nonnegative
    residual: Nonnegative
    capitalisation_date: date
    available_for_use_date: date | None = None
    available_for_use_evidence: str = Field(default="", max_length=1000)
    construction_in_progress: bool = False
    location: str = Field(default="", max_length=200)
    ownership_evidence: str = Field(default="", max_length=1000)
    physical_verification: Literal["not_verified", "verified", "exception"] = "not_verified"
    useful_life_years: Positive
    method: Literal["straight_line", "diminishing_balance"]
    diminishing_rate: Rate = Decimal(0)
    opening_accumulated: Nonnegative = Decimal(0)
    impairment: Nonnegative = Decimal(0)
    disposal_date: date | None = None
    proceeds: Nonnegative = Decimal(0)
    revaluation_increment: Money = Decimal(0)
    revaluation_assessment: str = Field(default="", max_length=4000)
    estimate_change_date: date | None = None
    revised_remaining_life_years: Positive | None = None
    revised_residual: Nonnegative | None = None
    estimate_change_rationale: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def asset_dates(self):
        if self.available_for_use_date and self.available_for_use_date < self.capitalisation_date:
            raise ValueError("Available-for-use date precedes acquisition/capitalisation")
        if self.available_for_use_date and not self.available_for_use_evidence.strip():
            raise ValueError("Available-for-use date requires evidence")
        if self.disposal_date and self.disposal_date < self.capitalisation_date:
            raise ValueError("Disposal precedes acquisition")
        if self.method == "diminishing_balance" and not self.diminishing_rate:
            raise ValueError("Diminishing-balance method requires an approved positive rate")
        if self.estimate_change_date and (
            self.method != "straight_line"
            or not self.revised_remaining_life_years
            or self.revised_residual is None
            or not self.estimate_change_rationale.strip()
        ):
            raise ValueError(
                "Estimate changes require straight-line remaining life, residual and rationale"
            )
        if not self.estimate_change_date and (
            self.revised_remaining_life_years is not None or self.revised_residual is not None
        ):
            raise ValueError("Revised estimates require an effective date")
        return self


class FixedAssets(AccountingInput):
    period_start: date
    period_end: date
    assets: list[Asset] = Field(min_length=1, max_length=20000)


class Impairment(AccountingInput):
    cgu: str = Field(min_length=1, max_length=200)
    carrying_amount: Nonnegative
    cash_flows: list[Money] = Field(min_length=1, max_length=100)
    discount_rate: Rate
    fair_value_less_disposal_costs: Nonnegative
    goodwill_included: Nonnegative = Decimal(0)
    forecast_source: str = Field(min_length=1, max_length=4000)
    reversal_requested: Nonnegative = Decimal(0)
    reversal_cap_excluding_goodwill: Nonnegative = Decimal(0)


class Provision(AccountingInput):
    recognition: Literal["provision", "contingent_liability", "contingent_asset"]
    obligation_assessment: str = Field(min_length=1, max_length=4000)
    probability_assessment: str = Field(min_length=1, max_length=4000)
    best_estimate: Nonnegative
    settlement_years: Nonnegative
    discount_rate: Rate
    opening: Nonnegative
    utilisation: Nonnegative = Decimal(0)
    reversals: Nonnegative = Decimal(0)


class CashFlow(Body):
    profile_id: uuid.UUID
    method: Literal["indirect", "direct"] = "indirect"
    noncash_adjustments: Money = Decimal(0)
    investing: Money = Decimal(0)
    financing: Money = Decimal(0)
    exchange_effect: Money = Decimal(0)
    direct_operating_receipts: Nonnegative = Decimal(0)
    direct_operating_payments: Nonnegative = Decimal(0)
    policy: str = Field(min_length=1, max_length=4000)
    movement_schedule_source: str = Field(min_length=1, max_length=4000)


class GroupMember(Strict):
    engagement_id: uuid.UUID
    financial_run_id: uuid.UUID
    ownership: Rate
    power: bool
    variable_returns: bool
    ability_to_affect_returns: bool
    control_rationale: str = Field(min_length=1, max_length=4000)
    closing_rate: Positive
    average_rate: Positive
    historical_rate: Positive
    rate_source: str = Field(min_length=1, max_length=1000)
    rate_date: date
    net_assets_at_acquisition: Money = Decimal(0)
    consideration: Nonnegative = Decimal(0)
    nci_at_acquisition: Nonnegative = Decimal(0)
    acquisition_type: Literal[
        "parent", "business_combination", "common_control", "asset_acquisition", "equity_method"
    ]
    accounting_policy: str = Field(min_length=1, max_length=4000)
    control_effective_from: date | None = None
    control_effective_to: date | None = None
    hyperinflationary: bool = False
    average_rate_representative: bool = True
    opening_rate: Positive | None = None


class IntercompanyBalance(Strict):
    reference: str = Field(min_length=1, max_length=100)
    from_engagement_id: uuid.UUID
    to_engagement_id: uuid.UUID
    debit_line: str
    credit_line: str
    receivable: Nonnegative
    payable: Nonnegative
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    difference_type: Literal[
        "matched", "timing", "currency", "missing_entry", "classification", "disputed"
    ]
    evidence: str = Field(min_length=1, max_length=4000)


class Elimination(Strict):
    reference: str = Field(min_length=1, max_length=100)
    debit_line: str
    credit_line: str
    amount: Positive
    reason: str = Field(min_length=1, max_length=4000)
    source_record_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    intercompany_reference: str = Field(default="", max_length=100)


class Consolidation(Body):
    presentation_currency: str = Field(pattern=r"^[A-Z]{3}$")
    members: list[GroupMember] = Field(min_length=2, max_length=100)
    eliminations: list[Elimination] = Field(default_factory=list, max_length=1000)
    unrealised_profit: Nonnegative = Decimal(0)
    unrealised_profit_inventory_line: str = Field(default="", max_length=100)
    unrealised_profit_expense_line: str = Field(default="", max_length=100)
    unrealised_profit_source: str = Field(default="", max_length=4000)
    intercompany: list[IntercompanyBalance] = Field(default_factory=list, max_length=10000)


class StockReceipt(Strict):
    reference: str = Field(min_length=1, max_length=100)
    date: date
    sequence: int = Field(default=0, ge=0)
    quantity: Positive
    unit_cost: Nonnegative
    landed_cost: Nonnegative = Decimal(0)
    evidence: str = Field(min_length=1, max_length=1000)
    transaction_type: Literal["purchase", "transfer_in"] = "purchase"
    transfer_reference: str = Field(default="", max_length=100)


class StockIssue(Strict):
    reference: str = Field(min_length=1, max_length=100)
    date: date
    sequence: int = Field(default=0, ge=0)
    quantity: Positive
    evidence: str = Field(min_length=1, max_length=1000)
    transaction_type: Literal["dispatch", "transfer_out"] = "dispatch"
    transfer_reference: str = Field(default="", max_length=100)


class InventoryItem(Strict):
    reference: str = Field(min_length=1, max_length=100)
    sku: str = Field(default="", max_length=100)
    uom: str = Field(min_length=1, max_length=30)
    location: str = Field(min_length=1, max_length=200)
    ownership: Literal["owned", "custody_only"]
    opening_quantity: Nonnegative
    opening_unit_cost: Nonnegative
    receipts: list[StockReceipt] = Field(default_factory=list, max_length=10000)
    issues: list[StockIssue] = Field(default_factory=list, max_length=10000)
    expected_closing_quantity: Nonnegative
    selling_price: Nonnegative
    completion_cost: Nonnegative = Decimal(0)
    selling_cost: Nonnegative = Decimal(0)
    nrv_evidence: str = Field(min_length=1, max_length=1000)
    prior_write_down_remaining: Nonnegative = Decimal(0)


class Inventory(Body):
    profile_id: uuid.UUID
    period_start: date
    period_end: date
    method: Literal["fifo", "weighted_average"]
    policy_version: str = Field(min_length=1, max_length=200)
    items: list[InventoryItem] = Field(min_length=1, max_length=10000)


class EmployeeBenefits(Body):
    """Aggregate accounting bridge; employee masters remain in restricted HR systems."""

    profile_id: uuid.UUID
    policy_version: str = Field(min_length=1, max_length=200)
    employment_framework: Literal["uae_mainland", "difc", "adgm", "other"]
    framework_assessment: str = Field(min_length=1, max_length=4000)
    scheme: Literal["defined_benefit", "defined_contribution"]
    measurement_source: str = Field(min_length=1, max_length=4000)
    actuarial_report_reference: str = Field(default="", max_length=1000)
    opening_obligation: Nonnegative
    current_service_cost: Nonnegative
    past_service_cost: Money = Decimal(0)
    net_interest: Money
    remeasurement_oci: Money
    settlements: Nonnegative
    closing_ledger_provision: Nonnegative
    statutory_settlement_estimate: Nonnegative | None = None
    payroll_expense: Nonnegative
    opening_payroll_payable: Nonnegative
    payroll_deductions: Nonnegative
    confirmed_bank_payments: Nonnegative
    closing_payroll_ledger_payable: Nonnegative
    leave_bonus_accrual: Nonnegative = Decimal(0)


class AccountingPolicy(Body):
    profile_id: uuid.UUID
    category: Literal[
        "material_policy",
        "judgment",
        "estimation_uncertainty",
        "policy_change",
        "estimate_change",
        "prior_period_error",
        "subsequent_event",
        "going_concern",
        "related_party",
        "commitment",
        "contingency",
    ]
    standard: str = Field(min_length=1, max_length=100)
    applicable_from: date
    facts: str = Field(min_length=1, max_length=8000)
    assessment: str = Field(min_length=1, max_length=8000)
    evidence_reference: str = Field(min_length=1, max_length=1000)
    note_id: uuid.UUID | None = None


class Disclosure(Body):
    profile_id: uuid.UUID
    standard: str
    category: str = Field(min_length=1, max_length=200)
    applicability: Literal["applicable", "not_applicable", "unknown"]
    rationale: str = Field(min_length=1, max_length=4000)
    note_id: uuid.UUID | None = None
    checklist_version: str = Field(default="original-checklist/1", max_length=100)


class Note(Body):
    profile_id: uuid.UUID
    note_reference: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=12000)
    linked_line_codes: list[str] = Field(default_factory=list, max_length=100)
    schedule_run_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    ai_authored: bool = False


class FinancialApproval(Body):
    run_id: uuid.UUID
    release_rationale: str = Field(min_length=1, max_length=4000)


BODIES: dict[str, type[Body]] = {
    "profile": ReportingProfile,
    "mapping": Mapping,
    "adjustment": Adjustment,
    "lease": Lease,
    "ecl": ECL,
    "instrument": Instrument,
    "revenue": Revenue,
    "deferred-tax": DeferredTax,
    "fixed-assets": FixedAssets,
    "inventory": Inventory,
    "employee-benefits": EmployeeBenefits,
    "accounting-policy": AccountingPolicy,
    "impairment": Impairment,
    "provision": Provision,
    "cash-flow": CashFlow,
    "consolidation": Consolidation,
    "disclosure": Disclosure,
    "note": Note,
    "financials": FinancialApproval,
}
