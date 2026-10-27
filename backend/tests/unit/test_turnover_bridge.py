"""Explicit synthetic UAE/India registration-period turnover populations."""

import uuid
from copy import deepcopy

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_country_workflows import parsed


def populations(country="AE"):
    base = dict(
        registration="100000000000001" if country == "AE" else "29ABCDE1234F1Z5",
        period_start="2026-04-01",
        period_end="2026-06-30",
        currency="AED" if country == "AE" else "INR",
        assessment="SYNTHETIC independently assessed net-of-tax population",
    )
    return {
        "scope": [dict(base, id="scope")],
        "books": [dict(base, id="book", reference="BOOK-1", amount="100.00000001")],
        "return": [dict(base, id="return", reference="FILED-1", amount="95.00000001")],
        "adjustments": [
            dict(base, id="adjustment", reference="BRIDGE-1", amount="-5", reason="timing")
        ],
    }


def compare(rows=None, country="AE", **changes):
    from app.modules.country_workflows.turnover import ROLES

    rows = rows or populations(country)
    sources = {role: parsed(ROLES[role], records) for role, records in rows.items()}
    data = WorkflowInput(
        workflow="tax-turnover-bridge",
        source_ids={role: uuid.uuid4() for role in sources},
        as_of="2026-06-30",
        currency="AED" if country == "AE" else "INR",
        title="SYNTHETIC turnover bridge",
        rationale="Explicit reviewed source scope and independently assessed differences",
        **changes,
    )
    return calculate(data, country, sources)


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_signed_bridge_exact_precision_and_retained_adjustment_assessment(country):
    result = compare(country=country)
    row = result["rows"][0]
    assert row["state"] == "MATCHED" and not result["blocked"]
    assert row["expected_return_turnover"] == "95.00000001"
    assert row["difference"] == "0E-8" and row["source_row_ids"]["adjustments"] == ["adjustment"]
    assert result["turnover_adjustment_rows"][0]["reason"] == "timing"
    assert not result["statutory_calculation_qualified"] and approval_error(result) is None


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_equal_opposite_registration_differences_do_not_net_to_a_match(country):
    rows = populations(country)
    for role, records in rows.items():
        extra = deepcopy(records[0])
        extra.update(
            id="second-" + role,
            registration="100000000000002" if country == "AE" else "27ABCDE1234F1Z5",
        )
        records.append(extra)
    rows["return"][0]["amount"] = "90.00000001"
    rows["return"][1]["amount"] = "100.00000001"
    result = compare(rows, country)
    assert result["exception_count"] == 2
    totals = result["turnover_difference_totals"]["AED" if country == "AE" else "INR"]
    assert totals == {"positive_difference": "5.00000000", "negative_difference": "-5.00000000"}
    assert all(row["state"] == "VARIANCE" for row in result["rows"])
    assert approval_error(result)


def test_absent_expected_registration_cannot_be_a_zero_or_hidden_scope():
    rows = populations()
    rows["scope"].append(dict(rows["scope"][0], id="unreported", registration="100000000000002"))
    result = compare(rows, tolerance="100000")
    missing = result["rows"][1]
    assert result["blocked"] and missing["state"] == "MISSING_POPULATION"
    assert missing["book_revenue"] is missing["reported_turnover"] is missing["difference"] is None
    assert set(missing["missing_roles"]) == {"books", "return", "adjustments"}


@pytest.mark.parametrize(
    "fault,match",
    [
        ("overlap", "Overlapping"),
        ("duplicate-scope", "Duplicate expected"),
        ("reference", "Duplicate turnover"),
        ("nil-conflict", "nil adjustments"),
        ("country", "registration syntax"),
        ("currency", "return currency"),
        ("future", "closed"),
    ],
)
def test_ambiguous_or_wrong_country_period_populations_are_rejected(fault, match):
    rows = populations()
    if fault == "overlap":
        rows["scope"].append(dict(rows["scope"][0], id="overlap", period_start="2026-05-01"))
    elif fault == "duplicate-scope":
        rows["scope"].append(dict(rows["scope"][0], id="duplicate"))
    elif fault == "reference":
        rows["books"].append(dict(rows["books"][0], id="duplicate"))
    elif fault == "nil-conflict":
        rows["adjustments"].append(
            dict(
                rows["adjustments"][0], id="nil", reference="NIL", reason="assessed-nil", amount="0"
            )
        )
    elif fault == "country":
        rows["return"][0]["registration"] = "29ABCDE1234F1Z5"
    elif fault == "currency":
        rows["return"][0]["currency"] = "USD"
    else:
        rows["return"][0]["period_end"] = "2026-07-01"
    with pytest.raises(ValueError, match=match):
        compare(rows)


def test_outside_scope_is_visible_and_hard_blocked():
    rows = populations()
    rows["return"].append(
        dict(rows["return"][0], id="extra", reference="EXTRA", registration="100000000000002")
    )
    result = compare(rows)
    assert result["blocked"] and result["rows"][1]["state"] == "OUTSIDE_DECLARED_SCOPE"


def test_explicit_nil_populations_and_adjustment_are_valid_not_missing():
    rows = populations()
    for role in ("books", "return", "adjustments"):
        rows[role][0]["amount"] = "0"
    rows["adjustments"][0]["reason"] = "assessed-nil"
    assert compare(rows)["rows"][0]["state"] == "MATCHED"
