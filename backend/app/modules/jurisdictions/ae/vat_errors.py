"""Historical VAT difference schedule; filing acceptance and correction route stay reviewed facts."""

from datetime import date
from decimal import Decimal, localcontext

from pydantic import Field, model_validator

from app.modules.audit_execution.schemas import Strict


class PeriodError(Strict):
    period_start: date
    period_end: date
    filed_tax_due_aed: Decimal = Field(max_digits=28, decimal_places=8)
    corrected_tax_due_aed: Decimal = Field(max_digits=28, decimal_places=8)

    @model_validator(mode="after")
    def dates(self):
        if self.period_end < self.period_start:
            raise ValueError("Invalid VAT correction period")
        return self


class ErrorSchedule(Strict):
    periods: list[PeriodError] = Field(min_length=1, max_length=1000)
    correction_rule_review: str = Field(min_length=10, max_length=4000)


def calculate(data: ErrorSchedule):
    ordered = sorted(data.periods, key=lambda row: row.period_start)
    if any(left.period_end >= right.period_start for left, right in zip(ordered, ordered[1:])):
        raise ValueError(
            "Duplicate or overlapping VAT filing periods; do not count a correction twice"
        )
    with localcontext() as context:
        context.prec = 64
        rows = [
            {
                "period_start": str(r.period_start),
                "period_end": str(r.period_end),
                "filed_tax_due_aed": str(r.filed_tax_due_aed),
                "corrected_tax_due_aed": str(r.corrected_tax_due_aed),
                "difference_aed": str(r.corrected_tax_due_aed - r.filed_tax_due_aed),
                "direction": "additional_tax_review"
                if r.corrected_tax_due_aed > r.filed_tax_due_aed
                else "reduction_review"
                if r.corrected_tax_due_aed < r.filed_tax_due_aed
                else "no_quantified_difference",
                "correction_workflow": "PROFESSIONAL_REVIEW_REQUIRED",
            }
            for r in ordered
        ]
        return {
            "rows": rows,
            "gross_increases_aed": str(
                sum((max(Decimal(r["difference_aed"]), Decimal(0)) for r in rows), Decimal(0))
            ),
            "gross_decreases_aed": str(
                sum((max(-Decimal(r["difference_aed"]), Decimal(0)) for r in rows), Decimal(0))
            ),
            "netting_permitted": None,
            "filing_acceptance_verified": False,
            "submitted": False,
            "rule_review": data.correction_rule_review,
            "limitations": [
                "Arithmetic uses supplied reviewed period totals; original filing acceptance is not authenticated",
                "Thresholds, discovery deadlines and the permitted current-return/disclosure route require approved effective rules; no automatic route conclusion",
            ],
        }
