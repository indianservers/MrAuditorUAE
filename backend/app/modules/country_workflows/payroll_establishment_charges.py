"""Assessed establishment charges, separate from employee PF/EPS contributions.

No statutory rates, exemptions, wage ceilings or minima are installed here.
"""

import calendar
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.modules.country_workflows.payroll_calculations import rounding
from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory.payroll_profiles import Identifier, Money

CONTRACT = "india-establishment-charges/1"
Component = Literal["PF:ADMINISTRATION", "PF:INSPECTION", "PF:EDLI", "PF:EDLI_INSPECTION"]


class ChargeMember(Strict):
    id: Identifier
    registration: Identifier
    subject: Identifier
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    component: Component
    currency: Literal["INR"] = "INR"
    amount: Money = Field(ge=0)
    contributing: bool
    evidence_reference: Identifier

    @model_validator(mode="after")
    def contribution_population(self):
        if not self.contributing and self.amount != 0:
            raise ValueError(
                "A non-contributing member must have an explicitly zero assessed charge wage"
            )
        return self


class ChargeControl(Strict):
    id: Identifier
    registration: Identifier
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    component: Component
    currency: Literal["INR"] = "INR"
    rule_group: Identifier
    jurisdiction: Identifier
    expected_members: int = Field(strict=True, ge=0, le=5000)
    expected_contributors: int = Field(strict=True, ge=0, le=5000)
    amount: Money = Field(ge=0, description="Independent sum of assessed member wage bases")
    establishment_state: Literal["NON_FUNCTIONAL_NO_CONTRIBUTORS", "OTHER"]
    evidence_reference: Identifier
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("expected_members", "expected_contributors", mode="before")
    @classmethod
    def canonical_count(cls, value):
        if isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]*", value):
            return int(value)
        return value

    @model_validator(mode="after")
    def assessed(self):
        if self.expected_contributors > self.expected_members:
            raise ValueError("Contributors cannot exceed the controlled member population")
        if (
            self.establishment_state == "NON_FUNCTIONAL_NO_CONTRIBUTORS"
            and self.expected_contributors
        ):
            raise ValueError("Non-functional no-contributor treatment requires zero contributors")
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess establishment status and component wage population")
        return self


class ChargeRule(Strict):
    id: Identifier
    component: Component
    rule_group: Identifier
    jurisdiction: Identifier
    rate: Decimal = Field(ge=0, le=1, max_digits=18, decimal_places=12)
    salary_cap: Money | None = Field(default=None, gt=0)
    rounding: Literal["nearest-rupee", "next-rupee", "floor-rupee", "paise"]
    effective_from: date
    effective_to: date
    source_url: HttpUrl
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_evidence_version_id: UUID
    source_version: Identifier
    evidence_reference: Identifier
    applicability_review: str = Field(min_length=10, max_length=2000)
    aggregation: Literal["ROUND_MEMBERS_THEN_SUM", "SUM_BASES_THEN_ROUND"]
    minimum_other: Money = Field(ge=0)
    minimum_non_functional: Money = Field(ge=0)

    @model_validator(mode="after")
    def charge_parameters(self):
        if self.effective_to < self.effective_from or len(self.applicability_review.strip()) < 10:
            raise ValueError("Assess applicability and ordered effective dates")
        if self.aggregation == "SUM_BASES_THEN_ROUND" and self.salary_cap is not None:
            raise ValueError("Aggregate establishment charges cannot cap the combined payroll")
        # Minima are monetary obligations, not a second rounding instruction.
        if any(
            rounding(value, self.rounding) != value
            for value in (self.minimum_other, self.minimum_non_functional)
        ):
            raise ValueError("Charge minima must already conform to the selected rounding unit")
        return self


ROW_TYPES: dict[str, type[BaseModel]] = {
    "payroll-charge-members": ChargeMember,
    "payroll-charge-controls": ChargeControl,
    "payroll-charge-rules": ChargeRule,
}
ROLES = {
    "members": "payroll-charge-members",
    "controls": "payroll-charge-controls",
    "rules": "payroll-charge-rules",
    "reported": "obligations",
}


def scope(row):
    return row["registration"].upper(), row["period"], row["component"]


def calculate(data, tables):
    if data.currency != "INR" or data.tolerance != 0 or data.date_tolerance != 0:
        raise ValueError("Establishment charge review requires INR and exact controls")
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        return _calculate(data, tables)


def _calculate(data, tables):
    members = defaultdict(list)
    identities = set()
    for raw in tables["members"]:
        row = ChargeMember.model_validate(raw).model_dump(mode="json")
        key = (*scope(row), row["subject"].upper())
        if key in identities:
            raise ValueError("Duplicate member within establishment, month and charge component")
        identities.add(key)
        members[scope(row)].append(row)
    controls = {}
    control: dict[str, Any] | None
    for raw in tables["controls"]:
        control = ChargeControl.model_validate(raw).model_dump(mode="json")
        key = scope(control)
        if key in controls:
            raise ValueError("One independent control per establishment, month and component")
        controls[key] = control
    if not controls or members.keys() - controls.keys():
        raise ValueError("Every member population needs an explicit establishment control")
    # Administration and inspection are alternatives, never additive substitutes.
    for key in controls:
        alternative = {
            "PF:ADMINISTRATION": "PF:INSPECTION",
            "PF:INSPECTION": "PF:ADMINISTRATION",
            "PF:EDLI": "PF:EDLI_INSPECTION",
            "PF:EDLI_INSPECTION": "PF:EDLI",
        }[key[2]]
        if (*key[:2], alternative) in controls:
            raise ValueError(
                "Resolve mutually exclusive administration/insurance and inspection scope"
            )
    policies = [ChargeRule.model_validate(raw).model_dump(mode="json") for raw in tables["rules"]]
    reported = {}
    for row in tables["reported"]:
        if (
            row["component"]
            not in {"PF:ADMINISTRATION", "PF:INSPECTION", "PF:EDLI", "PF:EDLI_INSPECTION"}
            or row["currency"] != "INR"
            or row["subject"].upper() != row["registration"].upper()
            or row.get("arrear_scope")
            or row.get("population") == "arrears"
            or row.get("pension_scope")
            or row.get("savings_scope")
            or row.get("benefit_scope")
            or row.get("withholding_scope")
        ):
            raise ValueError("Use separate establishment-level monthly charge observations only")
        key = scope(row)
        if key in reported:
            raise ValueError("Restate duplicate establishment charge observations")
        reported[key] = row
    rows: list[dict[str, Any]] = []
    for key in sorted(controls.keys() | reported.keys()):
        control, observation = controls.get(key), reported.get(key)
        expected = selected = minimum = subtotal = None
        trace = []
        state = "CONTROL_MISSING" if control is None else None
        if control:
            year, month = map(int, control["period"].split("-"))
            first, last = (
                date(year, month, 1),
                date(year, month, calendar.monthrange(year, month)[1]),
            )
            if last > data.as_of:
                raise ValueError("Establishment charge month must be closed")
            population = members[key]
            if (
                len(population) != control["expected_members"]
                or sum(r["contributing"] for r in population) != control["expected_contributors"]
                or sum((Decimal(r["amount"]) for r in population), Decimal(0))
                != Decimal(control["amount"])
            ):
                state = "MEMBER_POPULATION_CONTROL_DIFFERENCE"
            candidates = [
                rule
                for rule in policies
                if (rule["component"], rule["rule_group"], rule["jurisdiction"])
                == (control["component"], control["rule_group"], control["jurisdiction"])
                and rule["effective_from"] <= last.isoformat()
                and rule["effective_to"] >= first.isoformat()
            ]
            if state is None:
                if (
                    len(candidates) != 1
                    or candidates[0]["effective_from"] > first.isoformat()
                    or candidates[0]["effective_to"] < last.isoformat()
                ):
                    state = "RULE_MISSING_SPLIT_OR_AMBIGUOUS"
                else:
                    selected = candidates[0]
                    rate = Decimal(selected["rate"])
                    for member in population:
                        wage = Decimal(member["amount"])
                        capped = (
                            min(wage, Decimal(selected["salary_cap"]))
                            if selected["salary_cap"] is not None
                            else wage
                        )
                        unrounded = capped * rate
                        trace.append(
                            {
                                "member_source_id": member["id"],
                                "subject": member["subject"],
                                "registration": key[0],
                                "period": key[1],
                                "component": key[2],
                                "assessed_wage": str(wage),
                                "capped_wage": str(capped),
                                "rate": selected["rate"],
                                "salary_cap": selected["salary_cap"],
                                "unrounded_charge": str(unrounded),
                                "member_rounded_charge": str(
                                    rounding(unrounded, selected["rounding"])
                                )
                                if selected["aggregation"] == "ROUND_MEMBERS_THEN_SUM"
                                else None,
                                "contributing_as_assessed": member["contributing"],
                                "evidence_reference": member["evidence_reference"],
                            }
                        )
                    if selected["aggregation"] == "ROUND_MEMBERS_THEN_SUM":
                        subtotal = sum(
                            (Decimal(r["member_rounded_charge"]) for r in trace),
                            Decimal(0),
                        )
                    else:
                        subtotal = rounding(Decimal(control["amount"]) * rate, selected["rounding"])
                    minimum = Decimal(
                        selected["minimum_non_functional"]
                        if control["establishment_state"] == "NON_FUNCTIONAL_NO_CONTRIBUTORS"
                        else selected["minimum_other"]
                    )
                    expected = max(subtotal, minimum)
        difference = (
            Decimal(observation["amount"]) - expected
            if observation and expected is not None
            else None
        )
        state = state or (
            "OBSERVATION_MISSING"
            if observation is None
            else "MATCHED"
            if difference == 0
            else "CHARGE_DIFFERENCE"
        )
        rows.append(
            {
                "id": "establishment-charge:" + str(len(rows) + 1),
                "registration": key[0],
                "subject": key[0],
                "period": key[1],
                "component": key[2],
                "currency": "INR",
                "member_source_ids": [r["id"] for r in members[key]],
                "member_trace": trace,
                "control_source_id": control["id"] if control else None,
                "basis_source_id": control["id"] if control else None,
                "rule_source_id": selected["id"] if selected else None,
                "rule_document_sha256": selected["source_sha256"] if selected else None,
                "rule_document_version_id": selected["source_evidence_version_id"]
                if selected
                else None,
                "rule_version": selected["source_version"] if selected else None,
                "reported_source_id": observation["id"] if observation else None,
                "assessed_wage_total": control["amount"] if control else None,
                "aggregation": selected["aggregation"] if selected else None,
                "charge_before_minimum": str(subtotal) if subtotal is not None else None,
                "applied_establishment_minimum": str(minimum) if minimum is not None else None,
                "expected_amount": str(expected) if expected is not None else None,
                "reported_amount": observation["amount"] if observation else None,
                "difference": str(difference) if difference is not None else None,
                "state": state,
            }
        )
    blocked = any(row["expected_amount"] is None for row in rows)
    return {
        "rows": rows,
        "blocked": blocked,
        "exception_count": sum(r["state"] != "MATCHED" for r in rows),
        "expected_total": str(
            sum(
                (Decimal(r["expected_amount"]) for r in rows if r["expected_amount"] is not None),
                Decimal(0),
            )
        ),
        "expected_total_complete": not blocked,
        "currency": "INR",
        "establishment_charge_contract": CONTRACT,
        "limitations": [
            "Assessed component wage populations, rates, caps, rounding, establishment status and minima only; no legal exemption or applicability is inferred",
            "Minima apply once per establishment/month/component, not once per employee; administration and inspection alternatives cannot be combined",
            "Independent reported amounts do not establish filing, payment, interest, damages or complete employee contribution coverage",
        ],
    }
