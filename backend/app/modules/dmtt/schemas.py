import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.modules.audit_execution.schemas import Body, Strict

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Positive = Annotated[Money, Field(ge=0)]
Rate = Annotated[Decimal, Field(ge=0, le=1, max_digits=18, decimal_places=12)]


class Revenue(Strict):
    year: int
    months: int = Field(default=12, ge=1, le=24)
    eur: Positive
    evidence_id: uuid.UUID


class Group(Body):
    fiscal_start: date
    fiscal_end: date
    upe_name: str = Field(min_length=1, max_length=300)
    upe_jurisdiction: str = Field(min_length=2, max_length=2)
    calculation_currency: str = Field(default="AED", pattern=r"^[A-Z]{3}$")
    accounting_basis: Literal["standalone_ifrs", "upe_package"] = "standalone_ifrs"
    currency_election_evidence_id: uuid.UUID | None = None
    constituent_entity_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    multinational: bool
    preceding_revenues: list[Revenue] = Field(min_length=4, max_length=4)
    rule_version: Literal["UAE-CD142-MD96/v2"]
    technical_evidence_id: uuid.UUID
    special_cases: list[str] = Field(default_factory=list, max_length=30)
    synthetic: bool = False

    @model_validator(mode="after")
    def periods(self):
        if self.fiscal_end < self.fiscal_start or self.fiscal_start < date(2025, 1, 1):
            raise ValueError("DMTT fiscal period must begin on or after 2025-01-01")
        if {x.year for x in self.preceding_revenues} != set(
            range(self.fiscal_start.year - 4, self.fiscal_start.year)
        ):
            raise ValueError("Four immediately preceding distinct years required")
        return self


class ScopeInput(Strict):
    fiscal_start: date
    multinational: bool | None = None
    preceding_revenues: list[Revenue] = Field(default_factory=list, max_length=4)


class Adjustment(Strict):
    category: Literal[
        "net_tax",
        "excluded_dividend",
        "excluded_equity",
        "revaluation",
        "disallowed_expense",
        "prior_error",
        "pension",
        "fx_asymmetry",
        "intragroup",
        "other",
    ]
    amount: Money
    article: str = Field(pattern=r"^3\.[1-5](\.[0-9]+)?$")
    evidence_id: uuid.UUID
    rationale: str = Field(min_length=20, max_length=4000)


class Deferred(Strict):
    amount: Money
    recorded_rate: Rate
    treatment: Literal["ordinary", "excluded", "globe_loss_recast", "transition"]
    evidence_id: uuid.UUID
    loss_attributable: bool = False
    transition_exclusions_checked: bool = False
    origin_year: int | None = None
    remaining_dtl: Positive = Decimal(0)
    recapture_exception: bool = False
    exception_evidence_id: uuid.UUID | None = None


class Entity(Body):
    group_id: uuid.UUID
    entity_id: uuid.UUID
    source_engagement_id: uuid.UUID
    financial_run_id: uuid.UUID
    jurisdiction: str = Field(min_length=2, max_length=2)
    classification: Literal[
        "ordinary", "excluded", "investment", "pe", "jv", "minority_subgroup", "stateless"
    ]
    classification_evidence_id: uuid.UUID
    fx_to_calculation: Annotated[Decimal, Field(gt=0, max_digits=24, decimal_places=12)]
    fx_evidence_id: uuid.UUID
    adjustments: list[Adjustment] = Field(default_factory=list, max_length=100)
    current_tax: Money
    covered_tax_adjustments: Money = Decimal(0)
    covered_tax_evidence_id: uuid.UUID
    deferred: list[Deferred] = Field(default_factory=list, max_length=100)
    eligible_payroll: Positive = Decimal(0)
    eligible_tangible_assets: Positive = Decimal(0)
    substance_evidence_id: uuid.UUID
    additional_topup: Positive = Decimal(0)
    additional_topup_evidence_id: uuid.UUID | None = None


class Election(Body):
    group_id: uuid.UUID
    type: Literal["transitional_cbcr", "de_minimis", "globe_loss", "other"]
    evidence_id: uuid.UUID
    qualified_sources: bool
    all_conditions_reviewed: bool
    once_out_history_clear: bool
    cbcr_revenue_eur: Positive = Decimal(0)
    cbcr_profit_eur: Money = Decimal(0)
    simplified_taxes_eur: Money = Decimal(0)
    cbcr_sbie_eur: Positive = Decimal(0)
    three_year_revenues_eur: list[Positive] = Field(default_factory=list, max_length=3)
    three_year_incomes_eur: list[Money] = Field(default_factory=list, max_length=3)


class Memo(Body):
    group_id: uuid.UUID
    calculation_id: uuid.UUID | None = None
    technical_evidence_id: uuid.UUID
    conclusion: str = Field(min_length=20, max_length=12000)


BODIES: dict[str, type[Body]] = {
    "group": Group,
    "entity": Entity,
    "election": Election,
    "memo": Memo,
}
