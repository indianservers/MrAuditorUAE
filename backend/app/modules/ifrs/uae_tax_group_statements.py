"""Internal four-statement workpaper engine, pending retained-evidence/API integration.

This is deliberately separate from IFRS 10 consolidation. It never issues financial
statements or establishes legal membership, source authenticity or audit completion.
Position uses debit-positive balances; performance and equity movements use
income/increase-positive values. No FX, acquisition or elimination entry is inferred.
"""

import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, localcontext
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.modules.grc.deadlines import CalendarDate
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "uae-tax-group-four-statement-workpaper/1"
FTA7_SHA256 = "f3eebe866669ad14f6f2e0789631f3feaf492295ab51243126711d9296be2119"
CTP007_SHA256 = "5b8d235dfd5af78789cc8cb96d5f55dbb57fb1df5e2ba5224fc82d6696147dbf"
Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]
Nonnegative = Annotated[Money, Field(ge=0)]
Statement = Literal["position", "profit_loss", "oci", "changes_equity"]
KINDS = {
    "position": {"asset", "liability", "equity"},
    "profit_loss": {"income", "expense"},
    "oci": {"oci"},
    "changes_equity": {
        "opening_equity",
        "profit",
        "oci",
        "contribution",
        "distribution",
        "other",
        "closing_equity",
    },
}
PROTECTED = {"member_investment", "member_equity", "direct_member_investment_impairment"}


class ExactInput(Strict):
    @model_validator(mode="before")
    @classmethod
    def no_binary_amounts(cls, value):
        if isinstance(value, dict):
            for key in (
                "amount",
                "delta",
                "deductible_loss",
                "previously_reversed",
                "period_income",
                "cost_basis",
                "cumulative_impairment",
            ):
                if isinstance(value.get(key), (float, bool)):
                    raise ValueError("Use exact decimal strings for workpaper amounts")
                amount = value.get(key)
                if isinstance(amount, str) and not re.fullmatch(
                    r"-?[0-9]{1,28}(?:\.[0-9]{1,8})?", amount
                ):
                    raise ValueError("Use bounded plain decimal notation for workpaper amounts")
                if isinstance(amount, Decimal):
                    exponent = amount.as_tuple().exponent
                    if not isinstance(exponent, int) or not -8 <= exponent <= 28:
                        raise ValueError("Use bounded finite decimal amounts")
        return value


class StatementLine(ExactInput):
    reference: str = Field(min_length=1, max_length=100)
    statement: Statement
    code: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=300)
    kind: str = Field(min_length=1, max_length=40)
    amount: Money
    treatment: Literal[
        "ordinary",
        "nonmember_investment",
        "member_investment",
        "member_equity",
        "direct_member_investment_impairment",
        "uae_ct_current",
        "uae_ct_deferred",
        "foreign_or_emirate_tax",
        "consolidation_only_acquisition",
        "standalone_business_acquisition",
    ]
    counterparty_member: str | None = Field(default=None, min_length=1, max_length=100)
    transaction_reference: str | None = Field(default=None, min_length=1, max_length=100)
    source_reference: str = Field(min_length=10, max_length=2000)
    measurement_basis: Literal["cost_less_impairment", "other", "unassessed"] = "unassessed"
    cost_basis: Nonnegative | None = None
    cumulative_impairment: Nonnegative | None = None

    @model_validator(mode="after")
    def classification(self):
        if (
            any(not v.strip() for v in (self.reference, self.code, self.label))
            or len(self.source_reference.strip()) < 10
        ):
            raise ValueError("Meaningful line identities, captions and source references required")
        if self.kind not in KINDS[self.statement]:
            raise ValueError("Statement and line classification disagree")
        if bool(self.counterparty_member) != bool(self.transaction_reference):
            raise ValueError(
                "An intramember line needs both counterparty and transaction reference"
            )
        if self.treatment in PROTECTED and not self.counterparty_member:
            raise ValueError(
                "Member investments, equity and direct impairments need the member identity"
            )
        if self.treatment == "member_investment" and (self.statement, self.kind) != (
            "position",
            "asset",
        ):
            raise ValueError("Member investment must be an asset caption")
        if self.treatment == "member_equity" and (self.statement, self.kind) != (
            "position",
            "equity",
        ):
            raise ValueError("Member equity must be an equity caption")
        if self.treatment == "nonmember_investment":
            if (self.statement, self.kind) != ("position", "asset") or self.counterparty_member:
                raise ValueError(
                    "Nonmember investments require a separate asset caption outside member eliminations"
                )
            if (
                self.cost_basis is not None
                and self.cumulative_impairment is not None
                and self.cumulative_impairment > self.cost_basis
            ):
                raise ValueError("Investment impairment cannot exceed its declared cost")
        return self


class MemberStatements(Strict):
    member: str = Field(min_length=1, max_length=100)
    legal_entity_id: UUID
    role: Literal["parent", "subsidiary"]
    period_start: CalendarDate
    period_end: CalendarDate
    membership_from: CalendarDate
    membership_through: CalendarDate
    currency: Literal["AED"]
    basis: Literal["standalone_unconsolidated"]
    accounting_standard: Literal["IFRS", "IFRS_FOR_SMES", "unassessed"]
    uniform_policy: Literal["assessed_aligned", "adjusted_with_evidence", "unassessed"]
    policy_assessment: str = Field(min_length=10, max_length=4000)
    source_evidence_version_id: UUID
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    lines: list[StatementLine] = Field(min_length=4, max_length=20000)

    @model_validator(mode="after")
    def coverage(self):
        if (
            not self.membership_from
            <= self.period_start
            <= self.period_end
            <= self.membership_through
        ):
            raise ValueError(
                "A whole-period approved member package is required; joining/leaving needs an aligned package"
            )
        if len({line.reference for line in self.lines}) != len(self.lines):
            raise ValueError("Member line references must be unique across all four statements")
        if {line.statement for line in self.lines} != set(KINDS):
            raise ValueError("Supply all four statements, including explicit nil OCI")
        required = {
            "position": {"asset", "liability", "equity"},
            "profit_loss": {"income", "expense"},
            "changes_equity": {"opening_equity", "closing_equity", "profit", "oci"},
        }
        if any(
            not kinds <= {line.kind for line in self.lines if line.statement == statement}
            for statement, kinds in required.items()
        ):
            raise ValueError(
                "Retain explicit opening/closing equity, profit, OCI and nil statement categories"
            )
        if len(self.policy_assessment.strip()) < 10:
            raise ValueError("Retain a meaningful policy assessment")
        return self


class FrameworkAdjustment(ExactInput):
    reference: str = Field(min_length=1, max_length=100)
    member: str = Field(min_length=1, max_length=100)
    line_reference: str = Field(min_length=1, max_length=100)
    delta: Money
    category: Literal[
        "uniform_policy",
        "uae_ct_exclusion",
        "consolidation_acquisition_removal",
        "intramember_elimination",
        "consequential_asset_adjustment",
    ]
    counterparty_member: str | None = Field(default=None, min_length=1, max_length=100)
    transaction_reference: str | None = Field(default=None, min_length=1, max_length=100)
    source_reference: str = Field(min_length=10, max_length=2000)
    rationale: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def documented_movement(self):
        if (
            self.delta == 0
            or any(not v.strip() for v in (self.reference, self.member, self.line_reference))
            or any(len(v.strip()) < 10 for v in (self.rationale, self.source_reference))
        ):
            raise ValueError("Retain a nonzero explicit adjustment and meaningful source/rationale")
        return self


class PreJoinLoss(ExactInput):
    transaction_reference: str = Field(min_length=1, max_length=100)
    members: list[str] = Field(min_length=2, max_length=2)
    deductible_loss: Nonnegative
    previously_reversed: Nonnegative
    period_income: Nonnegative
    source_reference: str = Field(min_length=10, max_length=2000)
    assessment: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def bounded_reversals(self):
        if self.previously_reversed > self.deductible_loss or len(set(self.members)) != 2:
            raise ValueError("Pre-join loss needs distinct members and bounded prior reversals")
        return self


class PeriodStatements(Strict):
    period_start: CalendarDate
    period_end: CalendarDate
    population: Literal["assessed_complete", "unassessed"]
    intramember_population: Literal["assessed_complete", "unassessed"]
    population_assessment: str = Field(min_length=10, max_length=4000)
    members: list[MemberStatements] = Field(min_length=2, max_length=100)
    adjustments: list[FrameworkAdjustment] = Field(max_length=20000)
    pre_join_losses: list[PreJoinLoss] = Field(max_length=10000)
    basis_of_preparation: str = Field(min_length=10, max_length=20000)
    accounting_policies: str = Field(min_length=10, max_length=20000)
    estimates_and_judgments: str = Field(min_length=10, max_length=20000)
    membership_disclosures: str = Field(min_length=10, max_length=20000)

    @model_validator(mode="after")
    def complete_period(self):
        if not date(2023, 6, 1) <= self.period_start <= self.period_end:
            raise ValueError("Ordered corporate-tax reporting period required")
        if len({m.member for m in self.members}) != len(self.members) or len(
            {m.legal_entity_id for m in self.members}
        ) != len(self.members):
            raise ValueError("Member references and legal entities must be unique")
        if sum(m.role == "parent" for m in self.members) != 1:
            raise ValueError("One parent package is required")
        if any(
            (m.period_start, m.period_end) != (self.period_start, self.period_end)
            for m in self.members
        ):
            raise ValueError("All standalone packages must have the same financial year")
        if sum(len(m.lines) for m in self.members) > 20000:
            raise ValueError("The complete period is bounded to 20000 statement lines")
        if len({a.reference for a in self.adjustments}) != len(self.adjustments):
            raise ValueError("Adjustment references must be unique")
        if len({p.transaction_reference for p in self.pre_join_losses}) != len(
            self.pre_join_losses
        ):
            raise ValueError("Pre-join transaction exceptions must be unique")
        for field in (
            "population_assessment",
            "basis_of_preparation",
            "accounting_policies",
            "estimates_and_judgments",
            "membership_disclosures",
        ):
            if len(getattr(self, field).strip()) < 10:
                raise ValueError("Retain meaningful assessments and all four note sections")
        return self


class TaxGroupStatements(Strict):
    contract: Literal["uae-tax-group-four-statement-workpaper/1"]
    group_reference: str = Field(min_length=1, max_length=120)
    first_group_period_start: CalendarDate
    current: PeriodStatements
    comparative: PeriodStatements | None
    comparative_basis: Literal["first_group_period", "assessed_current_framework", "unassessed"]

    @model_validator(mode="after")
    def comparatives(self):
        if (
            not date(2025, 1, 1) <= self.current.period_start
            or self.first_group_period_start < date(2023, 6, 1)
            or self.first_group_period_start > self.current.period_start
        ):
            raise ValueError(
                "Current framework starts from 2025 and group formation cannot follow the reporting start"
            )
        first = self.first_group_period_start == self.current.period_start
        if first:
            if self.comparative is not None or self.comparative_basis != "first_group_period":
                raise ValueError(
                    "First group tax period must be explicit; do not invent prior group figures"
                )
        elif self.comparative is None or self.comparative_basis == "first_group_period":
            raise ValueError(
                "An existing group requires preceding-period comparatives, even in its first framework year"
            )
        if self.comparative and (
            self.comparative.period_end + timedelta(days=1) != self.current.period_start
            or self.comparative.period_start < self.first_group_period_start
        ):
            raise ValueError("Retain the immediately preceding group tax period")
        return self


def _differences(totals):
    return {
        "position_balance": sum(
            (totals[("position", k)] for k in ("asset", "liability", "equity")), Decimal(0)
        ),
        "equity_rollforward": sum(
            (
                totals[("changes_equity", k)]
                for k in (
                    "opening_equity",
                    "profit",
                    "oci",
                    "contribution",
                    "distribution",
                    "other",
                )
            ),
            Decimal(0),
        )
        - totals[("changes_equity", "closing_equity")],
        "equity_position_agreement": totals[("changes_equity", "closing_equity")]
        + totals[("position", "equity")],
        "profit_transfer_agreement": totals[("changes_equity", "profit")]
        - totals[("profit_loss", "income")]
        - totals[("profit_loss", "expense")],
        "oci_transfer_agreement": totals[("changes_equity", "oci")] - totals[("oci", "oci")],
    }


def _period(data: PeriodStatements):
    issues = []
    members = {m.member: m for m in data.members}
    originals = {(m.member, line.reference): line for m in data.members for line in m.lines}
    values = {key: line.amount for key, line in originals.items()}
    exceptions = {p.transaction_reference: p for p in data.pre_join_losses}
    source_checks = {}
    for member in data.members:
        source_totals: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
        for line in member.lines:
            source_totals[(line.statement, line.kind)] += line.amount
        source_checks[member.member] = _differences(source_totals)
        for code, difference in source_checks[member.member].items():
            if difference:
                issues.append(
                    {
                        "code": "SOURCE_MEMBER_" + code.upper(),
                        "member": member.member,
                        "difference": difference,
                    }
                )
    transactions = defaultdict(list)
    for key, line in originals.items():
        if line.counterparty_member and (
            line.counterparty_member not in members or line.counterparty_member == key[0]
        ):
            raise ValueError("Intramember references must identify another actual Tax Group member")
        if line.transaction_reference:
            transactions[line.transaction_reference].append((key, line))
    for exception in exceptions.values():
        if not set(exception.members) <= members.keys():
            raise ValueError("Pre-join loss exception references a nonmember")
        related = transactions[exception.transaction_reference]
        if not related or any(
            {key[0], line.counterparty_member} != set(exception.members) for key, line in related
        ):
            raise ValueError(
                "Pre-join loss exception must bind its exact declared member transaction"
            )
    for adjustment in data.adjustments:
        key = (adjustment.member, adjustment.line_reference)
        if key not in originals:
            raise ValueError("Adjustment target is absent from the retained standalone statements")
        line = originals[key]
        intra = adjustment.category in {"intramember_elimination", "consequential_asset_adjustment"}
        if intra:
            if not line.counterparty_member or (
                adjustment.counterparty_member,
                adjustment.transaction_reference,
            ) != (line.counterparty_member, line.transaction_reference):
                raise ValueError(
                    "Eliminations and consequential adjustments require the exact member pair and transaction"
                )
            if line.treatment in PROTECTED:
                raise ValueError(
                    "Do not eliminate member investments/equity or direct investment impairment"
                )
            loss_exception = exceptions.get(line.transaction_reference or "")
            if (
                loss_exception
                and loss_exception.deductible_loss - loss_exception.previously_reversed
                > loss_exception.period_income
            ):
                raise ValueError(
                    "Do not eliminate a transaction while its pre-join deductible loss remains unreversed"
                )
        elif (
            adjustment.counterparty_member is not None
            or adjustment.transaction_reference is not None
        ):
            raise ValueError(
                "Do not disguise member eliminations as an unrelated framework adjustment"
            )
        if adjustment.category == "uae_ct_exclusion" and line.treatment == "foreign_or_emirate_tax":
            raise ValueError("Foreign and emirate taxes are not UAE Corporate Tax exclusions")
        if (
            adjustment.category == "consolidation_acquisition_removal"
            and line.treatment == "standalone_business_acquisition"
        ):
            raise ValueError(
                "Do not remove standalone business-acquisition goodwill under the separate-entity consolidation exclusion"
            )
        values[key] += adjustment.delta
    for member in data.members:
        if member.uniform_policy == "unassessed" or member.accounting_standard == "unassessed":
            issues.append({"code": "MEMBER_ACCOUNTING_POLICY_UNASSESSED", "member": member.member})
        if member.uniform_policy == "adjusted_with_evidence" and not any(
            a.member == member.member and a.category == "uniform_policy" for a in data.adjustments
        ):
            issues.append({"code": "DECLARED_POLICY_ADJUSTMENT_MISSING", "member": member.member})
    standards = {m.accounting_standard for m in data.members}
    if len(standards) != 1:
        issues.append({"code": "MEMBER_ACCOUNTING_STANDARDS_DIFFER"})
    for field in ("population", "intramember_population"):
        if getattr(data, field) != "assessed_complete":
            issues.append({"code": "POPULATION_UNASSESSED", "scope": field})
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for key, original in originals.items():
        value = values[key]
        if original.treatment == "nonmember_investment" and (
            original.measurement_basis != "cost_less_impairment"
            or original.cost_basis is None
            or original.cumulative_impairment is None
            or value != original.cost_basis - original.cumulative_impairment
        ):
            issues.append(
                {
                    "code": "NONMEMBER_INVESTMENT_COST_BRIDGE_UNRESOLVED",
                    "member": key[0],
                    "line": key[1],
                }
            )
        if (
            original.treatment
            in {"uae_ct_current", "uae_ct_deferred", "consolidation_only_acquisition"}
            and value
        ):
            issues.append({"code": "FRAMEWORK_EXCLUSION_REMAINS", "member": key[0], "line": key[1]})
        if (
            original.counterparty_member
            and original.treatment not in PROTECTED
            and value
            and original.transaction_reference not in exceptions
        ):
            issues.append({"code": "INTRAMEMBER_AMOUNT_REMAINS", "member": key[0], "line": key[1]})
        chart_key = (original.statement, original.code)
        row = rows.setdefault(
            chart_key,
            {
                "statement": original.statement,
                "code": original.code,
                "label": original.label,
                "kind": original.kind,
                "amount": Decimal(0),
                "source_lines": [],
            },
        )
        if row["kind"] != original.kind:
            raise ValueError("Group chart code has conflicting classifications")
        row["amount"] += value
        row["source_lines"].append(
            {
                "member": key[0],
                "reference": key[1],
                "original_amount": original.amount,
                "adjustment": value - original.amount,
                "amount": value,
                "source_evidence_version_id": members[key[0]].source_evidence_version_id,
                "source_sha256": members[key[0]].source_sha256,
                "source_reference": original.source_reference,
                "source_label": original.label,
                "treatment": original.treatment,
                "counterparty_member": original.counterparty_member,
                "transaction_reference": original.transaction_reference,
                "measurement_basis": original.measurement_basis,
                "cost_basis": original.cost_basis,
                "cumulative_impairment": original.cumulative_impairment,
            }
        )
    totals: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for row in rows.values():
        totals[(row["statement"], row["kind"])] += row["amount"]
    assets = totals[("position", "asset")]
    liabilities = -totals[("position", "liability")]
    equity = -totals[("position", "equity")]
    profit = totals[("profit_loss", "income")] + totals[("profit_loss", "expense")]
    oci = totals[("oci", "oci")]
    opening = totals[("changes_equity", "opening_equity")]
    closing = totals[("changes_equity", "closing_equity")]
    checks = _differences(totals)
    ct_expense_remains = any(
        line.statement == "profit_loss"
        and line.treatment in {"uae_ct_current", "uae_ct_deferred"}
        and values[key]
        for key, line in originals.items()
    )
    for code, difference in checks.items():
        if difference:
            issues.append({"code": code.upper(), "difference": difference})
    loss_schedule = []
    for exception in exceptions.values():
        remaining = exception.deductible_loss - exception.previously_reversed
        included_ceiling = min(remaining, exception.period_income)
        loss_schedule.append(
            {
                **exception.model_dump(),
                "unreversed_before_period": remaining,
                "period_income_ceiling_for_tax_review": included_ceiling,
                "unreversed_after_declared_income": remaining - included_ceiling,
            }
        )
        issues.append(
            {
                "code": "PRE_JOIN_LOSS_ACCOUNTING_AND_TAX_BRIDGE_REQUIRES_REVIEW",
                "transaction": exception.transaction_reference,
            }
        )
    return {
        "period_start": data.period_start,
        "period_end": data.period_end,
        "members": [member.model_dump(exclude={"lines"}) for member in data.members],
        "statements": {
            name: [row for (statement, _), row in rows.items() if statement == name]
            for name in KINDS
        },
        "totals": {
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "profit_loss_sum": profit,
            "profit_before_uae_corporate_tax": None if ct_expense_remains else profit,
            "oci": oci,
            "opening_equity": opening,
            "closing_equity": closing,
        },
        "reconciliation_differences": checks,
        "source_member_reconciliation_differences": source_checks,
        "adjustments": [a.model_dump() for a in data.adjustments],
        "pre_join_loss_schedule": loss_schedule,
        "notes": {
            field: getattr(data, field)
            for field in (
                "basis_of_preparation",
                "accounting_policies",
                "estimates_and_judgments",
                "membership_disclosures",
            )
        },
        "issues": issues,
        "arithmetic_reconciled": not any(checks.values())
        and not any(any(check.values()) for check in source_checks.values()),
    }


def calculate(data: TaxGroupStatements):
    """Aggregate explicit inputs only. Binding/review/issuance remain outside this engine."""
    from app.modules.ifrs.calculations import serial

    with localcontext() as precision:
        precision.prec = 48
        current = _period(data.current)
        comparative = _period(data.comparative) if data.comparative else None
        opening_difference = (
            current["totals"]["opening_equity"] - comparative["totals"]["closing_equity"]
            if comparative
            else Decimal(0)
        )
    issues = [{"period": "current", **issue} for issue in current["issues"]]
    if comparative:
        issues += [{"period": "comparative", **issue} for issue in comparative["issues"]]
        if opening_difference:
            issues.append(
                {
                    "code": "COMPARATIVE_OPENING_EQUITY_BRIDGE_REQUIRED",
                    "difference": opening_difference,
                }
            )
        if data.comparative_basis == "unassessed":
            issues.append({"code": "COMPARATIVE_FRAMEWORK_BASIS_UNASSESSED"})
    return serial(
        {
            "contract": CONTRACT,
            "group_reference": data.group_reference,
            "currency": "AED",
            "current": current,
            "comparative": comparative,
            "comparative_basis": data.comparative_basis,
            "issues": issues,
            "validation": {
                "ready": False,
                "arithmetic_reconciled": current["arithmetic_reconciled"]
                and (comparative is None or comparative["arithmetic_reconciled"])
                and not opening_difference,
                "framework_inputs_without_detected_issues": not issues,
            },
            "source_binding_established": False,
            "professional_qualification": "NOT_ESTABLISHED",
            "statutory_issuance": False,
            "limitations": [
                "Internal arithmetic engine: no public workflow, retained-byte verification, source freshness or independent approval is established here",
                "Standalone source facts, membership, policies, complete transaction populations and prescribed notes require independent professional evidence",
                "No IFRS10 investment/equity elimination, goodwill, NCI, FX or automatic journal is inferred",
                "Pre-join loss income ceilings are review schedules, not a determination of taxable income",
                "Leaving-member continuity, clawback treatment, full authority-required note wording, audit and submission need their separate verified workflows",
            ],
        }
    )
