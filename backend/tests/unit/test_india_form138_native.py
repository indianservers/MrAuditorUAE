"""Salary observations preserve issuer originals and distinguish synthetic completions."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.country_workflows.india_form138_native import PROFILE, SPEC_SHA256
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput
from tests.unit.test_india_withholding_native import edit

ROOT = (
    Path(__file__).resolve().parents[3]
    / "docs/country-workflows/authority-references/form138-2026-07-22"
)


def original138():
    return (ROOT / "protean-form138-original-sample.txt").read_bytes()


def synthetic138():
    raw = original138()
    for line, field, value in [
        (2, 16, "202728"),
        (2, 17, "202627"),
        (3, 17, "00001"),
        (3, 19, "09052026"),
        (3, 24, "1000.00"),
        (3, 25, "100.00"),
        (4, 18, "Y"),
        (4, 19, "06052026"),
        (4, 27, "06052026"),
        (4, 29, "09052026"),
        (5, 18, "Y"),
        (5, 19, "06052026"),
        (5, 27, "06052026"),
        (5, 29, "09052026"),
    ]:
        raw = edit(raw, line, field, value)
    return raw


def controls138():
    return {
        "tax_year": "202627",
        "tan": "BLRF02329F",
        "quarter": "Q1",
        "observed_on": "2026-10-31",
        "date_width_assessment": "DD29_EIGHT_DIGIT_DATE_PER_NUMBERED_REMARKS",
        "batch_count": 1,
        "challan_count": 1,
        "party_count": 2,
        "tax_deducted": "4000",
        "allocated_deposit": "4000",
        "challan_deposit": "24100",
        "payment_base": "4200",
        "challan_tax": "22000",
        "challan_interest": "1000",
        "challan_fee": "1000",
        "challan_penalty": "100",
        "allocated_interest": "1000",
        "allocated_penalty": "100",
        "record_status": "current",
        "crosswalk_document_version_id": str(uuid4()),
        "assessment": "SYNTHETIC separate controls and explicitly assessed source year, version and DD29 size/notes conflict; no issuer qualification",
        "groups": [
            {
                "transaction_reference": f"SYN-SALARY-{i}",
                "transaction_date": "2026-05-06",
                "period": "2026-05",
                "rule_reference": "SYN-ASSESSED-SALARY",
                "party_records": [f"1/1/{i}"],
            }
            for i in (1, 2)
        ],
    }


def options138(**changes):
    return SourceInput.model_validate(
        {
            "file_format": PROFILE,
            "evidence_version_id": str(uuid4()),
            "table_type": "withholding-records",
            "label": "SYNTHETIC dated salary observations",
            "expected_rows": 2,
            "control_totals": {"INR": "4000"},
            "form138_controls": controls138(),
            **changes,
        }
    )


def parse(raw=None, **changes):
    return parse_native(
        raw if raw is not None else synthetic138(), options138(**changes), "IN", "SYNTHETIC-138.txt"
    )


def test_original_workbook_and_sample_are_retained_exactly():
    assert (
        hashlib.sha256((ROOT / "protean-form138-22072026.xlsx").read_bytes()).hexdigest()
        == SPEC_SHA256
    )
    assert (
        hashlib.sha256(original138()).hexdigest()
        == "3cd9ca7ff46668bcdd102db133959380f39b765c3e0b15448b1fe6a5cb43eb4e"
    )
    with pytest.raises(ValueError, match="year"):
        parse(original138())


def test_salary_observations_reuse_the_reported_only_withholding_contract():
    result = parse()
    assert result["allowed_source_roles"] == ["reported"]
    assert result["allowed_workflows"] == ["india-withholding-liability"]
    assert result["control_totals"] == {"INR": "4000.00"}
    assert [(r["legal_role"], r["tax_kind"], r["amount"]) for r in result["rows"]] == [
        ("deductor", "TDS", "2000.00")
    ] * 2
    meta = result["native_metadata"]
    assert meta["date_width_conflict"]["numbered_size"] == 7
    assert meta["date_width_conflict"]["adopted_observation_width"] == 8
    assert [r["recorded_deposit_date"] for r in meta["party_links"]] == ["2026-05-09"] * 2
    assert meta["challan_controls"][0]["recorded_penalty"] == "100.00"
    assert meta["fvu_validation"] == "NOT_PERFORMED"
    assert meta["bank_payment_or_tax_credit"] == "NOT_EVIDENCED"
    assert meta["source_sha256"] == hashlib.sha256(synthetic138()).hexdigest()


@pytest.mark.parametrize(
    "line,field,value,reason",
    [
        (1, 3, "NS1", "salary"),
        (1, 4, "C", "salary"),
        (1, 7, "I", "salary"),
        (2, 5, "24Q", "batch"),
        (2, 16, "202627", "year"),
        (2, 17, "202526", "year"),
        (2, 18, "Q4", "quarter"),
        (2, 4, "2", "counts"),
        (2, 47, "24000.00", "gross"),
        (3, 4, "2", "distinct"),
        (3, 6, "Y", "non-nil"),
        (3, 13, "X", "payment"),
        (3, 15, "123", "identifiers"),
        (3, 17, "", "identifiers"),
        (3, 24, "0.00", "allocations"),
        (3, 25, "0.00", "allocations"),
        (3, 8, "22000.10", "whole"),
        (3, 12, "24000.00", "gross"),
        (3, 5, "1", "counts"),
        (3, 21, "3999.00", "allocations"),
        (3, 22, "3999.00", "allocations"),
        (4, 5, "2", "challan reference"),
        (4, 6, "C", "correction"),
        (4, 8, "badpan", "PAN"),
        (4, 15, "9999", "salary code"),
        (4, 18, "", "deposited"),
        (4, 18, "N", "contradict"),
        (4, 19, "06052025", "quarter"),
        (4, 20, "0.00", "base"),
        (4, 24, "2000", "two-decimal"),
        (4, 25, "1999.00", "contradict"),
        (4, 27, "", "dates"),
        (4, 29, "0905202", "ddmmyyyy"),
        (4, 29, "31022026", "calendar"),
        (4, 29, "01052026", "precedes"),
        (4, 29, "09112026", "cutoff"),
        (4, 32, "B", "reason"),
        (4, 33, "bad", "certificate"),
        (4, 28, "9.0000", "width"),
        (5, 4, "1", "Duplicate"),
    ],
)
def test_conflicted_or_inconsistent_observations_fail_closed(line, field, value, reason):
    with pytest.raises(ValueError, match=reason):
        parse(edit(synthetic138(), line, field, value))


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
    ],
)
def test_each_independent_amount_control_is_enforced(field):
    controls = controls138()
    controls[field] = "1"
    with pytest.raises(ValueError, match="independent"):
        parse(form138_controls=controls)


def test_q4_and_unassessed_date_interpretation_are_not_accepted():
    for change in [
        {"quarter": "Q4"},
        {"date_width_assessment": ""},
        {"tax_year": "202728"},
        {"batch_count": True},
    ]:
        controls = controls138()
        controls.update(change)
        with pytest.raises(ValueError):
            options138(form138_controls=controls)


def test_other_native_formats_cannot_take_salary_controls():
    with pytest.raises(ValueError):
        options138(file_format="india-form143-regular-20260722-v1.1")
    with pytest.raises(ValueError):
        options138(form138_controls=None)
    with pytest.raises(ValueError):
        parse_native(synthetic138(), options138(), "AE", "salary.txt")


def test_crosswalk_does_not_merge_different_employee_or_section_contexts():
    controls = controls138()
    controls["groups"] = [{**controls["groups"][0], "party_records": ["1/1/1", "1/1/2"]}]
    with pytest.raises(ValueError, match="cannot merge"):
        parse(expected_rows=1, form138_controls=controls)
    controls = controls138()
    controls["groups"][1]["party_records"] = ["1/1/3"]
    with pytest.raises(ValueError, match="identities"):
        parse(form138_controls=controls)


def test_layout_pins_only_the_dated_source_and_declares_all_four_widths():
    selected = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "app/modules/country_workflows/india_form138_layout.json"
        ).read_text()
    )
    assert selected["source_sha256"] == SPEC_SHA256
    assert {k: len(v) for k, v in selected["field_lengths"].items()} == {
        "FH": 18,
        "BH": 72,
        "CD": 30,
        "DD": 45,
    }
    assert selected["workbook_version"] == "1.1" and selected["page_version_at_inspection"] == "1.2"


@pytest.mark.parametrize("quarter,month", [("Q2", "08"), ("Q3", "11")])
def test_other_supported_quarters_require_their_actual_employee_dates(quarter, month):
    raw = synthetic138()
    for line in (4, 5):
        for field, day in ((19, "06"), (27, "06"), (29, "09")):
            raw = edit(raw, line, field, day + month + "2026")
    raw = edit(raw, 2, 18, quarter)
    declared = controls138()
    declared.update(quarter=quarter, observed_on="2027-01-01")
    for group in declared["groups"]:
        group.update(period=f"2026-{month}", transaction_date=f"2026-{month}-06")
    assert parse(raw, form138_controls=declared)["rows"][0]["period"] == f"2026-{month}"


def test_zero_deduction_preserves_a_real_zero_and_requires_absent_tax_dates():
    raw = synthetic138()
    for line in (4, 5):
        for field, value in ((18, "N"), (24, "0.00"), (25, "0.00"), (27, ""), (29, "")):
            raw = edit(raw, line, field, value)
    for field in (21, 22):
        raw = edit(raw, 3, field, "0.00")
    declared = controls138()
    declared.update(tax_deducted="0", allocated_deposit="0")
    result = parse(raw, form138_controls=declared, control_totals={"INR": "0"})
    assert all(row["amount"] == "0.00" for row in result["rows"])
    assert result["native_metadata"]["party_links"][0]["recorded_deposit_date"] is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.rstrip(),
        lambda b: b.replace(b"\r\n", b"\n"),
        lambda b: b"\xef\xbb\xbf" + b,
        lambda b: b + b"\r\n",
        lambda b: b.replace(b"ABCD", b"AB\tD"),
    ],
)
def test_original_encoding_and_record_boundaries_are_not_repaired(mutate):
    with pytest.raises(ValueError):
        parse(mutate(synthetic138()))
