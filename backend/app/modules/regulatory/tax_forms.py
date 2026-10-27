"""Tax-period/designation guards, not official form content or filing authority."""

import uuid
from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from app.modules.jurisdictions.profiles import Strict

INDIA_TRANSITION = date(2026, 4, 1)
FORM_GUIDANCE = "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/income-tax-forms?mobile-app=1"
FORM_26_GUIDANCE = "https://www.incometaxindia.gov.in/documents/d/guest/fn-26"
SCOPE_CONTRACT = "assessed-tax-period-form/1"


def india_tax_regime(start):
    return "2025-ACT" if start >= INDIA_TRANSITION else "1961-ACT"


class IndiaTaxAuditScope(Strict):
    applicability_id: uuid.UUID
    tax_period_start: date
    tax_period_end: date
    audited_under_other_law: bool = Field(strict=True)
    form: Literal["3CA-3CD", "3CB-3CD", "26"]
    audit_report_part: Literal["C", "D"] | None = None

    @model_validator(mode="after")
    def selected_form(self):
        start, end = self.tax_period_start, self.tax_period_end
        if end < start:
            raise ValueError("Tax period dates must be ordered")
        closing_year = start.year + (1 if start.month >= 4 else 0)
        if closing_year > 9999 or end > date(closing_year, 3, 31):
            raise ValueError("A tax-audit period cannot span two Indian tax years")
        modern = india_tax_regime(start) == "2025-ACT"
        expected = "26" if modern else "3CA-3CD" if self.audited_under_other_law else "3CB-3CD"
        part = ("C" if self.audited_under_other_law else "D") if modern else None
        if self.form != expected or self.audit_report_part != part:
            raise ValueError(
                "Tax-audit form/report part differs from the selected tax period and other-law audit basis"
            )
        return self

    def facts(self):
        return {
            "tax_period_start": self.tax_period_start.isoformat(),
            "tax_period_end": self.tax_period_end.isoformat(),
            "tax_audit_form": self.form,
            "audited_under_other_law": self.audited_under_other_law,
            **({"audit_report_part": self.audit_report_part} if self.audit_report_part else {}),
        }

    def covered_by(self, start, end):
        return start <= self.tax_period_start and self.tax_period_end <= end


def require_assessed_tax_scope(scope, body):
    if (
        body.get("area") != "india-tax-audit"
        or body.get("country") != "IN"
        or body.get("review_status") != "REVIEWED"
        or not body.get("items")
    ):
        raise ValueError(
            "A current independently reviewed India tax-audit applicability case is required"
        )
    if any(
        item.get("state") not in {"PREPARED", "NOT_APPLICABLE", "EXCEPTION_IDENTIFIED"}
        for item in body["items"]
    ):
        raise ValueError(
            "Resolve the tax-audit applicability case's outstanding clauses before report composition"
        )
    if any(
        item.get("state") in {"PREPARED", "EXCEPTION_IDENTIFIED"}
        and (
            not item.get("evidence_ids")
            or len(item.get("procedure", "").strip()) < 10
            or len(item.get("conclusion", "").strip()) < 10
        )
        for item in body["items"]
    ):
        raise ValueError(
            "Prepared tax-audit clauses and documented exceptions require evidence, procedures and conclusions"
        )
    facts = scope.facts()
    for item in body["items"]:
        supplied = item.get("facts", {})
        result = item.get("applicability_result", {})
        if (
            item.get("state") == "PREPARED"
            and item.get("evidence_ids")
            and len(item.get("procedure", "").strip()) >= 10
            and len(item.get("conclusion", "").strip()) >= 10
            and result.get("applicability") == "APPLICABLE"
            and not result.get("missing_fact_provenance")
            and all(
                type(supplied.get(key)) is type(value) and supplied[key] == value
                for key, value in facts.items()
            )
            and all(
                item.get("fact_sources", {}).get(key, {}).get("comparison") == "exact"
                for key in facts
            )
        ):
            return
    raise ValueError(
        "The reviewed applicability case must bind the exact tax period, form, report part and other-law audit basis to retained sources"
    )


def has_tax_scope_contract(body, dependencies):
    if body.get("category") != "india-tax-audit":
        return True
    if body.get("tax_form_scope_contract") != SCOPE_CONTRACT:
        return False
    try:
        scope = IndiaTaxAuditScope.model_validate(body.get("tax_audit_scope"))
    except ValueError:
        return False
    return any(
        dep.get("type") == "event" and dep.get("id") == str(scope.applicability_id)
        for dep in dependencies
    )
