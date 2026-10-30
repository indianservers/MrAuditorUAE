"""Public issuer sample structure plus synthetic assessed mappings; not filing qualification."""

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.india_withholding_native import profile_limits
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput

ROOT = (
    Path(__file__).resolve().parents[3]
    / "docs/country-workflows/authority-references/protean-legacy-2025-05-27"
)


def original(form="26Q"):
    return (ROOT / f"protean-{form}-original-sample.txt").read_bytes()


def controls(form="26Q"):
    count = 4 if form == "26Q" else 10
    return {
        "tan": "MUMN77777A",
        "financial_year": "202021",
        "quarter": "Q1" if form == "26Q" else "Q3",
        "observed_on": "2026-10-30",
        "batch_count": 1,
        "challan_count": 1,
        "party_count": count,
        "income_tax": "1900" if form == "26Q" else "1000",
        "surcharge": "0",
        "cess": "0",
        "allocated_deposit": "1900" if form == "26Q" else "1000",
        "challan_deposit": "100000" if form == "26Q" else "10000",
        "payment_base": "19000" if form == "26Q" else "10000",
        **({"purchase_value": "10000"} if form == "27EQ" else {}),
        "record_status": "current",
        "crosswalk_document_version_id": str(uuid4()),
        "assessment": "SYNTHETIC independent public-sample transaction crosswalk and arithmetic controls; not legal or client qualification",
        "groups": [
            {
                "transaction_reference": f"SYN-ASSESSMENT-{i}",
                "transaction_date": "2020-04-01" if form == "26Q" else "2020-10-01",
                "period": "2020-04" if form == "26Q" else "2020-10",
                "rule_reference": "SYN-ASSESSED-SECTION",
                "party_records": [f"1/1/{i}"],
            }
            for i in range(1, count + 1)
        ],
    }


def options(form="26Q", **changes):
    return SourceInput.model_validate(
        {
            "file_format": "india-26q-regular-v7.8" if form == "26Q" else "india-27eq-regular-v6.9",
            "evidence_version_id": str(uuid4()),
            "table_type": "withholding-records",
            "label": "SYNTHETIC public native statement assessment",
            "expected_rows": 4 if form == "26Q" else 10,
            "control_totals": {"INR": "1900" if form == "26Q" else "1000"},
            "native_withholding_controls": controls(form),
            **changes,
        }
    )


@pytest.mark.parametrize("form", ["26Q", "27EQ"])
def test_public_sample_complete_counts_totals_and_reported_only_observations(form):
    result = parse_native(original(form), options(form), "IN", "original.txt")
    assert result["row_count"] == (4 if form == "26Q" else 10)
    assert result["allowed_source_roles"] == ["reported"]
    assert result["allowed_workflows"] == ["india-withholding-liability"]
    assert (
        result["review_status"] == "UNVERIFIED"
        and result["statutory_calculation_qualified"] is False
    )
    assert result["native_metadata"]["filing_or_acknowledgment"] == "NOT_EVIDENCED"
    assert result["native_metadata"]["bank_payment_or_tax_credit"] == "NOT_EVIDENCED"
    assert result["native_metadata"]["fvu_validation"] == "NOT_PERFORMED"
    assert len(result["native_metadata"]["party_links"]) == result["row_count"]
    assert result["rows"][0]["legal_role"] == ("deductor" if form == "26Q" else "collector")
    assert all(r["payment_date"] is None for r in result["rows"])


@pytest.mark.parametrize("country", ["AE", "GB"])
def test_legacy_india_statement_profile_is_not_a_domestic_other_country_rule(country):
    with pytest.raises(ValueError, match="unavailable"):
        parse_native(original(), options(), country, "original.txt")


def edit(content, line, field, value):
    records = [row.decode().split("^") for row in content.splitlines()]
    records[line - 1][field - 1] = value
    return ("\r\n".join("^".join(row) for row in records) + "\r\n").encode()


@pytest.mark.parametrize(
    "line,field,value",
    [
        (1, 2, "UNKNOWN"),
        (1, 3, "TC1"),
        (1, 4, "C"),
        (1, 8, "MUMN88888B"),
        (1, 9, "2"),
        (2, 3, "2"),
        (2, 4, "2"),
        (2, 5, "140"),
        (2, 13, "MUMN88888B"),
        (2, 16, "202223"),
        (2, 17, "202627"),
        (2, 18, "Q2"),
        (2, 47, "99999.00"),
        (3, 3, "2"),
        (3, 4, "2"),
        (3, 5, "5"),
        (3, 22, "100001.00"),
        (3, 27, "99999.00"),
        (3, 29, "1899.00"),
        (3, 30, "1899.00"),
        (3, 33, "1899.00"),
        (4, 1, "5"),
        (4, 3, "2"),
        (4, 4, "2"),
        (4, 5, "2"),
        (4, 6, "A"),
        (4, 10, "UNKNOWN"),
        (4, 14, "-1.00"),
        (4, 17, "1001.00"),
        (4, 19, "1001.00"),
        (4, 22, "10000.01"),
        (4, 23, "31022020"),
        (4, 24, "01072020"),
        (4, 26, "10.00"),
        (4, 33, ""),
    ],
)
def test_changed_structure_dates_counts_money_or_identity_never_partially_import(
    line, field, value
):
    with pytest.raises(ValueError):
        parse_native(edit(original(), line, field, value), options(), "IN", "mutated.txt")


@pytest.mark.parametrize(
    "field",
    [
        "batch_count",
        "challan_count",
        "income_tax",
        "surcharge",
        "cess",
        "allocated_deposit",
        "challan_deposit",
        "payment_base",
    ],
)
def test_independent_native_counts_and_component_controls_are_enforced(field):
    declared = controls()
    declared[field] = int(declared[field]) + 1
    with pytest.raises(ValueError):
        parse_native(
            original(), options(native_withholding_controls=declared), "IN", "original.txt"
        )


@pytest.mark.parametrize(
    "change",
    [
        {"native_withholding_controls": None},
        {"control_totals": {"AED": "1900"}},
        {"expected_rows": 3},
        {"file_format": "canonical-csv"},
        {"table_type": "transactions"},
    ],
)
def test_selected_profile_requires_explicit_complete_mapping_and_inr_controls(change):
    with pytest.raises(ValueError):
        options(**change)


@pytest.mark.parametrize(
    "field,value",
    [
        ("batch_count", True),
        ("party_count", 0),
        ("financial_year", "202627"),
        ("financial_year", "202022"),
        ("assessment", "          "),
        ("crosswalk_document_version_id", None),
        ("record_status", ""),
    ],
)
def test_no_implicit_zero_currentness_or_successor_form_coercion(field, value):
    declared = controls()
    declared[field] = value
    with pytest.raises(ValueError):
        options(native_withholding_controls=declared)


def test_overlapping_and_uncovered_crosswalk_keys_are_rejected():
    declared = controls()
    declared["groups"][1]["party_records"] = ["1/1/1"]
    with pytest.raises(ValueError):
        options(native_withholding_controls=declared)
    declared = controls()
    declared["groups"][1]["party_records"] = ["1/1/99"]
    with pytest.raises(ValueError, match="cover every"):
        parse_native(
            original(), options(native_withholding_controls=declared), "IN", "original.txt"
        )


def test_explicit_many_party_group_preserves_tax_and_complete_original_lineage():
    content = edit(original(), 5, 33, "BA1")
    declared = controls()
    declared["groups"][0]["party_records"].append("1/1/2")
    declared["groups"].pop(1)
    result = parse_native(
        content,
        options(native_withholding_controls=declared, expected_rows=3),
        "IN",
        "synthetic-grouped.txt",
    )
    assert result["rows"][0]["amount"] == "1500.00"
    assert result["rows"][0]["native_party_count"] == 2
    assert len(result["native_metadata"]["party_links"]) == 4
    assert result["control_totals"] == {"INR": "1900.00"}


def test_incompatible_group_never_merges_native_section_codes_or_reporting_months():
    declared = controls()
    declared["groups"][0]["party_records"].append("1/1/2")
    declared["groups"].pop(1)
    with pytest.raises(ValueError, match="one PAN"):
        parse_native(
            original(),
            options(native_withholding_controls=declared, expected_rows=3),
            "IN",
            "original.txt",
        )


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"\r\n",
        b"\xef\xbb\xbf" + original(),
        original().replace(b"\r\n", b"\n"),
        original() + b"\r\n",
        original().replace(b"NSDL", b"NS\x00DL"),
    ],
)
def test_encoding_empty_records_and_control_characters_are_not_silently_normalized(content):
    with pytest.raises(ValueError):
        parse_native(content, options(), "IN", "source.txt")


def test_nonzero_components_and_partial_allocated_deposit_never_become_gross_cash():
    content = original()
    for line, field, value in [
        (4, 15, "10.00"),
        (4, 16, "40.00"),
        (4, 17, "1050.00"),
        (4, 19, "1030.00"),
        (3, 23, "20.00"),
        (3, 24, "80.00"),
        (3, 25, "5.00"),
        (3, 26, "3.00"),
        (3, 39, "2.00"),
        (3, 27, "100110.00"),
        (2, 47, "100110.00"),
        (3, 29, "1930.00"),
        (3, 31, "10.00"),
        (3, 32, "40.00"),
        (3, 33, "1950.00"),
        (3, 34, "5.00"),
        (3, 35, "3.00"),
    ]:
        content = edit(content, line, field, value)
    declared = controls()
    declared.update(surcharge="10", cess="40", allocated_deposit="1930", challan_deposit="100110")
    parsed = parse_native(
        content,
        options(native_withholding_controls=declared, control_totals={"INR": "1950"}),
        "IN",
        "synthetic-components.txt",
    )
    assert parsed["rows"][0]["amount"] == "1050.00"
    link = parsed["native_metadata"]["party_links"][0]
    assert link["total_tax"] == "1050.00" and link["allocated_deposit"] == "1030.00"
    assert parsed["native_metadata"]["component_controls"]["challan_deposit"] == "100110.00"


@pytest.mark.parametrize("form", ["26Q", "27EQ"])
@pytest.mark.parametrize("book_entry_flag", ["", "X", "0", "n", "N"])
def test_unknown_book_entry_flag_cannot_bypass_allocated_deposit_charge_control(
    form, book_entry_flag
):
    declared = controls(form)
    allocated = int(declared["allocated_deposit"])
    declared["challan_deposit"] = str(allocated)
    content = original(form)
    for line, field, value in [
        (2, 47, f"{allocated}.00"),
        (3, 22, f"{allocated - 5}.00"),
        (3, 25, "5.00"),
        (3, 27, f"{allocated}.00"),
        (3, 34, "5.00"),
        (3, 37, book_entry_flag),
    ]:
        content = edit(content, line, field, value)
    # All population and aggregate controls agree, but the gross challan cannot
    # cover the allocated party deposit plus its explicitly recorded interest.
    with pytest.raises(ValueError, match="book-entry flag|applicable recorded charges"):
        parse_native(
            content, options(form, native_withholding_controls=declared), "IN", "synthetic.txt"
        )


@pytest.mark.parametrize("form", ["26Q", "27EQ"])
def test_explicit_book_entry_is_preserved_as_observation_without_cash_evidence(form):
    parsed = parse_native(edit(original(form), 3, 37, "Y"), options(form), "IN", "synthetic.txt")
    assert parsed["native_metadata"]["challan_controls"][0]["book_entry_flag"] == "Y"
    assert parsed["native_metadata"]["bank_payment_or_tax_credit"] == "NOT_EVIDENCED"


@pytest.mark.parametrize("form", ["26Q", "27EQ"])
def test_nil_marker_cannot_label_a_positive_nonempty_party_population(form):
    with pytest.raises(ValueError, match="Nil statements are separate"):
        parse_native(edit(original(form), 3, 6, "Y"), options(form), "IN", "synthetic.txt")


def test_multiple_challans_are_complete_and_can_map_to_the_same_assessed_transactions():
    records = [line.decode().split("^") for line in original().splitlines()]
    records[1][3] = "2"
    records[1][46] = "200000.00"
    second = [list(row) for row in records[2:]]
    second[0][3] = "2"
    for row in second[1:]:
        row[3] = "2"
    records.extend(second)
    for index, row in enumerate(records, 1):
        row[0] = str(index)
    content = ("\r\n".join("^".join(row) for row in records) + "\r\n").encode()
    declared = controls()
    declared.update(
        challan_count=2,
        party_count=8,
        income_tax="3800",
        allocated_deposit="3800",
        challan_deposit="200000",
        payment_base="38000",
    )
    for index, group in enumerate(declared["groups"], 1):
        group["party_records"].append(f"1/2/{index}")
    result = parse_native(
        content,
        options(native_withholding_controls=declared, control_totals={"INR": "3800"}),
        "IN",
        "synthetic-two-challans.txt",
    )
    assert len(result["rows"]) == 4 and len(result["native_metadata"]["party_links"]) == 8
    assert result["rows"][0]["amount"] == "2000.00"


def test_prepared_native_statement_cannot_establish_expected_or_payment_roles():
    parsed = parse_native(original(), options(), "IN", "original.txt")
    data = WorkflowInput(
        workflow="india-withholding-liability",
        source_ids={role: uuid4() for role in ("expected", "withheld", "reported", "deposited")},
        as_of="2026-06-30",
        withholding_role="deductor",
        title="Synthetic source-role isolation",
        rationale="Prepared return observations are not independent expectations or payment evidence",
    )
    with pytest.raises(ValueError, match="restricted"):
        calculate(data, "IN", {role: parsed for role in data.source_ids})


def test_maximum_party_population_retains_every_record_without_partial_output():
    records = [line.decode().split("^") for line in original().splitlines()]
    records = records[:4]
    records[1][46] = "5000000.00"
    records[2][4] = "5000"
    for field in (22, 27, 29, 30, 33):
        records[2][field - 1] = "5000000.00"
    template = records.pop()
    for i in range(1, 5001):
        row = list(template)
        row[0] = str(i + 3)
        row[4] = str(i)
        records.append(row)
    content = ("\r\n".join("^".join(row) for row in records) + "\r\n").encode()
    declared = controls()
    declared.update(
        party_count=5000,
        income_tax="5000000",
        allocated_deposit="5000000",
        challan_deposit="5000000",
        payment_base="50000000",
    )
    group = declared["groups"][0]
    declared["groups"] = [
        {**group, "transaction_reference": f"SYN-{i}", "party_records": [f"1/1/{i}"]}
        for i in range(1, 5001)
    ]
    result = parse_native(
        content,
        options(
            native_withholding_controls=declared,
            expected_rows=5000,
            control_totals={"INR": "5000000"},
        ),
        "IN",
        "synthetic-5000.txt",
    )
    assert len(result["rows"]) == len(result["native_metadata"]["party_links"]) == 5000
    assert result["native_metadata"]["party_links"][-1]["party_key"] == "1/1/5000"


@pytest.mark.parametrize("status", ["superseded", "cancelled"])
def test_assessed_history_status_never_silently_turns_raw_positive_observations_into_zero(status):
    declared = controls()
    declared["record_status"] = status
    result = parse_native(
        original(), options(native_withholding_controls=declared), "IN", "original.txt"
    )
    assert all(row["record_status"] == status for row in result["rows"])
    assert result["rows"][0]["amount"] == "1000.00"


def test_pinned_lexical_limits_point_to_the_exact_original_issuer_workbooks():
    limits, _ = profile_limits()
    for form, version in (("26Q", "7.8"), ("27EQ", "6.9"), ("27Q", "7.5")):
        assert (
            limits[form]["source_sha256"]
            == hashlib.sha256((ROOT / f"protean-{form}-{version}.xls").read_bytes()).hexdigest()
        )
        assert {tag: len(fields) for tag, fields in limits[form]["field_lengths"].items()} == {
            "FH": 18,
            "BH": 72,
            "CD": 41,
            "DD": 54,
        }


@pytest.mark.parametrize("form", ["26Q", "27EQ"])
@pytest.mark.parametrize("quarter,month", [("Q1", 4), ("Q2", 7), ("Q3", 10), ("Q4", 1)])
def test_financial_quarter_scope_including_last_legacy_q4_is_not_inferred_from_upload_date(
    form, quarter, month
):
    year = 2025 if quarter == "Q4" else 2020
    event_year = year + (month < 4)
    period = f"{event_year}-{month:02}"
    native_date = f"01{month:02}{event_year}"
    declared = controls(form)
    declared.update(financial_year=f"{year}{(year + 1) % 100:02}", quarter=quarter)
    for group in declared["groups"]:
        group.update(transaction_date=period + "-01", period=period)
    content = original(form)
    for line, field, value in [
        (1, 5, f"3103{year + 1}"),
        (2, 16, f"{year + 1}{(year + 2) % 100:02}"),
        (2, 17, declared["financial_year"]),
        (2, 18, quarter),
        (3, 18, native_date),
    ]:
        content = edit(content, line, field, value)
    for line in range(4, 4 + declared["party_count"]):
        content = edit(content, line, 23, native_date)
        content = edit(content, line, 24, native_date)
    result = parse_native(
        content,
        options(form, native_withholding_controls=declared),
        "IN",
        "synthetic-quarter-scope-not-fvu-validation.txt",
    )
    assert all(
        row["period"] == period
        and row["tax_year_start"] == f"{year}-04-01"
        and row["tax_year_end"] == f"{year + 1}-03-31"
        for row in result["rows"]
    )
    assert result["native_metadata"]["fvu_validation"] == "NOT_PERFORMED"
