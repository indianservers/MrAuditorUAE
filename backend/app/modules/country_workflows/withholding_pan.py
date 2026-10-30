"""Reserved missing-PAN observations need explicit retained treatment, never inferred identity."""

import re
from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.modules.jurisdictions.profiles import Strict

CONTRACT = "withholding-missing-pan-treatment/1"
MARKERS = frozenset({"PANNOTAVBL", "PANAPPLIED", "PANINVALID"})


def marker(value):
    normalized = value.strip().upper() if isinstance(value, str) else ""
    return normalized if normalized in MARKERS else None


class MissingPANTreatment(Strict):
    marker: Literal["PANNOTAVBL", "PANAPPLIED", "PANINVALID"]
    party_reference: str = Field(min_length=1, max_length=120, pattern=r"^\S(?:.*\S)?$")
    treatment_reference: str = Field(min_length=1, max_length=120, pattern=r"^\S(?:.*\S)?$")
    assessed_on: date
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("assessed_on", mode="before")
    @classmethod
    def exact_date(cls, value):
        if (
            type(value) is date
            or isinstance(value, str)
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        ):
            return value
        raise ValueError("PAN treatment requires an explicit ISO assessment date")

    @model_validator(mode="after")
    def meaningful(self):
        if marker(self.party_reference) or len(self.assessment.strip()) < 10:
            raise ValueError(
                "Retain an actual assessed party reference and meaningful missing-PAN treatment"
            )
        return self


def assess(counterparty, record, as_of, assessment_issues):
    observed = marker(counterparty)
    if observed is None:
        return {}
    issues = []
    context = record.get("pan_treatment") if record else None
    validated = None
    if context is None:
        issues.append("PAN_TREATMENT_ASSESSMENT_MISSING")
    else:
        try:
            validated = MissingPANTreatment.model_validate(context)
        except (ValueError, TypeError):
            issues.append("PAN_TREATMENT_ASSESSMENT_INVALID")
    if validated:
        if validated.marker != observed:
            issues.append("PAN_MARKER_DIFFERS_FROM_ASSESSED_TREATMENT")
        if validated.treatment_reference != record.get("rule_reference"):
            issues.append("PAN_TREATMENT_REFERENCE_DIFFERS_FROM_RULE")
        if validated.assessed_on > as_of:
            issues.append("PAN_TREATMENT_ASSESSMENT_AFTER_CUTOFF")
        if assessment_issues:
            issues.append("PAN_TREATMENT_RETAINED_ASSESSMENT_NOT_SUPPORTED")
    return {
        "pan_status": observed,
        "pan_issues": issues,
        "pan_treatment_state": "PENDING_ASSESSMENT"
        if issues
        else "DOCUMENTED_ON_RETAINED_ASSESSMENT",
        "pan_treatment": validated.model_dump(mode="json") if validated else None,
        "pan_authentication": "NOT_PERFORMED",
    }


def identity_scope(record):
    context = record.get("pan_treatment")
    return (
        (context.get("marker"), context.get("party_reference"))
        if isinstance(context, dict)
        else None
    )


def relevant_rows(body):
    if body.get("workflow") not in {"india-withholding-liability", "india-withholding-credit"}:
        return []
    return [
        row
        for row in body.get("rows", [])
        if isinstance(row, dict) and marker(row.get("counterparty"))
    ]


def counts(rows):
    selected = [row for row in rows if marker(row.get("counterparty"))]
    pending = sum(
        row.get("pan_treatment_state") != "DOCUMENTED_ON_RETAINED_ASSESSMENT"
        or bool(row.get("pan_issues"))
        for row in selected
    )
    return {
        "rows_with_marker": len(selected),
        "pending_rows": pending,
        "documented_rows": len(selected) - pending,
    }


def current(body):
    rows = relevant_rows(body)
    if not rows:
        return True
    if body.get("withholding_pan_contract") != CONTRACT:
        return False
    if body.get("withholding_pan_counts") != counts(body.get("rows", [])):
        return False
    for row in rows:
        if (
            row.get("pan_status") != marker(row.get("counterparty"))
            or row.get("pan_authentication") != "NOT_PERFORMED"
            or not isinstance(row.get("pan_issues"), list)
            or row.get("pan_treatment_state")
            not in {"PENDING_ASSESSMENT", "DOCUMENTED_ON_RETAINED_ASSESSMENT"}
        ):
            return False
        if row["pan_treatment_state"] == "DOCUMENTED_ON_RETAINED_ASSESSMENT":
            try:
                treatment = MissingPANTreatment.model_validate(row.get("pan_treatment"))
            except (ValueError, TypeError):
                return False
            provenance = row.get("assessment_provenance")
            if (
                row["pan_issues"]
                or treatment.marker != row["pan_status"]
                or treatment.treatment_reference != row.get("rule_reference")
                or not isinstance(provenance, dict)
                or not provenance.get("assessment_evidence_version_id")
                or not provenance.get("assessment_sha256")
            ):
                return False
    return True


def approval_error(body):
    if not current(body):
        return "Regenerate missing-PAN comparisons with current retained PAN-treatment controls before approval or downstream use"
    if any(
        row.get("pan_issues")
        or row.get("pan_treatment_state") != "DOCUMENTED_ON_RETAINED_ASSESSMENT"
        for row in relevant_rows(body)
    ):
        return "Resolve the missing-PAN identity and treatment assessment in the retained rule/certificate source, then regenerate"
    return None
