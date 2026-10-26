"""Retained mandate budgets versus allocated expenditure, not a utilization certificate."""

import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, localcontext
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, field_validator, model_validator

from app.modules.country_workflows.audit_calculations import result
from app.modules.jurisdictions.profiles import Strict

ID = Annotated[str, Field(min_length=1, max_length=120)]
Value = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]
ControlValue = Annotated[Decimal, Field(max_digits=64, decimal_places=8, allow_inf_nan=False)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


def calendar_day(value):
    if (
        type(value) is date
        or isinstance(value, str)
        and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
    ):
        return value
    raise ValueError(
        "Grant dates require explicit ISO calendar dates, not inferred timestamps or timezones"
    )


Day = Annotated[date, BeforeValidator(calendar_day)]


class Exact(Strict):
    @model_validator(mode="after")
    def exact_text(self):
        for key, value in self.__dict__.items():
            if isinstance(value, str) and (
                value != value.strip()
                or any(
                    ord(c) < 32
                    or ord(c) == 127
                    or 0xD800 <= ord(c) <= 0xDFFF
                    or ord(c) in {0xFFFE, 0xFFFF}
                    for c in value
                )
            ):
                raise ValueError(
                    "Grant identifiers and assessments require exact text without control characters"
                )
        return self


class GrantBudget(Exact):
    id: ID
    fund_id: ID
    category: ID
    donor: ID
    project: ID
    country: str = Field(pattern=r"^[A-Z]{2}$")
    currency: Currency
    valid_from: Day
    valid_to: Day
    category_ceiling: Value = Field(ge=0)
    fund_ceiling: Value = Field(ge=0)
    mandate_reference: ID
    source_evidence_version_id: UUID
    source_sha256: Hash
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def dates(self):
        if self.valid_to < self.valid_from:
            raise ValueError("Grant mandate validity dates must be ordered")
        return self


class GrantExpense(Exact):
    id: ID
    account: ID
    project: ID
    vendor: ID
    reference: ID
    line_reference: ID
    currency: Currency
    date: Day
    kind: Literal["expense", "credit"]
    amount: Value
    original_reference: str = Field(default="", max_length=120)
    evidence_reference: ID

    @model_validator(mode="after")
    def sign(self):
        if self.kind == "expense" and (self.amount < 0 or self.original_reference):
            raise ValueError(
                "Expense amounts are nonnegative without a credit's original reference"
            )
        if self.kind == "credit" and (self.amount >= 0 or not self.original_reference):
            raise ValueError("Credits require a negative amount and original expenditure reference")
        return self


class GrantAllocation(Exact):
    id: ID
    expense_id: ID
    fund_id: ID
    category: ID
    currency: Currency
    amount: Value
    rationale: str = Field(min_length=10, max_length=2000)
    credit_original_reference: str = Field(default="", max_length=120)
    credit_evidence_version_id: UUID | None = None
    credit_source_sha256: Hash | None = None

    @model_validator(mode="after")
    def credit_support(self):
        support = (
            self.credit_original_reference,
            self.credit_evidence_version_id,
            self.credit_source_sha256,
        )
        if self.amount < 0 and not all(support):
            raise ValueError(
                "Negative grant allocations need the original reference and retained recovery-assessment document"
            )
        if self.amount >= 0 and any(support):
            raise ValueError("Credit recovery evidence applies only to negative allocations")
        return self


class GrantControl(Exact):
    id: ID
    kind: Literal["expense-period", "fund-opening"]
    account: str = Field(default="", max_length=120)
    fund_id: str = Field(default="", max_length=120)
    category: str = Field(default="", max_length=120)
    currency: Currency
    period_start: Day
    period_end: Day
    amount: ControlValue
    expected_rows: int | None = Field(default=None, ge=0, le=5000, strict=True)
    positive_amount: ControlValue | None = Field(default=None, ge=0)
    negative_amount: ControlValue | None = Field(default=None, le=0)
    ledger_reference: ID
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("expected_rows", mode="before")
    @classmethod
    def explicit_count(cls, value):
        if isinstance(value, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
            return int(value)
        return value

    @model_validator(mode="after")
    def scope(self):
        if self.period_end < self.period_start:
            raise ValueError("Grant control dates must be ordered")
        if self.kind == "expense-period":
            if (
                not self.account
                or self.fund_id
                or self.category
                or any(
                    value is None
                    for value in (self.expected_rows, self.positive_amount, self.negative_amount)
                )
            ):
                raise ValueError(
                    "Expense controls need account, count and signed gross totals; no fund/category"
                )
            with localcontext() as context:
                context.prec = 80
                assert self.positive_amount is not None and self.negative_amount is not None
                if self.amount != self.positive_amount + self.negative_amount:
                    raise ValueError(
                        "Expense control net must equal its positive plus negative totals"
                    )
        elif (
            self.account
            or not self.fund_id
            or not self.category
            or self.period_start != self.period_end
            or any(
                value is not None
                for value in (self.expected_rows, self.positive_amount, self.negative_amount)
            )
        ):
            raise ValueError(
                "Opening controls require one fund/category/date and no expense-account counts"
            )
        return self


ROW_TYPES: dict[str, type[Strict]] = {
    "grant-budgets": GrantBudget,
    "grant-expenses": GrantExpense,
    "grant-allocations": GrantAllocation,
    "grant-utilisation-controls": GrantControl,
}
ROLES = dict(
    budgets="grant-budgets",
    expenses="grant-expenses",
    allocations="grant-allocations",
    controls="grant-utilisation-controls",
)


def documents(rows, kind):
    if kind == "grant-budgets":
        return [
            dict(
                source_evidence_version_id=row["source_evidence_version_id"],
                source_sha256=row["source_sha256"],
            )
            for row in rows
        ]
    return [
        dict(
            source_evidence_version_id=row["credit_evidence_version_id"],
            source_sha256=row["credit_source_sha256"],
        )
        for row in rows
        if row.get("credit_evidence_version_id")
    ]


def compare(data, tables, country):
    with localcontext() as context:
        context.prec = 80
        return _compare(data, tables, country)


def _compare(data, tables, country):
    if data.period_start is None or data.period_start > data.as_of or data.period_start == date.min:
        raise ValueError(
            "Grant expenditure review requires an explicit ordered period with a prior opening date"
        )
    opening_date = data.period_start - timedelta(days=1)
    key: tuple[str, ...]
    budgets: dict[tuple[str, ...], Any] = {}
    fund_terms: dict[Any, Any] = {}
    for population in tables.values():
        if len(population) > 5000 or len({row["id"] for row in population}) != len(population):
            raise ValueError("Grant sources require at most 5000 distinct row identities each")
    for budget in tables["budgets"]:
        key = (budget["fund_id"], budget["category"], budget["currency"])
        if key in budgets:
            raise ValueError(
                "Ambiguous grant/category/currency mandate; assess amendments separately"
            )
        if budget["country"] != country:
            raise ValueError("Grant mandate country differs from the engagement country")
        fund = (key[0], key[2])
        terms = (budget["donor"], budget["project"], Decimal(budget["fund_ceiling"]))
        if fund in fund_terms and fund_terms[fund] != terms:
            raise ValueError("Fund donor/project/ceiling must agree across its category mandates")
        budgets[key] = budget
        fund_terms[fund] = terms
    if not budgets:
        raise ValueError(
            "A declared grant population is required; absence is not a nil eligibility conclusion"
        )
    expenses = {row["id"]: row for row in tables["expenses"]}
    if len(expenses) != len(tables["expenses"]):
        raise ValueError("Duplicate expense identities")
    voucher_lines = [
        tuple(
            row[field] for field in ("account", "currency", "vendor", "reference", "line_reference")
        )
        for row in expenses.values()
    ]
    if len(set(voucher_lines)) != len(voucher_lines):
        raise ValueError("Duplicate original expense voucher lines")
    controls: dict[Any, Any] = {}
    openings: dict[Any, Any] = {}
    for control in tables["controls"]:
        if control["kind"] == "expense-period":
            key = (control["account"], control["currency"])
            if key in controls or (control["period_start"], control["period_end"]) != (
                data.period_start.isoformat(),
                data.as_of.isoformat(),
            ):
                raise ValueError(
                    "Expense controls must identify unique accounts and the exact review period"
                )
            controls[key] = control
        else:
            key = (control["fund_id"], control["category"], control["currency"])
            if (
                key in openings
                or control["period_start"] != opening_date.isoformat()
                or control["period_end"] != opening_date.isoformat()
            ):
                raise ValueError(
                    "Opening utilisation controls must use the day before the review period"
                )
            openings[key] = control
    if not controls:
        raise ValueError(
            "At least one explicit expense account control is required, including for a nil population"
        )
    expense_groups = defaultdict(list)
    for expense in expenses.values():
        if not data.period_start <= date.fromisoformat(expense["date"]) <= data.as_of:
            raise ValueError(
                "Expense population must be within the explicit review period; no silent filtering"
            )
        expense_groups[(expense["account"], expense["currency"])].append(expense)
    rows: list[dict[str, Any]] = []
    blocked = False
    for key in sorted(controls.keys() | expense_groups.keys()):
        population = expense_groups[key]
        control = controls.get(key)
        positive = sum(
            (Decimal(row["amount"]) for row in population if Decimal(row["amount"]) >= 0),
            Decimal(0),
        )
        negative = sum(
            (Decimal(row["amount"]) for row in population if Decimal(row["amount"]) < 0), Decimal(0)
        )
        agreed = (
            control is not None
            and control["expected_rows"] == len(population)
            and Decimal(control["amount"]) == positive + negative
            and Decimal(control["positive_amount"]) == positive
            and Decimal(control["negative_amount"]) == negative
        )
        blocked |= not agreed
        rows.append(
            dict(
                id=f"expense-control:{len(rows) + 1}",
                kind="expense-control",
                account=key[0],
                currency=key[1],
                observed_rows=len(population),
                expected_rows=control["expected_rows"] if control else None,
                amount=str(positive + negative),
                positive_amount=str(positive),
                negative_amount=str(negative),
                control_amount=control["amount"] if control else None,
                expected_positive_amount=control["positive_amount"] if control else None,
                expected_negative_amount=control["negative_amount"] if control else None,
                control_source_id=control["id"] if control else None,
                state="MATCHED" if agreed else "EXPENSE_POPULATION_CONTROL_GAP",
            )
        )
    allocations = defaultdict(list)
    budget_allocations: defaultdict[Any, list[dict[str, Any]]] = defaultdict(list)
    fund_allocations = defaultdict(list)
    for allocation in tables["allocations"]:
        key = (allocation["fund_id"], allocation["category"], allocation["currency"])
        expense = expenses.get(allocation["expense_id"])
        budget = budgets.get(key)
        reasons = []
        if expense is None:
            reasons.append("UNKNOWN_EXPENSE")
        if budget is None:
            reasons.append("MISSING_CATEGORY_MANDATE")
        if expense:
            if expense["currency"] != allocation["currency"]:
                reasons.append("CURRENCY_MISMATCH")
            if (
                (Decimal(expense["amount"]) < 0) != (Decimal(allocation["amount"]) < 0)
                or Decimal(expense["amount"]) == 0
                and Decimal(allocation["amount"]) != 0
            ):
                reasons.append("ALLOCATION_SIGN_MISMATCH")
            if budget and expense["project"] != budget["project"]:
                reasons.append("PROJECT_MISMATCH")
            if (
                Decimal(allocation["amount"]) < 0
                and allocation["credit_original_reference"] != expense["original_reference"]
            ):
                reasons.append("CREDIT_REFERENCE_MISMATCH")
        hard_gap = bool(reasons)
        if expense and budget and not budget["valid_from"] <= expense["date"] <= budget["valid_to"]:
            reasons.append("OUTSIDE_MANDATE_DATES")
        if Decimal(allocation["amount"]) < 0:
            reasons.append("CREDIT_RECOVERY_REVIEW")
        blocked |= hard_gap
        allocations[allocation["expense_id"]].append(allocation)
        budget_allocations[key].append(allocation)
        fund_allocations[(key[0], key[2])].append(allocation)
        rows.append(
            dict(
                **{key: value for key, value in allocation.items() if key != "id"},
                id="allocation:" + allocation["id"],
                allocation_source_id=allocation["id"],
                kind="allocation",
                expense_reference=expense["reference"] if expense else None,
                expense_date=expense["date"] if expense else None,
                expense_project=expense["project"] if expense else None,
                mandate_source_id=budget["id"] if budget else None,
                mandate_evidence_version_id=budget["source_evidence_version_id"]
                if budget
                else None,
                mandate_source_sha256=budget["source_sha256"] if budget else None,
                mandate_reference=budget["mandate_reference"] if budget else None,
                reasons=reasons,
                state="ALLOCATION_REVIEW" if reasons else "MATCHED",
            )
        )
    for expense in expenses.values():
        total = sum((Decimal(row["amount"]) for row in allocations[expense["id"]]), Decimal(0))
        difference = Decimal(expense["amount"]) - total
        matched = bool(allocations[expense["id"]]) and difference == 0
        blocked |= not matched
        rows.append(
            dict(
                id="expense:" + expense["id"],
                kind="expense-allocation-control",
                expense_id=expense["id"],
                currency=expense["currency"],
                amount=expense["amount"],
                allocated_amount=str(total),
                difference=str(difference),
                state="MATCHED" if matched else "UNALLOCATED_OR_EXCESS_EXPENDITURE",
            )
        )
    fund_openings: defaultdict[Any, Decimal] = defaultdict(lambda: Decimal(0))
    opening_review_funds = set()
    missing_funds = set()
    for key in sorted(budgets.keys() | openings.keys()):
        budget = budgets.get(key)
        opening = openings.get(key)
        reasons = []
        if budget is None:
            reasons.append("OPENING_WITHOUT_MANDATE")
        if opening is None:
            reasons.append("MISSING_OPENING_UTILISATION")
        blocked |= bool(reasons)
        start = Decimal(opening["amount"]) if opening else None
        if start is not None and start < 0:
            reasons.append("NEGATIVE_OPENING_UTILISATION_REVIEW")
            opening_review_funds.add((key[0], key[2]))
        entries = budget_allocations[key]
        gross = sum(
            (Decimal(row["amount"]) for row in entries if Decimal(row["amount"]) >= 0), Decimal(0)
        )
        credits = sum(
            (Decimal(row["amount"]) for row in entries if Decimal(row["amount"]) < 0), Decimal(0)
        )
        closing = start + gross + credits if start is not None else None
        limit = Decimal(budget["category_ceiling"]) if budget else None
        if closing is not None and closing < 0:
            reasons.append("NEGATIVE_UTILISATION_REVIEW")
        if closing is not None and limit is not None and closing > limit:
            reasons.append("CATEGORY_BUDGET_EXCEEDED")
        if (
            start is not None
            and budget
            and start != 0
            and opening_date < date.fromisoformat(budget["valid_from"])
        ):
            reasons.append("OPENING_PRECEDES_MANDATE")
        if credits:
            reasons.append("CREDIT_RECOVERY_REVIEW")
        if start is not None:
            fund_openings[(key[0], key[2])] += start
        else:
            missing_funds.add((key[0], key[2]))
        rows.append(
            dict(
                id=f"budget:{len(rows) + 1}",
                kind="category-budget",
                fund_id=key[0],
                category=key[1],
                currency=key[2],
                opening_amount=str(start) if start is not None else None,
                positive_amount=str(gross),
                negative_amount=str(credits),
                closing_utilisation=str(closing) if closing is not None else None,
                ceiling=str(limit) if limit is not None else None,
                remaining_under_signed_schedule=str(limit - closing)
                if limit is not None and closing is not None
                else None,
                mandate_source_id=budget["id"] if budget else None,
                opening_source_id=opening["id"] if opening else None,
                mandate_evidence_version_id=budget["source_evidence_version_id"]
                if budget
                else None,
                mandate_source_sha256=budget["source_sha256"] if budget else None,
                mandate_reference=budget["mandate_reference"] if budget else None,
                mandate_valid_from=budget["valid_from"] if budget else None,
                mandate_valid_to=budget["valid_to"] if budget else None,
                reasons=reasons,
                state="BUDGET_REVIEW" if reasons else "MATCHED",
            )
        )
    for fund, terms in sorted(fund_terms.items()):
        entries = fund_allocations[fund]
        gross = sum(
            (Decimal(row["amount"]) for row in entries if Decimal(row["amount"]) >= 0), Decimal(0)
        )
        credits = sum(
            (Decimal(row["amount"]) for row in entries if Decimal(row["amount"]) < 0), Decimal(0)
        )
        closing = None if fund in missing_funds else fund_openings[fund] + gross + credits
        reasons = []
        if fund in opening_review_funds:
            reasons.append("NEGATIVE_OPENING_UTILISATION_REVIEW")
        if closing is None:
            reasons.append("MISSING_OPENING_UTILISATION")
        elif closing > Decimal(terms[2]):
            reasons.append("FUND_BUDGET_EXCEEDED")
        elif closing < 0:
            reasons.append("NEGATIVE_UTILISATION_REVIEW")
        if credits:
            reasons.append("CREDIT_RECOVERY_REVIEW")
        rows.append(
            dict(
                id=f"fund:{len(rows) + 1}",
                kind="fund-budget",
                fund_id=fund[0],
                currency=fund[1],
                donor=terms[0],
                project=terms[1],
                opening_amount=str(fund_openings[fund]) if closing is not None else None,
                positive_amount=str(gross),
                negative_amount=str(credits),
                closing_utilisation=str(closing) if closing is not None else None,
                ceiling=str(terms[2]),
                remaining_under_signed_schedule=str(Decimal(terms[2]) - closing)
                if closing is not None
                else None,
                reasons=reasons,
                state="BUDGET_REVIEW" if reasons else "MATCHED",
            )
        )
    return {
        **result(
            rows,
            blocked,
            [
                "Book expenditure allocation to declared grant/category budgets only; recognition, capitalisation, cash availability, bank settlement, legal eligibility, donor approval and utilization certificates require separate procedures",
                "Credits retain signed cost observations and always require recovery review; their evidence does not machine-verify the original charge or legal budget restoration",
                "Opening utilisation and account/gross/count controls are independently reviewed declarations; agreement does not establish ledger or mandate completeness",
                "Currencies are never netted or implicitly converted; legal/CSR/FCRA/charity permissions remain separate country-specific assessments",
                "Allocation capacity is checked within this declared population; workpapers are analyses, not an entity-wide grant posting or disbursement ledger",
            ],
        ),
        "grant_utilisation_contract": "mandate-expenditure-allocation/1",
        "grant_document_binding": "NOT_VERIFIED_BY_PURE_CALCULATOR",
        "population_basis": "DECLARED_EXPENDITURE_AND_OPENING_SCHEDULES",
        "currency_scope": sorted(
            {row["currency"] for population in tables.values() for row in population}
        ),
        "review_window": {"from": data.period_start.isoformat(), "through": data.as_of.isoformat()},
        "cash_availability_established": False,
        "legal_eligibility_established": False,
        "certificate_issued": False,
    }
