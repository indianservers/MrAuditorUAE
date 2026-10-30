"""Explicit synthetic completions never replace the unchanged incomplete public sample."""

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.country_workflows.india_form143_native import PROFILE, SPEC_SHA256, layout
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput
from tests.unit.test_india_withholding_native import edit

ROOT = (
    Path(__file__).resolve().parents[3]
    / "docs/country-workflows/authority-references/form143-2026-07-22"
)


def original143():
    return (ROOT / "protean-form143-original-sample.txt").read_bytes()


def synthetic143():
    raw = original143()
    for line, field, value in [
        (3, 17, "00001"),
        (3, 24, "1000.00"),
        (3, 25, "1000.00"),
        (4, 18, "Y"),
    ]:
        raw = edit(raw, line, field, value)
    return raw


def controls143():
    return {
        "tax_year": "202627",
        "tan": "BLRF02329F",
        "quarter": "Q1",
        "observed_on": "2026-10-30",
        "batch_count": 1,
        "challan_count": 1,
        "party_count": 1,
        "tax_collected": "700",
        "allocated_deposit": "700",
        "challan_deposit": "213000",
        "payment_base": "21000",
        "challan_tax": "210000",
        "challan_interest": "1000",
        "challan_fee": "1000",
        "challan_other": "1000",
        "allocated_interest": "1000",
        "allocated_other": "1000",
        "record_status": "current",
        "crosswalk_document_version_id": str(uuid4()),
        "assessment": "SYNTHETIC explicit completion of missing source fields and independently assessed counts and crosswalk; no issuer, client or legal qualification",
        "groups": [
            {
                "transaction_reference": "SYN-ASSESSMENT-1",
                "transaction_date": "2026-05-01",
                "period": "2026-05",
                "rule_reference": "SYN-ASSESSED-SECTION",
                "party_records": ["1/1/1"],
            }
        ],
    }


def options143(**changes):
    return SourceInput.model_validate(
        {
            "file_format": PROFILE,
            "evidence_version_id": str(uuid4()),
            "table_type": "withholding-records",
            "label": "SYNTHETIC dated Form 143 observations; original public sample remains unchanged",
            "expected_rows": 1,
            "control_totals": {"INR": "700"},
            "form143_controls": controls143(),
            **changes,
        }
    )


def test_incomplete_original_public_sample_is_never_repaired_or_qualified_implicitly():
    with pytest.raises(ValueError, match="identifiers"):
        parse_native(original143(), options143(), "IN", "original-public-143.txt")


def test_dated_numbered_layout_is_bound_to_the_exact_retained_original_workbook():
    assert (
        hashlib.sha256((ROOT / "protean-form143-22072026.xlsx").read_bytes()).hexdigest()
        == SPEC_SHA256
    )
    selected, _ = layout()
    assert selected["workbook_version"] == "1.1" and selected["page_version_at_inspection"] == "1.2"
    assert {k: len(v) for k, v in selected["field_lengths"].items()} == {
        "FH": 18,
        "BH": 72,
        "CD": 30,
        "DD": 45,
    }


def test_multiple_collectees_and_challans_preserve_the_new_party_reference_order():
    rows = [r.decode().split("^") for r in synthetic143().splitlines()]
    rows[1][3] = "2"
    rows[1][46] = "426000.00"
    rows[2][4] = "2"
    rows[2][20] = rows[2][21] = "1400.00"
    second = list(rows[3])
    second[3] = "2"
    challan = list(rows[2])
    challan[3] = "2"
    challan[4] = "1"
    challan[20] = challan[21] = "700.00"
    third = list(rows[3])
    third[3] = "3"
    third[4] = "2"
    rows += [second, challan, third]
    for i, r in enumerate(rows, 1):
        r[0] = str(i)
    content = ("\r\n".join("^".join(r) for r in rows) + "\r\n").encode()
    declared = controls143()
    declared.update(
        challan_count=2,
        party_count=3,
        tax_collected="2100",
        allocated_deposit="2100",
        payment_base="63000",
        challan_deposit="426000",
        challan_tax="420000",
        challan_interest="2000",
        challan_fee="2000",
        challan_other="2000",
        allocated_interest="2000",
        allocated_other="2000",
    )
    declared["groups"] = [
        {
            **declared["groups"][0],
            "transaction_reference": f"SYN-ASSESSMENT-{i}",
            "party_records": [key],
        }
        for i, key in enumerate(["1/1/1", "1/1/2", "1/2/3"], 1)
    ]
    data = options143(expected_rows=3, control_totals={"INR": "2100"}, form143_controls=declared)
    result = parse_native(content, data, "IN", "SYNTHETIC-multiple-collectees.txt")
    assert [r["party_key"] for r in result["native_metadata"]["party_links"]] == [
        "1/1/1",
        "1/1/2",
        "1/2/3",
    ]
    assert len(result["native_metadata"]["challan_controls"]) == 2
    # Swapping DD party number and challan reference must not inherit the
    # legacy DD layout merely because both fields were 1 in the public sample.
    with pytest.raises(ValueError, match="challan reference"):
        parse_native(edit(content, 7, 5, "3"), data, "IN", "SYNTHETIC-wrong-reference.txt")


@pytest.mark.parametrize(
    "quarter,day",
    [("Q1", "2026-04-10"), ("Q2", "2026-07-10"), ("Q3", "2026-10-10"), ("Q4", "2027-01-10")],
)
def test_each_declared_tax_quarter_preserves_the_tax_year_boundary(quarter, day):
    from datetime import date

    raw = synthetic143()
    printed = date.fromisoformat(day).strftime("%d%m%Y")
    for line, field, value in [
        (1, 5, "02042027"),
        (2, 18, quarter),
        (3, 19, printed),
        (4, 19, printed),
        (4, 27, printed),
    ]:
        raw = edit(raw, line, field, value)
    declared = controls143()
    declared.update(quarter=quarter, observed_on="2027-04-02")
    declared["groups"][0].update(transaction_date=day, period=day[:7])
    data = options143(form143_controls=declared)
    result = parse_native(raw, data, "IN", "SYNTHETIC-quarter-boundary.txt")
    assert result["rows"][0]["period"] == day[:7]
    assert (
        result["rows"][0]["tax_year_start"] == "2026-04-01"
        and result["rows"][0]["tax_year_end"] == "2027-03-31"
    )
    if quarter == "Q4":
        with pytest.raises(ValueError, match="tax quarter"):
            parse_native(edit(raw, 4, 27, "10012026"), data, "IN", "SYNTHETIC-wrong-q4-year.txt")


def test_explicit_synthetic_completion_preserves_different_prepared_amounts_and_source_conflict():
    result = parse_native(synthetic143(), options143(), "IN", "SYNTHETIC-explicit-completion.txt")
    assert result["row_count"] == 1 and result["control_totals"] == {"INR": "700.00"}
    assert result["allowed_source_roles"] == ["reported"]
    assert result["allowed_workflows"] == ["india-withholding-liability"]
    row = result["rows"][0]
    assert (
        row["legal_role"] == "collector"
        and row["tax_kind"] == "TCS"
        and row["payment_date"] is None
    )
    assert row["tax_year_start"] == "2026-04-01" and row["tax_year_end"] == "2027-03-31"
    m = result["native_metadata"]
    assert m["workbook_version"] == "1.1" and m["page_version_at_assessment"] == "1.2"
    assert m["filing_or_acknowledgment"] == m["bank_payment_or_tax_credit"] == "NOT_EVIDENCED"
    assert (
        m["fvu_validation"] == "NOT_PERFORMED"
        and result["statutory_calculation_qualified"] is False
    )
    c = m["challan_controls"][0]
    assert (
        c["recorded_payment_mode"] == "B"
        and c["ddo_serial"] == "00001"
        and c["challan_number"] == ""
    )
    assert (
        c["recorded_tax"] == "210000.00"
        and c["gross_deposit"] == "213000.00"
        and c["allocated_deposit"] == "700.00"
    )
    p = m["party_links"][0]
    assert p["total_tax"] == "700.00" and p["reason_flag"] == "B"
    assert (
        p["recorded_deposited_flag"] == "Y"
        and p["recorded_nonresident_flag"] == "Y"
        and p["recorded_pe_flag"] == "N"
    )
    assert p["certificate_reference"] == "" and "income_tax" not in p


@pytest.mark.parametrize("deposited_flag", ["Y", "N"])
def test_explicit_zero_tax_preserves_flags_and_receipt_base_without_inventing_exemption_or_payment(
    deposited_flag,
):
    raw = synthetic143()
    for line, field, value in [
        (3, 21, "0.00"),
        (3, 22, "0.00"),
        (4, 18, deposited_flag),
        (4, 24, "0.00"),
        (4, 25, "0.00"),
        (4, 27, ""),
        (4, 28, "0.0000"),
    ]:
        raw = edit(raw, line, field, value)
    declared = {**controls143(), "tax_collected": "0", "allocated_deposit": "0"}
    data = options143(control_totals={"INR": "0"}, form143_controls=declared)
    result = parse_native(raw, data, "IN", "SYNTHETIC-explicit-zero-tax.txt")
    assert result["rows"][0]["amount"] == "0.00"
    assert result["rows"][0]["payment_date"] is None
    assert result["native_metadata"]["party_links"][0]["recorded_deposited_flag"] == deposited_flag
    assert result["native_metadata"]["component_controls"]["payment_base"] == "21000.00"
    assert result["native_metadata"]["component_controls"]["challan_deposit"] == "213000.00"
    with pytest.raises(ValueError, match="zero rate"):
        parse_native(edit(raw, 4, 28, "1.0000"), data, "IN", "SYNTHETIC-invalid-zero-rate.txt")


@pytest.mark.parametrize("country", ["AE", "GB"])
def test_form143_is_not_a_domestic_other_country_rule(country):
    with pytest.raises(ValueError, match="unavailable"):
        parse_native(synthetic143(), options143(), country, "synthetic.txt")


@pytest.mark.parametrize(
    "line,field,value",
    [
        (1, 3, "NS1"),
        (1, 4, "C"),
        (1, 8, "MUMN77777A"),
        (1, 9, "2"),
        (2, 5, "27EQ"),
        (2, 16, "202627"),
        (2, 17, "202728"),
        (2, 18, "Q2"),
        (2, 47, "1.00"),
        (3, 4, "2"),
        (3, 5, "2"),
        (3, 6, "Y"),
        (3, 8, "210000.01"),
        (3, 12, "212000.00"),
        (3, 13, ""),
        (3, 13, "N"),
        (3, 15, "50000320"),
        (3, 17, ""),
        (3, 19, "31022026"),
        (3, 21, "701.00"),
        (3, 22, "701.00"),
        (3, 24, ""),
        (3, 25, ""),
        (3, 24, "999.00"),
        (3, 25, "999.00"),
        (4, 4, "0"),
        (4, 5, "2"),
        (4, 6, "C"),
        (4, 11, ""),
        (4, 13, ""),
        (4, 14, ""),
        (4, 15, "107"),
        (4, 18, ""),
        (4, 18, "N"),
        (4, 19, "01072026"),
        (4, 20, "0.00"),
        (4, 24, "701.00"),
        (4, 27, ""),
        (4, 28, "1.00"),
        (4, 34, "?"),
    ],
)
def test_form143_rejects_unknown_flags_missing_amounts_mixed_layouts_or_inconsistent_controls(
    line, field, value
):
    with pytest.raises(ValueError):
        parse_native(
            edit(synthetic143(), line, field, value), options143(), "IN", "synthetic-altered.txt"
        )


@pytest.mark.parametrize(
    "field",
    [
        "tax_collected",
        "allocated_deposit",
        "challan_deposit",
        "payment_base",
        "challan_tax",
        "challan_interest",
        "challan_fee",
        "challan_other",
        "allocated_interest",
        "allocated_other",
    ],
)
def test_each_independent_component_control_is_required_and_checked(field):
    controls = controls143()
    del controls[field]
    with pytest.raises(ValueError):
        options143(form143_controls=controls)
    controls = {**controls143(), field: "1"}
    with pytest.raises(ValueError, match="independent"):
        parse_native(synthetic143(), options143(form143_controls=controls), "IN", "synthetic.txt")


@pytest.mark.parametrize(
    "changes",
    [
        {"tax_year": "202526"},
        {"tax_year": "202728"},
        {"batch_count": True},
        {"batch_count": "1"},
        {"party_count": True},
        {"quarter": "Q5"},
    ],
)
def test_successor_controls_cannot_relax_the_dated_year_or_strict_population(changes):
    with pytest.raises(ValueError):
        options143(form143_controls={**controls143(), **changes})


@pytest.mark.parametrize("status", ["superseded", "cancelled"])
def test_history_retains_source_amounts_and_never_creates_zero_current_observations(status):
    result = parse_native(
        synthetic143(),
        options143(form143_controls={**controls143(), "record_status": status}),
        "IN",
        "history.txt",
    )
    assert result["rows"][0]["record_status"] == status and result["rows"][0]["amount"] == "700.00"
