"""Authored arithmetic/oracle checks; no operative country-rate qualification."""

from datetime import date, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction

import pytest

from app.modules.country_workflows.interest_accrual import MissingRate, accrue


def terms(**changes):
    return {
        "start": "2026-06-01",
        "cutoff": "2026-07-31",
        "rest_basis": "CALENDAR_MONTH_END",
        "day_basis": "ACT_365_FIXED",
        "event_timing": "END_OF_DAY",
        "rest_rounding": "ROUND_EACH_REST",
        "rounding": "HALF_UP",
        "currency_scale": 2,
        "multiplier": "3",
        **changes,
    }


def rates(**changes):
    return [
        {
            "id": "SYNTHETIC-RATE",
            "effective_from": "2026-01-01",
            "effective_to": "2026-12-31",
            "annual_rate": "0.01",
            **changes,
        }
    ]


def event(category="PRINCIPAL", **changes):
    return {
        "id": "SYNTHETIC-EVENT",
        "day": "2026-06-16",
        "category": category,
        "origin": "BANK",
        "amount": "18250",
        **changes,
    }


def test_monthly_rest_capitalizes_interest_only_after_the_rest_day():
    result = accrue("36500", terms(), rates(), [])
    # June: 30 * 3 = 90. July: (36500 + 90) * .03 * 31 / 365 = 93.22849...
    assert result["expected_amount"] == "183.23"
    assert [r["capitalized_amount"] for r in result["monthly_rests"]] == ["90.00", "93.23"]
    assert result["segments"][1]["capitalized_interest_basis"] == "90.00"


@pytest.mark.parametrize("timing,wanted", [("END_OF_DAY", "69.00"), ("BEGINNING_OF_DAY", "67.50")])
def test_partial_principal_payment_has_explicit_payment_day_treatment(timing, wanted):
    result = accrue("36500", terms(cutoff="2026-06-30", event_timing=timing), rates(), [event()])
    assert result["expected_amount"] == wanted and result["principal_remaining"] == "18250"


def test_unposted_interest_payment_does_not_reduce_principal_or_earn_interest():
    result = accrue(
        "36500",
        terms(cutoff="2026-06-30"),
        rates(),
        [event(), event("UNCAPITALIZED_INTEREST", id="INTEREST", day="2026-06-20", amount="10")],
    )
    assert result["expected_amount"] == "59.00"
    assert result["interest_cash_paid"] == "10" and result["interest_charged_rounded"] == "69.00"


def test_capitalized_interest_payment_reduces_the_subsequent_interest_basis():
    result = accrue(
        "36500",
        terms(event_timing="BEGINNING_OF_DAY"),
        rates(),
        [event("CAPITALIZED_INTEREST", day="2026-07-01", amount="40")],
    )
    assert result["expected_amount"] == "143.13"
    assert result["interest_cash_paid"] == "40" and result["interest_charged_rounded"] == "183.13"


def test_principal_payment_does_not_silently_discharge_unpaid_interest():
    result = accrue("36500", terms(), rates(), [event(day="2026-06-30", amount="36500")])
    assert result["principal_remaining"] == "0" and result["expected_amount"] == "90.23"


def test_full_principal_and_accrued_interest_payment_before_rest_prevents_later_accrual():
    result = accrue(
        "36500",
        terms(),
        rates(),
        [
            event(day="2026-06-30", amount="36500"),
            event("UNCAPITALIZED_INTEREST", id="INTEREST", day="2026-06-30", amount="90"),
        ],
    )
    assert result["expected_amount"] == "0.00" and result["interest_cash_paid"] == "90"


def test_bank_rate_change_splits_accrual_on_its_inclusive_effective_date():
    windows = rates(effective_to="2026-06-15") + rates(
        id="NEXT", effective_from="2026-06-16", annual_rate="0.02"
    )
    result = accrue("36500", terms(cutoff="2026-06-30"), windows, [])
    assert result["expected_amount"] == "135.00"
    assert [(r["start"], r["end"], r["days"]) for r in result["segments"]] == [
        ("2026-06-01", "2026-06-15", 15),
        ("2026-06-16", "2026-06-30", 15),
    ]


@pytest.mark.parametrize("basis,wanted", [("ACT_ACT_YEAR", "9.00"), ("ACT_365_FIXED", "9.03")])
def test_leap_day_denominator_is_a_declared_convention(basis, wanted):
    result = accrue(
        "36600",
        terms(start="2024-02-28", cutoff="2024-03-01", day_basis=basis),
        rates(effective_from="2024-01-01", effective_to="2024-12-31"),
        [],
    )
    assert result["expected_amount"] == wanted


def test_actual_year_basis_splits_at_year_boundary():
    result = accrue(
        "36600",
        terms(start="2023-12-31", cutoff="2024-01-01", day_basis="ACT_ACT_YEAR"),
        rates(effective_from="2023-01-01", effective_to="2024-12-31"),
        [],
    )
    assert [r["year_denominator"] for r in result["segments"]] == [365, 366]
    assert result["expected_amount"] == "6.01"


def test_anniversary_rests_keep_the_original_anchor_day_without_month_end_drift():
    result = accrue(
        "36500",
        terms(start="2026-01-31", cutoff="2026-03-31", rest_basis="MONTHLY_ANNIVERSARY"),
        rates(),
        [],
    )
    assert [row["day"] for row in result["monthly_rests"]] == ["2026-02-27", "2026-03-30"]
    assert sum(row["days"] for row in result["segments"]) == 60


@pytest.mark.parametrize(
    "mode,rounding",
    [("HALF_UP", ROUND_HALF_UP), ("CEILING", ROUND_CEILING), ("FLOOR", ROUND_FLOOR)],
)
@pytest.mark.parametrize("stage", ["ROUND_EACH_REST", "CARRY_PRECISION"])
def test_monthly_rounding_against_independent_fraction_oracle(mode, rounding, stage):
    principal, rate = Fraction(73, 10), Fraction(27, 100)

    def money(value):
        with localcontext() as context:
            context.prec = 120
            return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
                Decimal(".01"), rounding=rounding
            )

    if stage == "CARRY_PRECISION":
        # Closed product for the three authored monthly factors, not an event-loop oracle.
        wanted = money(
            principal * ((1 + rate * 31 / 365) * (1 + rate * 28 / 365) * (1 + rate * 31 / 365) - 1)
        )
    else:
        january = money(principal * rate * 31 / 365)
        february = money((principal + Fraction(january)) * rate * 28 / 365)
        march = money((principal + Fraction(january + february)) * rate * 31 / 365)
        wanted = january + february + march
    result = accrue(
        "7.3",
        terms(
            start="2026-01-01",
            cutoff="2026-03-31",
            multiplier="1",
            rounding=mode,
            rest_rounding=stage,
        ),
        rates(annual_rate="0.27"),
        [],
    )
    assert Decimal(result["expected_amount"]) == wanted


def test_missing_rate_stays_unknown_even_if_explicit_principal_was_paid_before_start():
    with pytest.raises(MissingRate) as error:
        accrue("36500", terms(cutoff="2026-06-30"), [], [event(day="2026-05-31", amount="36500")])
    assert error.value.day == date(2026, 6, 1)


def test_interior_rate_gap_is_not_filled_from_the_prior_rate():
    with pytest.raises(MissingRate) as error:
        accrue(
            "36500",
            terms(cutoff="2026-06-30"),
            rates(effective_to="2026-06-15") + rates(id="NEXT", effective_from="2026-06-17"),
            [],
        )
    assert error.value.day == date(2026, 6, 16)


def test_competing_rate_windows_are_not_resolved_by_order_or_latest_date():
    with pytest.raises(ValueError, match="Competing rate"):
        accrue("36500", terms(), rates() + rates(id="NEXT", effective_from="2026-06-16"), [])


def test_document_adjustment_is_retained_without_becoming_a_bank_payment():
    result = accrue(
        "36500", terms(cutoff="2026-06-30"), rates(), [event(origin="DOCUMENT_ADJUSTMENT")]
    )
    assert result["expected_amount"] == "69.00" and result["interest_cash_paid"] == "0"
    assert result["balance_events"][0]["origin"] == "DOCUMENT_ADJUSTMENT"


def test_non_cash_interest_reduction_is_not_reported_as_cash_interest_paid():
    result = accrue(
        "36500",
        terms(cutoff="2026-06-30"),
        rates(),
        [
            event(
                "UNCAPITALIZED_INTEREST",
                origin="DOCUMENT_ADJUSTMENT",
                day="2026-06-30",
                amount="30",
            )
        ],
    )
    assert (
        result["expected_amount"] == "60.00"
        and result["interest_reductions"] == "30"
        and result["interest_cash_paid"] == "0"
    )


@pytest.mark.parametrize(
    "item",
    [
        event(amount="36501"),
        event("UNCAPITALIZED_INTEREST", day="2026-06-01", amount="10"),
        event("CAPITALIZED_INTEREST", amount="1"),
    ],
)
def test_overdraw_cannot_be_reclassified_into_another_bucket(item):
    with pytest.raises(ValueError, match="exceeds the assessed unpaid"):
        accrue("36500", terms(), rates(), [item])


@pytest.mark.parametrize(
    "item", [event(day="2026-08-01"), event("UNCAPITALIZED_INTEREST", day="2026-05-31", amount="1")]
)
def test_future_or_pre_start_interest_events_are_rejected(item):
    with pytest.raises(ValueError):
        accrue("36500", terms(), rates(), [item])


@pytest.mark.parametrize("value", [True, 0.1, "NaN", "Infinity", "-1", None])
def test_principal_does_not_accept_ambiguous_or_nonfinite_values(value):
    with pytest.raises(ValueError):
        accrue(value, terms(), rates(), [])


@pytest.mark.parametrize("value", ["2026-06-01T00:00:00", datetime(2026, 6, 1), 1780272000])
def test_calendar_scope_cannot_be_inferred_from_a_timestamp(value):
    with pytest.raises(ValueError):
        accrue("36500", terms(start=value), rates(), [])


def test_private_decimal_precision_and_maximum_calendar_day():
    with localcontext() as context:
        context.prec = 4
        result = accrue("36500", terms(), rates(), [])
        assert result["expected_amount"] == "183.23" and context.prec == 4
    last = accrue(
        "365",
        terms(start="9999-12-31", cutoff="9999-12-31", multiplier="1"),
        rates(effective_from="9999-12-31", effective_to="9999-12-31", annual_rate="1"),
        [],
    )
    assert last["expected_amount"] == "1.00"
