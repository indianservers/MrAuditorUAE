"""Annual GST candidates from an explicitly assessed PAN population, not filing advice."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.modules.jurisdictions.profiles import Strict

CONTRACT = "india-annual-gst-candidates/1"
SOURCES = [
    "https://taxinformation.cbic.gov.in/view-pdf/1010465/ENG/Notifications",
    "https://taxinformation.cbic.gov.in/content-page/explore-act/1000315/1000001",
    "https://taxinformation.cbic.gov.in/content-page/explore-rules/1000468/1000001",
    "https://cbic-gst.gov.in/sectoral-faq.html",
]


class AnnualGSTScope(Strict):
    pan: str = Field(pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    financial_year_start: date
    financial_year_end: date
    rule_review_date: date
    taxpayer_type: Literal[
        "regular",
        "isd",
        "section-51",
        "section-52",
        "casual",
        "non-resident",
        "government-local-authority-audited",
        "composition",
        "mixed",
        "unknown",
    ]
    aggregate_turnover: Decimal | None = Field(
        default=None, ge=0, max_digits=28, decimal_places=8, allow_inf_nan=False
    )
    other_pan_turnover: Decimal | None = Field(
        default=None, ge=0, max_digits=28, decimal_places=8, allow_inf_nan=False
    )
    pan_population_complete: bool = False
    assessment: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def financial_year(self):
        if (
            self.financial_year_start.month != 4
            or self.financial_year_start.day != 1
            or (self.financial_year_end != date(self.financial_year_start.year + 1, 3, 31))
        ):
            raise ValueError("Annual GST candidates require the exact April-March financial year")
        if len(self.assessment.strip()) < 10:
            raise ValueError("Retain an explicit PAN population and taxpayer-status assessment")
        return self


def assess(scope, comparison, country, as_of):
    if country != "IN":
        raise ValueError("Annual Indian GST candidates are available only for India")
    reasons = []
    rows = comparison["rows"]
    registration_total = Decimal(0)
    periods: dict[str, list[tuple[date, date]]] = {}
    for row in rows:
        if row["registration"][2:12] != scope.pan:
            raise ValueError("Every annual turnover registration must belong to the declared PAN")
        start, end = date.fromisoformat(row["period_start"]), date.fromisoformat(row["period_end"])
        if not scope.financial_year_start <= start <= end <= scope.financial_year_end:
            raise ValueError(
                "Annual turnover partitions must stay inside the declared financial year"
            )
        periods.setdefault(row["registration"], []).append((start, end))
        if row["state"] != "MATCHED" or (
            row["difference"] is not None and Decimal(row["difference"]) != 0
        ):
            reasons.append("UNRESOLVED_TURNOVER_BRIDGE")
        if row["expected_return_turnover"] is not None:
            amount = Decimal(row["expected_return_turnover"])
            if amount < 0:
                reasons.append("NEGATIVE_REGISTRATION_TURNOVER_REQUIRES_REVIEW")
            registration_total += amount
    for intervals in periods.values():
        next_date = scope.financial_year_start
        for start, end in sorted(intervals):
            if start != next_date:
                reasons.append("REGISTRATION_YEAR_COVERAGE_INCOMPLETE")
            next_date = end + timedelta(days=1)
        if next_date != scope.financial_year_end + timedelta(days=1):
            reasons.append("REGISTRATION_YEAR_COVERAGE_INCOMPLETE")
    if not periods:
        reasons.append("REGISTRATION_YEAR_COVERAGE_INCOMPLETE")
    if not scope.pan_population_complete:
        reasons.append("PAN_POPULATION_NOT_ASSESSED_COMPLETE")
    if scope.aggregate_turnover is None or scope.other_pan_turnover is None:
        reasons.append("PAN_TURNOVER_CONTROL_MISSING")
    elif scope.aggregate_turnover != registration_total + scope.other_pan_turnover:
        reasons.append("PAN_TURNOVER_CONTROL_VARIANCE")
    if not date(2025, 9, 17) <= scope.rule_review_date <= date(2026, 10, 30):
        reasons.append("OUTSIDE_ASSESSED_RULE_REVIEW_WINDOW")
    if scope.financial_year_end > as_of:
        reasons.append("FINANCIAL_YEAR_NOT_CLOSED")
    if scope.financial_year_start.year not in {2024, 2025}:
        reasons.append("OUTSIDE_ASSESSED_RULE_YEARS")
    if scope.taxpayer_type in {"unknown", "mixed", "composition"}:
        reasons.append("TAXPAYER_STATUS_REQUIRES_SEPARATE_REVIEW")
    reasons = sorted(set(reasons))
    annual = reconciliation = "PENDING_REVIEW"
    if not reasons:
        if scope.taxpayer_type != "regular":
            annual = reconciliation = "CANDIDATE_SECTION_44_EXCLUSION"
        else:
            assert scope.aggregate_turnover is not None
            annual = (
                "CANDIDATE_EXEMPT_UP_TO_2_CRORE"
                if scope.aggregate_turnover <= Decimal("20000000")
                else "CANDIDATE_REQUIRED"
            )
            reconciliation = (
                "CANDIDATE_REQUIRED_SELF_CERTIFIED"
                if scope.aggregate_turnover > Decimal("50000000")
                else "CANDIDATE_THRESHOLD_NOT_EXCEEDED"
            )
    return {
        "contract": CONTRACT,
        "scope": scope.model_dump(mode="json"),
        "currency": "INR",
        "registration_turnover": str(registration_total),
        "gstr9": annual,
        "gstr9c": reconciliation,
        "pending_reasons": reasons,
        "source_urls": SOURCES,
        "statutory_qualification": False,
        "filing_status": "NOT_ESTABLISHED",
        "limitations": [
            "Candidate assessment for FY 2024-25 and 2025-26 only; current law, exclusions and notified relief require independent professional review",
            "PAN-wide turnover includes separately assessed other turnover; GSTIN turnover alone cannot establish the annual threshold",
            "Complete full-year registration partitions are required by this profile; new/cancelled registrations and mixed regimes need a separately assessed profile",
            "Government/local-authority status means the declared qualifying audited-books exclusion, not every government body",
            "No due-date extension, late fee, return preparation, self-certification or filing is inferred",
        ],
    }


def saved_current(body):
    parameters = body.get("parameters", {})
    if not isinstance(parameters, dict):
        return False
    scope = parameters.get("gst_annual_scope")
    if scope is None:
        return True
    assessment = body.get("annual_gst_assessment")
    return (
        isinstance(assessment, dict)
        and assessment.get("contract") == CONTRACT
        and assessment.get("scope") == scope
    )
