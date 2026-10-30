"""Historical salary observations reuse the controlled legacy reader, not Q4 annexures."""

import hashlib
from uuid import uuid4

import pytest

from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput
from tests.unit.test_india_withholding_native import ROOT, edit

PROFILE = "india-24q-regular-q1q3-v6.3"


def original24():
    return (ROOT / "protean-24Q-Q3-original-sample.txt").read_bytes()


def controls24():
    return {
        "tan": "MUMN77777A",
        "financial_year": "201819",
        "quarter": "Q3",
        "observed_on": "2026-10-31",
        "batch_count": 1,
        "challan_count": 1,
        "party_count": 1,
        "income_tax": "1000",
        "surcharge": "0",
        "cess": "0",
        "allocated_deposit": "1000",
        "challan_deposit": "1000",
        "payment_base": "10000",
        "record_status": "current",
        "crosswalk_document_version_id": str(uuid4()),
        "assessment": "SYNTHETIC independent controls and transaction crosswalk for the unchanged public salary sample; no client or filing qualification",
        "groups": [
            {
                "transaction_reference": "SYN-SALARY-LEGACY-1",
                "transaction_date": "2018-12-16",
                "period": "2018-12",
                "rule_reference": "SYN-ASSESSED-SALARY-LEGACY",
                "party_records": ["1/1/1"],
            }
        ],
    }


def options24(**changes):
    return SourceInput.model_validate(
        {
            "file_format": PROFILE,
            "evidence_version_id": str(uuid4()),
            "table_type": "withholding-records",
            "label": "SYNTHETIC historical salary controls",
            "expected_rows": 1,
            "control_totals": {"INR": "1000"},
            "native_withholding_controls": controls24(),
            **changes,
        }
    )


def parse(raw=None, **changes):
    return parse_native(
        raw if raw is not None else original24(), options24(**changes), "IN", "public-24q.txt"
    )


def test_unchanged_original_salary_sample_retains_components_dates_and_no_invented_rate():
    result = parse()
    assert result["allowed_source_roles"] == ["reported"]
    assert result["allowed_workflows"] == ["india-withholding-liability"]
    assert result["control_totals"] == {"INR": "1000.00"}
    assert result["rows"][0]["tax_kind"] == "TDS"
    m = result["native_metadata"]
    assert m["form"] == "24Q" and m["financial_year"] == "201819"
    assert (
        m["layout_specification_sha256"]
        == "669d4f4395dd0a9f55a195e62bf5896f63520c84d2ef042432db22789eee5062"
    )
    link = m["party_links"][0]
    assert link["recorded_deposit_date"] == "2018-12-14"
    assert link["native_tax_date"] == "2018-12-16"
    assert "recorded_rate" not in link
    assert link["income_tax"] == "1000.00" and link["surcharge"] == link["cess"] == "0.00"
    assert link["certificate_reference"] == "748596klop"
    assert (
        m["fvu_validation"] == "NOT_PERFORMED"
        and m["bank_payment_or_tax_credit"] == "NOT_EVIDENCED"
    )
    assert (
        hashlib.sha256((ROOT / "protean-24Q-Q1Q3-6.3.xls").read_bytes()).hexdigest()
        == m["layout_specification_sha256"]
    )


@pytest.mark.parametrize(
    "line,field,value,reason",
    [
        (1, 3, "NS1", "type"),
        (1, 4, "C", "regular"),
        (2, 5, "26Q", "form"),
        (2, 16, "202627", "year"),
        (2, 17, "202627", "year"),
        (2, 18, "Q4", "quarter"),
        (2, 4, "2", "count"),
        (2, 47, "900.00", "deposit"),
        (3, 4, "2", "identity"),
        (3, 5, "2", "count"),
        (3, 6, "Y", "Nil"),
        (3, 27, "900.00", "gross"),
        (3, 29, "900.00", "control"),
        (4, 4, "2", "challan"),
        (4, 5, "2", "identity"),
        (4, 7, "employee", "reference"),
        (4, 10, "badpan", "PAN"),
        (4, 14, "900.00", "tax"),
        (4, 23, "16122019", "quarter"),
        (4, 24, "", "positive"),
        (4, 25, "", "ddmmyyyy"),
        (4, 25, "31022018", "calendar"),
        (4, 26, "0.0000", "width"),
        (4, 33, "194", "salary"),
    ],
)
def test_salary_layout_and_population_fail_closed(line, field, value, reason):
    with pytest.raises(ValueError, match=reason):
        parse(edit(original24(), line, field, value))


@pytest.mark.parametrize(
    "field",
    ["income_tax", "surcharge", "cess", "allocated_deposit", "challan_deposit", "payment_base"],
)
def test_every_independent_salary_amount_control_is_enforced(field):
    declared = controls24()
    declared[field] = "1"
    with pytest.raises(ValueError, match="Independent"):
        parse(native_withholding_controls=declared)


def test_q4_annual_records_are_not_truncated_to_a_quarterly_salary_import():
    declared = controls24()
    declared["quarter"] = "Q4"
    with pytest.raises(ValueError, match="annual salary"):
        parse(native_withholding_controls=declared)
    with pytest.raises(ValueError, match="field count"):
        parse((ROOT / "protean-24Q-Q4-original-sample.txt").read_bytes())


def test_new_salary_form_and_foreign_country_cannot_use_the_historical_layout():
    with pytest.raises(ValueError):
        parse(file_format="india-form138-regular-20260722-v1.1")
    with pytest.raises(ValueError):
        parse_native(original24(), options24(), "AE", "public-24q.txt")


def test_native_zero_and_explicit_missing_pan_remain_observations():
    raw = original24()
    for line, field, value in [
        (4, 10, "PANNOTAVBL"),
        (4, 14, "0.00"),
        (4, 17, "0.00"),
        (4, 19, "0.00"),
        (4, 24, ""),
    ]:
        raw = edit(raw, line, field, value)
    for field in (29, 30, 33):
        raw = edit(raw, 3, field, "0.00")
    declared = controls24()
    declared.update(income_tax="0", allocated_deposit="0")
    result = parse(raw, native_withholding_controls=declared, control_totals={"INR": "0"})
    assert result["rows"][0]["counterparty"] == "PANNOTAVBL"
    assert result["rows"][0]["amount"] == "0.00"


@pytest.mark.parametrize("missing_pan", [False, True])
def test_salary_crosswalk_does_not_merge_distinct_employee_or_missing_pan_records(missing_pan):
    records = [line.decode().split("^") for line in original24().splitlines()]
    records[1][46] = "2000.00"
    records[2][4] = "2"
    for position in (21, 26, 28, 29, 32):
        records[2][position] = "2000.00"
    second = list(records[3])
    second[0], second[4] = "5", "2"
    records[3][6], second[6] = ("", "") if missing_pan else ("1", "2")
    if missing_pan:
        records[3][9] = second[9] = "PANNOTAVBL"
    records.append(second)
    raw = ("\r\n".join("^".join(row) for row in records) + "\r\n").encode()
    declared = controls24()
    declared.update(
        party_count=2,
        income_tax="2000",
        allocated_deposit="2000",
        challan_deposit="2000",
        payment_base="20000",
    )
    declared["groups"][0]["party_records"] = ["1/1/1", "1/1/2"]
    with pytest.raises(ValueError, match="Missing-PAN" if missing_pan else "employee references"):
        parse(raw, native_withholding_controls=declared, control_totals={"INR": "2000"})
    first = {**declared["groups"][0], "party_records": ["1/1/1"]}
    declared["groups"] = [
        first,
        {**first, "transaction_reference": "SYN-SALARY-LEGACY-2", "party_records": ["1/1/2"]},
    ]
    assert (
        parse(
            raw,
            expected_rows=2,
            native_withholding_controls=declared,
            control_totals={"INR": "2000"},
        )["row_count"]
        == 2
    )
