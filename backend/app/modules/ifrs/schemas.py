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
    reversal_of: uuid.UUID | None = None

    @model_validator(mode="after")
    def balanced(self):
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


class Lease(Body):
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


class ECL(Body):
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


class Instrument(Body):
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


class Revenue(Body):
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


class DeferredTax(Body):
    differences: list[TaxDifference] = Field(min_length=1, max_length=10000)
    current_tax: Nonnegative = Decimal(0)
    current_tax_source: str = Field(min_length=1, max_length=4000)


class Asset(Strict):
    reference: str = Field(min_length=1, max_length=100)
    component_of: str = Field(default="", max_length=100)
    cost: Nonnegative
    residual: Nonnegative
    capitalisation_date: date
    useful_life_years: Positive
    method: Literal["straight_line", "diminishing_balance"]
    diminishing_rate: Rate = Decimal(0)
    opening_accumulated: Nonnegative = Decimal(0)
    impairment: Nonnegative = Decimal(0)
    disposal_date: date | None = None
    proceeds: Nonnegative = Decimal(0)
    revaluation_increment: Money = Decimal(0)
    revaluation_assessment: str = Field(default="", max_length=4000)


class FixedAssets(Body):
    period_start: date
    period_end: date
    assets: list[Asset] = Field(min_length=1, max_length=20000)


class Impairment(Body):
    cgu: str = Field(min_length=1, max_length=200)
    carrying_amount: Nonnegative
    cash_flows: list[Money] = Field(min_length=1, max_length=100)
    discount_rate: Rate
    fair_value_less_disposal_costs: Nonnegative
    goodwill_included: Nonnegative = Decimal(0)
    forecast_source: str = Field(min_length=1, max_length=4000)
    reversal_requested: Nonnegative = Decimal(0)
    reversal_cap_excluding_goodwill: Nonnegative = Decimal(0)


class Provision(Body):
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


class Elimination(Strict):
    reference: str = Field(min_length=1, max_length=100)
    debit_line: str
    credit_line: str
    amount: Positive
    reason: str = Field(min_length=1, max_length=4000)
    source_record_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)


class Consolidation(Body):
    presentation_currency: str = Field(pattern=r"^[A-Z]{3}$")
    members: list[GroupMember] = Field(min_length=2, max_length=100)
    eliminations: list[Elimination] = Field(default_factory=list, max_length=1000)
    unrealised_profit: Nonnegative = Decimal(0)
    unrealised_profit_inventory_line: str = Field(default="", max_length=100)
    unrealised_profit_expense_line: str = Field(default="", max_length=100)
    unrealised_profit_source: str = Field(default="", max_length=4000)


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
    "impairment": Impairment,
    "provision": Provision,
    "cash-flow": CashFlow,
    "consolidation": Consolidation,
    "disclosure": Disclosure,
    "note": Note,
    "financials": FinancialApproval,
}
