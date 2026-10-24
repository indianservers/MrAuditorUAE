"""Monetary closing-rate arithmetic; classification and rates are reviewed inputs."""

from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from pydantic import Field

from app.modules.audit_execution.schemas import Strict


class MonetaryBalance(Strict):
    reference: str = Field(min_length=1, max_length=200)
    foreign_currency: str = Field(pattern=r"^[A-Z]{3}$")
    functional_currency: str = Field(pattern=r"^[A-Z]{3}$")
    foreign_units: Decimal = Field(max_digits=28, decimal_places=8)
    carrying_functional: Decimal = Field(max_digits=28, decimal_places=8)
    closing_rate: Decimal = Field(gt=0, max_digits=28, decimal_places=12)
    monetary_classification_reviewed: bool


def closing_revaluation(rows: list[MonetaryBalance], precision=2):
    with localcontext() as context:
        context.prec = 64
        return _closing_revaluation(rows, precision)


def _closing_revaluation(rows, precision):
    if not 1 <= len(rows) <= 1000 or type(precision) is not int or precision not in range(9):
        raise ValueError("Invalid FX population or rounding precision")
    if len({r.reference for r in rows}) != len(rows):
        raise ValueError("Duplicate monetary-item reference")
    if len({r.functional_currency for r in rows}) != 1:
        raise ValueError("Do not net balances in different functional currencies")
    import pycountry

    if any(
        pycountry.currencies.get(alpha_3=code) is None
        for r in rows
        for code in (r.foreign_currency, r.functional_currency)
    ):
        raise ValueError("Unknown ISO currency")
    quantum = Decimal(1).scaleb(-precision)
    output = []
    for row in rows:
        if row.foreign_currency == row.functional_currency:
            raise ValueError("Same-currency balances are not foreign-exchange revaluation items")
        if not row.monetary_classification_reviewed:
            raise ValueError(
                "Reviewed monetary classification required; nonmonetary items need a separate policy"
            )
        translated = (row.foreign_units * row.closing_rate).quantize(quantum, ROUND_HALF_EVEN)
        adjustment = (translated - row.carrying_functional).quantize(quantum, ROUND_HALF_EVEN)
        output.append(
            {
                "reference": row.reference,
                "foreign_currency": row.foreign_currency,
                "functional_currency": row.functional_currency,
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
        "rounding_policy": {
            "precision": precision,
            "method": "ROUND_HALF_EVEN",
            "basis": "Supplied approved currency policy",
        },
        "limitations": [
            "Not a realized FX or group translation/CTA schedule",
            "Rate applicability and classification require independent review",
        ],
    }
