"""Historical AY and current TY headers cannot silently change a credit population."""

import json
from copy import deepcopy

import pytest

from app.modules.country_workflows.annual_tax_statement import (
    AnnualTaxStatement,
    validate_population,
)
from app.modules.country_workflows.withholding_schemas import WithholdingRecord
from tests.unit.test_shared_audit_workflows import source
from tests.unit.test_withholding_workflows import population, record, run

PAN = "ABCDE1234F"  # Fictional format example; registry validity is not claimed.


def header(year=2026, **changes):
    modern = year >= 2026
    displayed = year if modern else year + 1
    return {
        "form": "168" if modern else "26AS",
        "pan": PAN,
        "period_start": f"{year}-04-01",
        "period_end": f"{year + 1}-03-31",
        "displayed_year_basis": "TAX_YEAR" if modern else "ASSESSMENT_YEAR",
        "displayed_year": f"{displayed}-{(displayed + 1) % 100:02d}",
        "generated_on": f"{year}-06-30",
        **changes,
    }


def observation(year=2026, **changes):
    return (
        record(
            legal_role="deductee",
            registration=PAN,
            tax_year_start=f"{year}-04-01",
            tax_year_end=f"{year + 1}-03-31",
            period=f"{year}-05",
            transaction_date=f"{year}-05-15",
            annual_statement=header(year),
        )
        | changes
    )


@pytest.mark.parametrize("year", [2022, 2025, 2026, 2027, 2099])
def test_exact_underlying_year_and_displayed_year_are_distinct(year):
    item = WithholdingRecord.model_validate(observation(year))
    assert item.annual_statement.model_dump(mode="json") == header(year)
    if year == 2025:
        assert item.annual_statement.displayed_year == "2026-27"
        assert item.annual_statement.form == "26AS"
    if year == 2026:
        assert item.annual_statement.displayed_year == "2026-27"
        assert item.annual_statement.form == "168"


@pytest.mark.parametrize(
    "year,changes",
    [
        (2025, {"form": "168"}),
        (2026, {"form": "26AS"}),
        (2025, {"displayed_year_basis": "TAX_YEAR"}),
        (2026, {"displayed_year_basis": "ASSESSMENT_YEAR"}),
        (2025, {"displayed_year": "2025-26"}),
        (2026, {"displayed_year": "2027-28"}),
        (2026, {"period_start": "2026-05-01"}),
        (2026, {"period_end": "2026-12-31"}),
        (2026, {"period_end": "2028-03-31"}),
        (2026, {"generated_on": "2026-03-31"}),
        (2026, {"pan": "ABCDE１２３４F"}),
        (2026, {"pan": "abcde1234f"}),
        (2026, {"displayed_year": "2026-2027"}),
        (2026, {"form": "26"}),
    ],
)
def test_wrong_form_year_basis_or_unresolved_header_fails(year, changes):
    with pytest.raises(ValueError):
        AnnualTaxStatement.model_validate(header(year, **changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"registration": "ZZZZZ1234Z"},
        {"tax_year_start": "2026-03-01"},
        {"tax_year_end": "2027-04-01"},
        {"transaction_date": "2026-07-01"},
        {"period": "2026-07"},
        {"legal_role": "deductor"},
        {"legal_role": "collector", "tax_kind": "TCS"},
    ],
)
def test_header_cannot_relabel_a_different_record(changes):
    with pytest.raises(ValueError):
        WithholdingRecord.model_validate(observation(**changes))


def test_collectee_statement_is_allowed_but_does_not_establish_tcs_entitlement():
    item = WithholdingRecord.model_validate(observation(legal_role="collectee", tax_kind="TCS"))
    assert item.tax_kind == "TCS"


@pytest.mark.parametrize("year", [2025, 2026])
def test_canonical_csv_preserves_declared_scope_original_bytes_and_controls(year):
    row = observation(year)
    row["annual_statement"] = json.dumps(row["annual_statement"])
    original = deepcopy(row)
    parsed = source("withholding-records", [row])
    assert row == original
    assert parsed["rows"][0]["annual_statement"] == header(year)
    assert parsed["control_totals"] == {"INR": "100"}


@pytest.mark.parametrize("role", ["books", "certificate", "reported", "deposited", "expected"])
def test_annual_header_is_not_book_certificate_or_liability_evidence(role):
    with pytest.raises(ValueError, match="statement source"):
        validate_population({role: [observation()]})


def test_declared_statement_cannot_cover_unscoped_rows_by_association():
    one = observation()
    two = {**one, "id": "TX2"}
    two.pop("annual_statement")
    with pytest.raises(ValueError, match="mix declared and unscoped"):
        validate_population({"statement": [one, two]})


def test_different_pans_cannot_share_one_statement_population():
    two = observation(registration="ZZZZZ1234Z", annual_statement=header(pan="ZZZZZ1234Z"))
    with pytest.raises(ValueError, match="one PAN"):
        validate_population({"statement": [observation(), two]})


def test_one_version_cannot_have_two_statement_snapshot_dates():
    two = observation(annual_statement=header(generated_on="2026-07-01"))
    with pytest.raises(ValueError, match="conflicting snapshot"):
        validate_population({"statement": [observation(), two]})


def credit_population():
    p = population("deductee")
    for rows in p.values():
        rows[0]["registration"] = PAN
    p["statement"][0]["annual_statement"] = json.dumps(header())
    return p


def test_current_and_superseded_snapshots_preserve_scope_without_summing_credit():
    p = credit_population()
    p["statement"].append(
        {
            **p["statement"][0],
            "id": "prior-snapshot",
            "source_version": "0",
            "record_status": "superseded",
            "amount": "150",
            "annual_statement": json.dumps(header(generated_on="2026-05-31")),
        }
    )
    out = run(p, "deductee")
    assert out["rows"][0]["state"] == "MATCHED"
    assert out["rows"][0]["amounts"]["statement"] == "100"
    assert out["rows"][0]["excluded_source_ids"]["statement"] == ["prior-snapshot"]
    assert out["rows"][0]["annual_statement"] == header()
    assert out["rows"][0]["credit_entitlement"] == "NOT_DETERMINED"
    assert out["annual_statement_scopes"] == [
        {"source_version": "0", **header(generated_on="2026-05-31")},
        {"source_version": "1", **header()},
    ]
    assert out["annual_statement_scope_basis"] == (
        "DECLARED_NORMALIZATION_NOT_NATIVE_HEADER_VERIFICATION"
    )


def test_generic_credit_evidence_does_not_implicitly_claim_a_portal_form():
    out = run(population("deductee"), "deductee")
    assert "annual_statement_scopes" not in out
    assert "annual_statement" not in out["rows"][0]


@pytest.mark.parametrize("country", ["AE", "GB"])
def test_indian_statement_scope_never_enables_another_country(country):
    with pytest.raises(ValueError, match="unavailable"):
        run(credit_population(), "deductee", country=country)


@pytest.mark.parametrize("value", ["not JSON", "[]", "true", "null"])
def test_csv_does_not_drop_malformed_or_null_header_claims(value):
    with pytest.raises(ValueError):
        WithholdingRecord.model_validate(observation(annual_statement=value))
