"""Declared registration-period turnover bridge; no tax classification is inferred."""

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.jurisdictions.profiles import Strict

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Identifier = Annotated[str, Field(min_length=1, max_length=120)]
CONTRACT = "registration-period-turnover/1"


class TurnoverScope(Strict):
    id: Identifier
    registration: str = Field(min_length=1, max_length=15)
    period_start: date
    period_end: date
    currency: str = Field(pattern="^[A-Z]{3}$")
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def assessed_period(self):
        if self.period_start > self.period_end or len(self.assessment.strip()) < 10:
            raise ValueError("Ordered period and explicit turnover assessment required")
        return self


class TurnoverAmount(TurnoverScope):
    reference: Identifier
    amount: Money


class TurnoverAdjustment(TurnoverAmount):
    reason: Literal[
        "timing",
        "scope",
        "valuation",
        "foreign-exchange",
        "non-revenue-supply",
        "other",
        "assessed-nil",
    ]

    @model_validator(mode="after")
    def explicit_nil(self):
        if self.reason == "assessed-nil" and self.amount != 0:
            raise ValueError("An assessed nil adjustment must be zero")
        return self


ROW_TYPES: dict[str, type[BaseModel]] = {
    "turnover-scope": TurnoverScope,
    "turnover-amounts": TurnoverAmount,
    "turnover-adjustments": TurnoverAdjustment,
}
ROLES = {
    "scope": "turnover-scope",
    "books": "turnover-amounts",
    "return": "turnover-amounts",
    "adjustments": "turnover-adjustments",
}


def key(row):
    return row["registration"], row["period_start"], row["period_end"], row["currency"]


def compare(data, tables, country):
    currency = "AED" if country == "AE" else "INR"
    pattern = r"[0-9]{15}" if country == "AE" else r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]"
    if data.currency != currency:
        raise ValueError(
            "Turnover bridge requires the country's return currency without inferred FX conversion"
        )
    for population in tables.values():
        for row in population:
            if row["currency"] != currency or not re.fullmatch(pattern, row["registration"]):
                raise ValueError(
                    "Turnover registration syntax and return currency must match the engagement country"
                )
            if not row["period_start"] <= row["period_end"] <= data.as_of.isoformat():
                raise ValueError(
                    "Turnover periods must be ordered and closed by the reconciliation date"
                )
    scopes: dict[tuple[str, str, str, str], dict] = {}
    for row in tables["scope"]:
        k = key(row)
        if k in scopes:
            raise ValueError("Duplicate expected registration-period scope")
        scopes[k] = row
    previous = None
    for k in sorted(scopes):
        if previous is not None and k[0] == previous[0] and k[1] <= previous[2]:
            raise ValueError(
                "Overlapping expected registration periods could double-count turnover"
            )
        previous = k
    if not scopes:
        raise ValueError(
            "Explicit expected registration-period scope required; empty scope is not a nil return"
        )
    groups: dict[str, defaultdict[tuple[str, str, str, str], list[dict]]] = {
        role: defaultdict(list) for role in ("books", "return", "adjustments")
    }
    for role, partitions in groups.items():
        references = set()
        for row in tables[role]:
            k = key(row)
            ref = (k, row["reference"])
            if ref in references:
                raise ValueError(
                    "Duplicate turnover reference within a source role and registration-period"
                )
            references.add(ref)
            partitions[k].append(row)
    rows: list[dict] = []
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for index, k in enumerate(
        sorted(set(scopes) | {k for partitions in groups.values() for k in partitions}), 1
    ):
        populations = {role: partitions.get(k, []) for role, partitions in groups.items()}
        amounts = {
            role: sum((Decimal(row["amount"]) for row in population), Decimal(0))
            if population
            else None
            for role, population in populations.items()
        }
        if (
            any(row["reason"] == "assessed-nil" for row in populations["adjustments"])
            and len(populations["adjustments"]) != 1
        ):
            raise ValueError("Assessed nil adjustments cannot coexist with other adjustment rows")
        expected = (
            amounts["books"] + amounts["adjustments"]
            if amounts["books"] is not None and amounts["adjustments"] is not None
            else None
        )
        delta = (
            expected - amounts["return"]
            if expected is not None and amounts["return"] is not None
            else None
        )
        missing = [role for role, population in populations.items() if not population]
        state = (
            "OUTSIDE_DECLARED_SCOPE"
            if k not in scopes
            else "MISSING_POPULATION"
            if missing
            else "MATCHED"
            if delta is not None and abs(delta) <= data.tolerance
            else "VARIANCE"
        )
        rows.append(
            {
                "id": f"turnover-{index}",
                "registration": k[0],
                "period_start": k[1],
                "period_end": k[2],
                "currency": k[3],
                "book_revenue": str(amounts["books"]) if amounts["books"] is not None else None,
                "signed_adjustments": str(amounts["adjustments"])
                if amounts["adjustments"] is not None
                else None,
                "expected_return_turnover": str(expected) if expected is not None else None,
                "reported_turnover": str(amounts["return"])
                if amounts["return"] is not None
                else None,
                "difference": str(delta) if delta is not None else None,
                "missing_roles": missing,
                "scope_source_id": scopes[k]["id"] if k in scopes else None,
                "scope_assessment": scopes[k]["assessment"] if k in scopes else None,
                "source_row_ids": {
                    role: [row["id"] for row in population]
                    for role, population in populations.items()
                },
                "state": state,
            }
        )
        if delta is not None and k in scopes:
            totals["positive_difference" if delta >= 0 else "negative_difference"] += delta
    return {
        "rows": rows,
        "turnover_contract": CONTRACT,
        "turnover_quantification": {
            "complete_for_declared_scope": all(
                row["difference"] is not None and row["state"] != "OUTSIDE_DECLARED_SCOPE"
                for row in rows
            ),
            "unquantified_partition_ids": [row["id"] for row in rows if row["difference"] is None],
            "outside_scope_partition_ids": [
                row["id"] for row in rows if row["state"] == "OUTSIDE_DECLARED_SCOPE"
            ],
        },
        "turnover_basis": "BOOK_REVENUE_PLUS_SIGNED_ADJUSTMENTS_EQUALS_RETURN_TURNOVER",
        "turnover_adjustment_rows": [
            {"source_role": "adjustments", **row} for row in tables["adjustments"]
        ],
        "turnover_difference_totals": {
            currency: {name: str(value) for name, value in totals.items()}
        },
        "exception_count": sum(row["state"] != "MATCHED" for row in rows),
        "blocked": any(
            row["state"] in {"OUTSIDE_DECLARED_SCOPE", "MISSING_POPULATION"} for row in rows
        ),
        "limitations": [
            "Declared registration-period scope only; no complete taxpayer registration or filing population is inferred",
            "Each book and return amount is independently assessed net-of-tax turnover in the return currency; classifications, FX conversion and tax liability are not inferred",
            "Signed adjustment reasons are retained assertions requiring independent review; agreement is not proof of legal correctness",
            "Positive and negative partition differences remain separate; no cross-registration or cross-period netting establishes agreement",
            "Explicit zero rows are required for assessed nil populations; missing sources are never zero",
        ],
    }
