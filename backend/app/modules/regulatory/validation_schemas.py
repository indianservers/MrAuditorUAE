"""Bounded declarative test inputs and independently supplied expected outcomes."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.modules.country_workflows.audit_schemas import BenefitEmployee
from app.modules.country_workflows.payroll_schemas import PayrollBasis
from app.modules.country_workflows.pension_schemas import PensionBasis
from app.modules.jurisdictions.profiles import Strict

Amount = Annotated[Decimal, Field(max_digits=80, decimal_places=40, allow_inf_nan=False)]
InputMoney = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]
ResolvedMoney = Annotated[Decimal, Field(max_digits=28, decimal_places=2, allow_inf_nan=False)]
Fact = Annotated[str, Field(max_length=4000)] | bool | int | None


class RuleFixture(Strict):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["checklist", "flat_rate", "benefit_profile", "payroll_profile", "pension_profile"]
    expected_reference: str = Field(min_length=10, max_length=1000)
    period_start: date | None = None
    period_end: date | None = None
    transaction_date: date | None = None
    facts: dict[str, Fact] = Field(default_factory=dict, max_length=100)
    employee: BenefitEmployee | None = None
    basis: PayrollBasis | None = None
    pension_basis: PensionBasis | None = None
    government_amount: ResolvedMoney | None = Field(default=None, ge=0)
    as_of: date | None = None
    reported_amount: InputMoney | None = Field(default=None, ge=0)
    pension_amount: ResolvedMoney | None = Field(default=None, ge=0)
    expected_applicability: (
        Literal["APPLICABLE", "NOT_APPLICABLE", "PENDING", "OUTSIDE_EFFECTIVE_PERIOD"] | None
    ) = None
    expected_state: str | None = Field(default=None, min_length=1, max_length=100)
    expected_amount: Amount | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def coherent(self):
        if len(self.expected_reference.strip()) < 10:
            raise ValueError("Document the independent expected-outcome reference")
        if self.kind in {"checklist", "flat_rate"}:
            if (
                self.period_start is None
                or self.period_end is None
                or self.expected_applicability is None
            ):
                raise ValueError(
                    "Generic fixtures require reporting dates and expected applicability"
                )
            if self.period_end < self.period_start:
                raise ValueError("Fixture reporting dates must be ordered")
            if any(
                value is not None
                for value in (
                    self.pension_basis,
                    self.government_amount,
                    self.employee,
                    self.basis,
                    self.as_of,
                    self.reported_amount,
                    self.pension_amount,
                    self.expected_state,
                )
            ):
                raise ValueError("Employee calculation inputs do not apply to generic fixtures")
            if self.kind == "checklist" and self.expected_amount is not None:
                raise ValueError("Checklist fixtures cannot assert a calculated amount")
            if (self.kind == "flat_rate" and self.expected_applicability == "APPLICABLE") != (
                self.expected_amount is not None
            ):
                raise ValueError(
                    "Only applicable flat-rate fixtures require an exact unrounded expected amount"
                )
        else:
            if (
                self.as_of is None
                or self.expected_state is None
                or self.period_start is not None
                or self.period_end is not None
                or self.transaction_date is not None
                or self.facts
                or self.expected_applicability is not None
            ):
                raise ValueError(
                    "Employee fixtures require an audit date and expected row state, without generic facts"
                )
            if self.kind == "benefit_profile":
                if self.employee is None or any(
                    value is not None
                    for value in (
                        self.basis,
                        self.pension_basis,
                        self.government_amount,
                        self.reported_amount,
                        self.pension_amount,
                    )
                ):
                    raise ValueError("Benefit fixtures require one assessed employee only")
            elif self.kind == "pension_profile":
                if (
                    self.pension_basis is None
                    or self.reported_amount is None
                    or any(
                        value is not None
                        for value in (self.employee, self.basis, self.pension_amount)
                    )
                ):
                    raise ValueError(
                        "Pension fixtures require an assessed pension basis and reported amount only"
                    )
            elif self.pension_basis is not None or self.government_amount is not None:
                raise ValueError(
                    "Government support and pension bases apply only to pension fixtures"
                )
            elif self.basis is None or self.reported_amount is None or self.employee is not None:
                raise ValueError(
                    "Payroll fixtures require an assessed wage basis and reported amount"
                )
        return self


class ValidationInput(Strict):
    cases: list[RuleFixture] = Field(min_length=1, max_length=20)
