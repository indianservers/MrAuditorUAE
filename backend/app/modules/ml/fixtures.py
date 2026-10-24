"""Publicly shareable synthetic contract fixtures, with no client source records."""

from datetime import date
from decimal import Decimal

from app.modules.ml.contracts import FinancialPopulation

SECTORS = ("trading", "professional-services", "construction", "real-estate", "free-zone", "group")


def financial_fixture(sector: str) -> FinancialPopulation:
    if sector not in SECTORS:
        raise ValueError("Unknown synthetic sector")
    journals, lines = [], []
    for i, day in enumerate((date(2026, 1, 31), date(2026, 6, 30), date(2026, 12, 31))):
        amount = Decimal("100.25")
        foreign = i == 1
        base = amount * (Decimal("3.6725") if foreign else Decimal(1))
        journal = f"synthetic-{sector}-{i}"
        journals.append(
            {
                "id": journal,
                "posting_date": day,
                "complete": i != 2,
                "source": "SYNTHETIC recurring monthly journal",
                "manual": i == 2,
                "reversal_of": f"synthetic-{sector}-0" if i == 2 else None,
            }
        )
        for side in range(1 if i == 2 else 2):
            debit = (side == 0) != (i == 2)
            lines.append(
                {
                    "id": journal + f"-{side}",
                    "journal_id": journal,
                    "account_id": "a" if side == 0 else "b",
                    "debit": amount if debit else Decimal(0),
                    "credit": Decimal(0) if debit else amount,
                    "base_debit": base if debit else Decimal(0),
                    "base_credit": Decimal(0) if debit else base,
                    "currency": "USD" if foreign else "AED",
                    "description": None if i == 2 else "SYNTHETIC recurring service قيد خدمات",
                    "project": "SYNTHETIC-project" if sector == "construction" else None,
                }
            )
    return FinancialPopulation.model_validate(
        {
            "tenant_id": "SYNTHETIC-isolated-tenant",
            "entity_id": "SYNTHETIC-" + sector,
            "source_system": "local-generated-fixture",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "functional_currency": "AED",
            "expected_line_count": len(lines),
            "usage_permission": "synthetic_only",
            "accounts": [
                {"id": "a", "code": "1000", "name": "مصروف خدمات", "canonical_type": "Expenses"},
                {"id": "b", "code": "2000", "name": "Bank", "canonical_type": "Assets"},
            ],
            "journals": journals,
            "lines": lines,
        }
    )
