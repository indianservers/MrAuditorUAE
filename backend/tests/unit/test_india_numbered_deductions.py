"""Dated original samples and explicit synthetic completions, never issuer/FVU or treaty proof."""

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.country_workflows.india_numbered_deductions import SPECS, layout
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput
from tests.unit.test_india_withholding_native import edit

ROOT = Path(__file__).resolve().parents[3] / "docs/country-workflows/authority-references"


def original(form):
    return (
        ROOT / f"form{form}-2026-07-22" / f"protean-form{form}-original-sample.txt"
    ).read_bytes()


def synthetic(form):
    raw = original(form)
    for line, field, value in [
        (3, 17, "00001"),
        (3, 24, "1000.00"),
        (3, 25, "100.00" if form == "140" else "1000.00"),
        (4, 18, "Y"),
    ]:
        raw = edit(raw, line, field, value)
    if form == "144":
        raw = edit(raw, 4, 33, "1234567890")
    return raw


def controls(form):
    return {
        "tax_year": "202627",
        "tan": "BLRF02329F",
        "quarter": "Q1",
        "observed_on": "2026-10-31",
        "batch_count": 1,
        "challan_count": 1,
        "party_count": 1,
        "tax_deducted": "900" if form == "140" else "2000",
        "allocated_deposit": "900" if form == "140" else "2000",
        "challan_deposit": "11200" if form == "140" else "24000",
        "payment_base": "1000" if form == "140" else "2100",
        "challan_tax": "10000" if form == "140" else "21000",
        "challan_interest": "1000",
        "challan_fee": "100" if form == "140" else "1000",
        "challan_penalty": "100" if form == "140" else "1000",
        "allocated_interest": "1000",
        "allocated_penalty": "100" if form == "140" else "1000",
        "cash_withdrawal_general": "0",
        "cash_withdrawal_cooperative": "0",
        "record_status": "current",
        "crosswalk_document_version_id": str(uuid4()),
        "assessment": "SYNTHETIC independently specified dated numbered source/cash controls and retained transaction crosswalk; no legal or client qualification",
        "groups": [
            {
                "transaction_reference": "SYN-ASSESSMENT-1",
                "transaction_date": "2026-05-02" if form == "140" else "2026-05-01",
                "period": "2026-05",
                "rule_reference": "SYN-ASSESSED-SECTION",
                "party_records": ["1/1/1"],
            }
        ],
    }


def options(form, **changes):
    return SourceInput.model_validate(
        {
            "file_format": f"india-form{form}-regular-20260722-v1.1",
            "evidence_version_id": str(uuid4()),
            "table_type": "withholding-records",
            "label": f"SYNTHETIC dated Form{form} observations",
            "expected_rows": 1,
            "control_totals": {"INR": "900" if form == "140" else "2000"},
            "numbered_deduction_controls": controls(form),
            **changes,
        }
    )


def parse(form, raw=None, **changes):
    return parse_native(
        raw if raw is not None else synthetic(form),
        options(form, **changes),
        "IN",
        f"SYNTHETIC-{form}.txt",
    )


@pytest.mark.parametrize("form", ["140", "144"])
def test_original_sample_is_kept_exact_and_not_silently_completed(form):
    expected = {
        "140": "0a9d7ae16e99f30f14d13c092ab52d115223f04534d0b015d3d581f4c17c271f",
        "144": "f03b62d56b888432a71102af5e3edc4a220db69f27b9ae8cd6a891f8b279375a",
    }
    assert hashlib.sha256(original(form)).hexdigest() == expected[form]
    assert (
        hashlib.sha256(
            (ROOT / f"form{form}-2026-07-22" / f"protean-form{form}-22072026.xlsx").read_bytes()
        ).hexdigest()
        == SPECS[form]
    )
    selected, _ = layout(form)
    assert {k: len(v) for k, v in selected["field_lengths"].items()} == {
        "FH": 18,
        "BH": 72,
        "CD": 30,
        "DD": 45,
    }
    with pytest.raises(ValueError, match="identifiers"):
        parse(form, original(form))


@pytest.mark.parametrize("form", ["140", "144"])
def test_dated_deductions_preserve_source_codes_separate_controls_and_disclosed_conflict(form):
    result = parse(form)
    row = result["rows"][0]
    m = result["native_metadata"]
    p = m["party_links"][0]
    assert row["legal_role"] == "deductor" and row["tax_kind"] == "TDS"
    assert row["amount"] == ("900.00" if form == "140" else "2000.00")
    assert result["allowed_source_roles"] == ["reported"] and result["allowed_workflows"] == [
        "india-withholding-liability"
    ]
    assert p["numbered_form"] == form and p["recorded_deposited_flag"] == "Y"
    assert (
        "income_tax" not in p
        and m["workbook_version"] == "1.1"
        and m["page_version_at_assessment"] == "1.2"
    )
    assert m["component_controls"]["cash_withdrawal_general"] == "0"
    assert m["challan_controls"][0]["recorded_penalty"] == (
        "100.00" if form == "140" else "1000.00"
    )
    assert (
        m["fvu_validation"] == "NOT_PERFORMED" and m["filing_or_acknowledgment"] == "NOT_EVIDENCED"
    )
    if form == "144":
        assert (
            p["recorded_destination_country"] == "04" and p["recorded_numbered_rate_basis"] == "B"
        )
        assert p["recorded_gross_up_flag"] == "N" and p["certificate_reference"] == "1234567890"


@pytest.mark.parametrize("form", ["140", "144"])
def test_unpaid_prepared_deduction_is_not_falsely_rejected_as_a_zero_tax_observation(form):
    raw = synthetic(form)
    for line, field, value in [(3, 21, "0.00"), (4, 18, "N"), (4, 25, "0.00")]:
        raw = edit(raw, line, field, value)
    c = controls(form)
    c["allocated_deposit"] = "0"
    result = parse(form, raw, numbered_deduction_controls=c)
    assert result["rows"][0]["amount"] == ("900.00" if form == "140" else "2000.00")
    assert result["native_metadata"]["party_links"][0]["allocated_deposit"] == "0.00"
    assert result["native_metadata"]["bank_payment_or_tax_credit"] == "NOT_EVIDENCED"


@pytest.mark.parametrize("form", ["140", "144"])
@pytest.mark.parametrize(
    "line,field,value",
    [
        (1, 3, "TC1"),
        (1, 4, "C"),
        (2, 5, "26Q"),
        (2, 16, "202627"),
        (2, 18, "Q4"),
        (2, 47, "1.00"),
        (3, 4, "2"),
        (3, 5, "2"),
        (3, 6, "Y"),
        (3, 8, "100.50"),
        (3, 17, ""),
        (3, 24, "0.00"),
        (3, 25, "0.00"),
        (4, 4, "2"),
        (4, 5, "2"),
        (4, 6, "C"),
        (4, 8, "badpan"),
        (4, 9, ""),
        (4, 15, "999"),
        (4, 18, ""),
        (4, 18, "N"),
        (4, 19, "01072026"),
        (4, 20, "0.00"),
        (4, 22, "1.00"),
        (4, 27, ""),
        (4, 28, "1.00"),
        (4, 31, "short"),
    ],
)
def test_unknown_layouts_counts_flags_dates_or_controls_are_rejected(form, line, field, value):
    with pytest.raises(ValueError):
        parse(form, edit(synthetic(form), line, field, value))


@pytest.mark.parametrize("form", ["140", "144"])
@pytest.mark.parametrize(
    "field",
    [
        "tax_deducted",
        "allocated_deposit",
        "challan_deposit",
        "payment_base",
        "challan_tax",
        "challan_interest",
        "challan_fee",
        "challan_penalty",
        "allocated_interest",
        "allocated_penalty",
        "cash_withdrawal_general",
        "cash_withdrawal_cooperative",
    ],
)
def test_every_independent_deduction_component_is_controlled(form, field):
    c = controls(form)
    c[field] = "1"
    with pytest.raises(ValueError, match="independent"):
        parse(form, numbered_deduction_controls=c)


@pytest.mark.parametrize(
    "field,value",
    [
        (12, "XX"),
        (14, ""),
        (17, "USA"),
        (21, ""),
        (30, "?"),
        (33, ""),
        (34, "x"),
        (38, "bademail"),
        (39, "abc"),
    ],
)
def test_nonresident_fields_remain_explicit_recorded_claims(field, value):
    with pytest.raises(ValueError):
        parse("144", edit(synthetic("144"), 4, field, value))


@pytest.mark.parametrize("form", ["140", "144"])
@pytest.mark.parametrize(
    "code,field,control",
    [("1065", 22, "cash_withdrawal_general"), ("1064", 23, "cash_withdrawal_cooperative")],
)
def test_cash_code_fields_retain_separate_amounts_and_independent_controls(
    form, code, field, control
):
    raw = edit(edit(synthetic(form), 4, 15, code), 4, field, "123.45")
    c = controls(form)
    c[control] = "123.45"
    result = parse(form, raw, numbered_deduction_controls=c)
    assert result["native_metadata"]["component_controls"][control] == "123.45"
    with pytest.raises(ValueError):
        parse(form, edit(raw, 4, field, ""), numbered_deduction_controls=c)


def test_missing_pan_low_recorded_treaty_rate_does_not_omit_residence_fields_or_imply_eligibility():
    raw = edit(edit(synthetic("144"), 4, 8, "PANNOTAVBL"), 4, 32, "C")
    with pytest.raises(ValueError, match="all four residence"):
        parse("144", raw)
    raw = edit(raw, 4, 41, "SYN-FOREIGN-ID")
    result = parse("144", raw)
    assert (
        result["native_metadata"]["party_links"][0]["recorded_foreign_tax_identifier"]
        == "SYN-FOREIGN-ID"
    )
    assert result["statutory_calculation_qualified"] is False


@pytest.mark.parametrize("form", ["140", "144"])
def test_dated_controls_cannot_be_used_for_another_country_or_source_profile(form):
    with pytest.raises(ValueError):
        parse_native(synthetic(form), options(form), "AE", "source.txt")
    with pytest.raises(ValueError):
        options(form, file_format="india-form143-regular-20260722-v1.1")
    c = controls(form)
    c["tax_year"] = "202728"
    with pytest.raises(ValueError):
        options(form, numbered_deduction_controls=c)


@pytest.mark.parametrize("form", ["140", "144"])
def test_late_deduction_is_retained_after_the_filing_quarter_without_inventing_a_year_mapping(form):
    raw = edit(synthetic(form), 4, 27, "10072026")
    c = controls(form)
    c["groups"][0]["period"] = "2026-07"
    result = parse(form, raw, numbered_deduction_controls=c)
    assert result["rows"][0]["period"] == "2026-07"
    assert result["native_metadata"]["quarter"] == "Q1"
    assert result["native_metadata"]["party_links"][0]["native_tax_date"] == "2026-07-10"
    with pytest.raises(ValueError, match="tax quarter"):
        parse(form, edit(synthetic(form), 4, 27, "31032026"))
    c["observed_on"] = "2027-05-01"
    with pytest.raises(ValueError, match="year mapping"):
        parse(form, edit(synthetic(form), 4, 27, "01042027"), numbered_deduction_controls=c)
    c = controls(form)
    c["batch_count"] = True
    with pytest.raises(ValueError):
        options(form, numbered_deduction_controls=c)
