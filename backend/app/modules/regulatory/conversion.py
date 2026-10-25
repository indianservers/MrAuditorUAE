"""Evidence-bound currency arithmetic; no inferred quote, direction or tax policy."""

import uuid
from datetime import date
from decimal import ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from typing import Literal

import pycountry
from pydantic import Field, HttpUrl, model_validator

from app.modules.jurisdictions.profiles import Strict


class ExchangeRate(Strict):
    id: str = Field(min_length=1, max_length=120)
    source_currency: str = Field(pattern=r"^[A-Z]{3}$")
    target_currency: str = Field(pattern=r"^[A-Z]{3}$")
    rate: Decimal = Field(gt=0, max_digits=28, decimal_places=18, allow_inf_nan=False)
    coverage_start: date
    coverage_end: date
    rate_date: date
    method: Literal["closing", "period-average", "assessed"]
    source_url: HttpUrl
    source_evidence_version_id: uuid.UUID
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_version: str = Field(min_length=1, max_length=120)
    applicability_review: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def explicit_scope(self):
        if self.source_currency == self.target_currency or any(
            pycountry.currencies.get(alpha_3=value) is None
            for value in (self.source_currency, self.target_currency)
        ):
            raise ValueError(
                "Exchange rates require distinct recognized source and target currencies"
            )
        if not self.coverage_start <= self.rate_date <= self.coverage_end:
            raise ValueError("Exchange rate date must lie in its declared coverage")
        if len(self.applicability_review.strip()) < 10:
            raise ValueError("An explicit exchange rate applicability assessment is required")
        return self


class ConversionInput(Strict):
    source_event_id: uuid.UUID
    rate_source_id: uuid.UUID
    rate_row_id: str = Field(min_length=1, max_length=120)
    decimal_places: int = Field(ge=0, le=8)
    rounding: Literal["half-up", "half-even", "towards-zero", "floor"]
    target_amount: Decimal = Field(max_digits=28, decimal_places=8, allow_inf_nan=False)
    title: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def meaningful_assessment(self):
        if len(self.assessment.strip()) < 10 or not self.rate_row_id.strip():
            raise ValueError("An explicit conversion and rounding assessment is required")
        return self


def calculate(amount, currency, start, end, quote, data):
    rate = ExchangeRate.model_validate(
        {key: value for key, value in quote.items() if key in ExchangeRate.model_fields}
    )
    if rate.source_currency != currency:
        raise ValueError(
            "Rate direction differs from the source currency; no reciprocal is inferred"
        )
    if rate.method == "closing":
        if rate.rate_date != end or rate.coverage_start != end or rate.coverage_end != end:
            raise ValueError("A closing rate must identify the reporting date exactly")
    elif not rate.coverage_start <= start <= end <= rate.coverage_end:
        raise ValueError("Rate coverage does not include the complete reporting period")
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        original = Decimal(str(amount))
        exponent = original.as_tuple().exponent
        if (
            not original.is_finite()
            or original.copy_abs() >= Decimal("1e20")
            or not isinstance(exponent, int)
            or exponent < -18
        ):
            raise ValueError("Conversion source amount exceeds the supported bound")
        unrounded = original * rate.rate
        converted = unrounded.quantize(
            Decimal(1).scaleb(-data.decimal_places),
            rounding={
                "half-up": ROUND_HALF_UP,
                "half-even": ROUND_HALF_EVEN,
                "towards-zero": ROUND_DOWN,
                "floor": ROUND_FLOOR,
            }[data.rounding],
        )
    if converted != data.target_amount:
        raise ValueError("Independent converted amount control does not agree")
    return {
        "conversion_contract": "reviewed-rate-conversion/1",
        "source_amount": str(original),
        "source_currency": currency,
        "target_currency": rate.target_currency,
        "rate": str(rate.rate),
        "unrounded_amount": str(unrounded),
        "converted_amount": str(converted),
        "decimal_places": data.decimal_places,
        "rounding": data.rounding,
        "rate_quote": rate.model_dump(mode="json"),
        "rate_source_row": quote.get("source_row"),
        "assessment": data.assessment,
    }


async def prepare(db, ctx, eng, data, request_id):
    from fastapi import HTTPException

    from app.db.models.platform import FinancialPeriod, LegalEntity
    from app.modules.intelligence import service

    source = await service.event(db, ctx, eng.id, data.source_event_id, True)
    rates = await service.event(db, ctx, eng.id, data.rate_source_id, True)
    if source.kind != "lead" or source.body.get("review_status") != "REVIEWED":
        raise HTTPException(409, "A current independently reviewed lead schedule is required")
    if (
        rates.kind != "workflow-source"
        or rates.body.get("table_type") != "fx-rates"
        or rates.body.get("review_status") != "REVIEWED"
    ):
        raise HTTPException(
            409, "A current independently reviewed exchange rate source is required"
        )
    quote = next((row for row in rates.body["rows"] if row["id"] == data.rate_row_id), None)
    if quote is None:
        raise HTTPException(422, "Select an exchange rate row from the reviewed source")
    period = await db.get(FinancialPeriod, eng.period_id)
    entity = await db.get(LegalEntity, eng.entity_id)
    try:
        result = calculate(
            source.body["totals"]["closing"],
            entity.functional_currency,
            period.start_date,
            period.end_date,
            quote,
            data,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return await service.append(
        db,
        ctx,
        eng,
        "regulatory-conversion",
        {
            **result,
            "rows": [
                {
                    "id": "conversion",
                    **{
                        key: result[key]
                        for key in (
                            "source_amount",
                            "source_currency",
                            "rate",
                            "target_currency",
                            "unrounded_amount",
                            "converted_amount",
                            "decimal_places",
                            "rounding",
                        )
                    },
                    "state": "MATCHED",
                }
            ],
            "title": data.title,
            "review_status": "UNVERIFIED",
            "source_event_id": str(source.id),
            "rate_source_id": str(rates.id),
            "contributors": sorted(
                {
                    str(ctx.user_id),
                    *source.body.get("contributors", [str(source.created_by)]),
                    *rates.body.get("contributors", [str(rates.created_by)]),
                }
            ),
            "professional_conclusion": "NOT_DETERMINED",
            "population_completeness": "SELECTED_REVIEWED_LEAD_AND_RATE_ONLY",
            "limitations": [
                "Explicit retained direct rate and assessed rounding only; no automatic retrieval, reciprocal, legal policy selection or posting",
                "Independent review is required before use in a regulatory assessment",
            ],
        },
        [service.event_receipt(source), service.event_receipt(rates)],
        request_id,
    )
