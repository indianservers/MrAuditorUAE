"""Monetary closing-rate arithmetic; classification and rates are reviewed inputs."""

from decimal import ROUND_HALF_EVEN, Decimal

from pydantic import Field

from app.modules.audit_execution.schemas import Strict


class MonetaryBalance(Strict):
    reference: str = Field(min_length=1, max_length=200)
    foreign_units: Decimal = Field(max_digits=28, decimal_places=8)
    carrying_functional: Decimal = Field(max_digits=28, decimal_places=8)
    closing_rate: Decimal = Field(gt=0, max_digits=28, decimal_places=12)
    monetary_classification_reviewed: bool


def closing_revaluation(rows: list[MonetaryBalance], precision=2):
    if not 1 <= len(rows) <= 1000 or precision not in range(9):
        raise ValueError("Invalid FX population or rounding precision")
    if len({r.reference for r in rows}) != len(rows):
        raise ValueError("Duplicate monetary-item reference")
    quantum = Decimal(1).scaleb(-precision)
    output = []
    for row in rows:
        if not row.monetary_classification_reviewed:
            raise ValueError(
                "Reviewed monetary classification required; nonmonetary items need a separate policy"
            )
        translated = (row.foreign_units * row.closing_rate).quantize(quantum, ROUND_HALF_EVEN)
        adjustment = (translated - row.carrying_functional).quantize(quantum, ROUND_HALF_EVEN)
        output.append(
            {
                "reference": row.reference,
                "foreign_units": str(row.foreign_units),
                "carrying_functional": str(row.carrying_functional),
                "closing_rate": str(row.closing_rate),
                "closing_functional": str(translated),
                "proposed_balance_adjustment": str(adjustment),
                "review_status": "UNREVIEWED",
            }
        )
    return {
        "rows": output,
        "net_balance_adjustment": str(
            sum((Decimal(r["proposed_balance_adjustment"]) for r in output), Decimal(0))
        ),
        "basis": "Functional-currency monetary closing balances; debit/liability signs follow source ledger",
        "realized_fx": None,
        "presentation_currency_translation": None,
        "journal_posted": False,
        "limitations": [
            "Not a realized FX or group translation/CTA schedule",
            "Rate applicability and classification require independent review",
        ],
    }
