"""Original issuer 27Q sample and independent synthetic controls, not treaty qualification."""

from uuid import uuid4

import pytest

from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput
from tests.unit.test_india_withholding_native import ROOT, edit


def original27():
    return (ROOT / "protean-27Q-original-sample.txt").read_bytes()


def controls27():
    return {
        "tan": "MUMN77777A",
        "financial_year": "201920",
        "quarter": "Q3",
        "observed_on": "2026-10-30",
        "batch_count": 1,
        "challan_count": 1,
        "party_count": 2,
        "income_tax": "166000",
        "surcharge": "0",
        "cess": "0",
        "allocated_deposit": "166000",
        "challan_deposit": "20000000",
        "payment_base": "26600000",
        "record_status": "current",
        "crosswalk_document_version_id": str(uuid4()),
        "assessment": "SYNTHETIC independently counted public sample and retained crosswalk; not client or treaty qualification",
        "groups": [
            {
                "transaction_reference": f"SYN-NR-{i}",
                "transaction_date": "2019-12-10",
                "period": "2019-12",
                "rule_reference": "SYN-NR-ASSESSED-SECTION",
                "party_records": [f"1/1/{i}"],
            }
            for i in (1, 2)
        ],
    }


def options27(**changes):
    return SourceInput.model_validate(
        {
            "file_format": "india-27q-regular-v7.5",
            "evidence_version_id": str(uuid4()),
            "table_type": "withholding-records",
            "label": "SYNTHETIC original public 27Q controlled observations",
            "expected_rows": 2,
            "control_totals": {"INR": "166000"},
            "native_withholding_controls": controls27(),
            **changes,
        }
    )


def test_original27_preserves_nonresident_fields_and_does_not_infer_treaty_or_payment():
    body = parse_native(original27(), options27(), "IN", "public-27q.txt")
    assert body["allowed_source_roles"] == ["reported"]
    assert body["allowed_workflows"] == ["india-withholding-liability"]
    assert body["row_count"] == 2 and body["control_totals"] == {"INR": "166000.00"}
    assert all(r["tax_kind"] == "TDS" and r["legal_role"] == "deductor" for r in body["rows"])
    assert all(r["payment_date"] is None for r in body["rows"])
    m = body["native_metadata"]
    assert m["nonresident_treaty_and_residence_qualification"] == "NOT_PERFORMED"
    assert (
        m["layout_specification_sha256"]
        == "dfde04d4458c90c6db7941f1c30c13c3d2a196a896e77d771b703fc5411da43a"
    )
    assert m["component_controls"]["challan_deposit"] == "20000000.00"
    assert m["challan_controls"][0]["challan_number"] == "00412"
    assert m["challan_controls"][0]["bsr_or_form24g_reference"] == "0000525"
    a, b = m["party_links"]
    assert [a["pan"], b["pan"]] == ["GHSPL9563J", "HNSPL7485K"]
    assert a["recorded_rate_basis"] == b["recorded_rate_basis"] == "B"
    assert [a["nature_of_remittance_code"], b["nature_of_remittance_code"]] == ["21", "49"]
    assert a["residence_country_code"] == b["residence_country_code"] == "113"
    assert a["cash_withdrawal_194n"] == "1100000.00"
    assert (
        b["cash_withdrawal_194n"] == a["foreign_tax_identifier"] == a["form_15ca_reference"] == ""
    )
    assert m["bank_payment_or_tax_credit"] == m["filing_or_acknowledgment"] == "NOT_EVIDENCED"


@pytest.mark.parametrize("country", ["AE", "GB"])
def test_27q_cannot_activate_as_other_country_domestic_rule(country):
    with pytest.raises(ValueError, match="unavailable"):
        parse_native(original27(), options27(), country, "public.txt")


@pytest.mark.parametrize(
    "line,field,value",
    [
        (1, 3, "TC1"),
        (2, 5, "26Q"),
        (2, 17, "202627"),
        (3, 37, ""),
        (3, 37, "?"),
        (3, 6, "Y"),
        (3, 29, "1.00"),
        (4, 35, ""),
        (4, 35, "C"),
        (4, 36, ""),
        (4, 36, "abc"),
        (4, 38, ""),
        (4, 38, "AE"),
        (4, 43, "-1.00"),
        (4, 43, "unknown"),
        (4, 42, "x" * 26),
        (4, 37, "x" * 16),
        (5, 4, "2"),
        (5, 5, "1"),
    ],
)
def test_27q_rejects_wrong_population_controls_or_unsupported_source_fields(line, field, value):
    with pytest.raises(ValueError):
        parse_native(edit(original27(), line, field, value), options27(), "IN", "bad.txt")


@pytest.mark.parametrize("field,value", [(35, "A"), (36, "49"), (38, "114"), (42, "FOREIGN-ID-2")])
def test_crosswalk_cannot_merge_distinct_nonresident_contexts(field, value):
    raw = edit(original27(), 5, 10, "GHSPL9563J")
    raw = edit(raw, 5, 33, "94N")
    raw = edit(raw, 5, 36, "21")
    raw = edit(raw, 5, field, value)
    controls = controls27()
    controls["groups"] = [{**controls["groups"][0], "party_records": ["1/1/1", "1/1/2"]}]
    with pytest.raises(ValueError, match="nonresident crosswalk group"):
        parse_native(
            raw, options27(expected_rows=1, native_withholding_controls=controls), "IN", "mixed.txt"
        )


def test_27q_purchase_control_is_not_a_tcs_population():
    controls = {**controls27(), "purchase_value": "0"}
    with pytest.raises(ValueError, match="purchase-value"):
        parse_native(
            original27(), options27(native_withholding_controls=controls), "IN", "original.txt"
        )


def test_missing_pan_sentinel_does_not_establish_one_nonresident_party_identity():
    raw = edit(original27(), 4, 10, "PANNOTAVBL")
    raw = edit(raw, 5, 10, "PANNOTAVBL")
    raw = edit(raw, 5, 33, "94N")
    raw = edit(raw, 5, 36, "21")
    declared = controls27()
    declared["groups"] = [{**declared["groups"][0], "party_records": ["1/1/1", "1/1/2"]}]
    with pytest.raises(ValueError, match="Missing-PAN nonresident parties"):
        parse_native(
            raw,
            options27(expected_rows=1, native_withholding_controls=declared),
            "IN",
            "missing-pan.txt",
        )


@pytest.mark.parametrize("flag", ["Y", "N", "", "?"])
def test_last_legacy_year_requires_its_recorded_opt_out_flag_without_inferring_election(flag):
    raw = original27()
    for line, field, value in [
        (1, 5, "05012026"),
        (2, 16, "202627"),
        (2, 17, "202526"),
        (3, 18, "10122025"),
    ]:
        raw = edit(raw, line, field, value)
    for line in (4, 5):
        for field, value in [(23, "10122025"), (24, "10122025"), (49, flag)]:
            raw = edit(raw, line, field, value)
    declared = controls27()
    declared["financial_year"] = "202526"
    for group in declared["groups"]:
        group.update(transaction_date="2025-12-10", period="2025-12")
    data = options27(native_withholding_controls=declared)
    if flag not in {"Y", "N"}:
        with pytest.raises(ValueError, match="115BAC opt-out flag"):
            parse_native(raw, data, "IN", "synthetic-last-legacy-year.txt")
    else:
        result = parse_native(raw, data, "IN", "synthetic-last-legacy-year.txt")
        assert {p["recorded_115bac_opt_out"] for p in result["native_metadata"]["party_links"]} == {
            flag
        }
        assert (
            result["native_metadata"]["nonresident_treaty_and_residence_qualification"]
            == "NOT_PERFORMED"
        )


@pytest.mark.parametrize("status", ["superseded", "cancelled"])
def test_history_preserves_actual_amounts_without_creating_current_or_zero_observations(status):
    controls = {**controls27(), "record_status": status}
    body = parse_native(
        original27(), options27(native_withholding_controls=controls), "IN", "history.txt"
    )
    assert {r["record_status"] for r in body["rows"]} == {status}
    assert body["control_totals"] == {"INR": "166000.00"}


@pytest.mark.parametrize(
    "year,codes,accepted",
    [
        (2010, False, True),
        (2012, False, True),
        (2012, True, False),
        (2013, False, False),
        (2013, True, True),
    ],
)
def test_nonresident_field_window_does_not_apply_later_layout_facts_to_earlier_years(
    year, codes, accepted
):
    raw = original27()
    fy = f"{year}{(year + 1) % 100:02}"
    ay = f"{year + 1}{(year + 2) % 100:02}"
    for line, field, value in [
        (1, 5, f"0501{year + 1}"),
        (2, 16, ay),
        (2, 17, fy),
        (3, 18, f"1012{year}"),
    ]:
        raw = edit(raw, line, field, value)
    for line in (4, 5):
        for field, value in [(23, f"1012{year}"), (24, f"1012{year}"), (33, "195"), (43, "")]:
            raw = edit(raw, line, field, value)
        if not codes:
            for field in (35, 36, 37, 38):
                raw = edit(raw, line, field, "")
    declared = controls27()
    declared["financial_year"] = fy
    for group in declared["groups"]:
        group.update(transaction_date=f"{year}-12-10", period=f"{year}-12")
    data = options27(native_withholding_controls=declared)
    if not accepted:
        with pytest.raises(ValueError, match="nonresident|Nonresident"):
            parse_native(raw, data, "IN", "synthetic-year-boundary.txt")
    else:
        result = parse_native(raw, data, "IN", "synthetic-year-boundary.txt")
        assert result["native_metadata"]["financial_year"] == fy
        assert result["native_metadata"]["party_links"][0]["recorded_rate_basis"] == (
            "B" if codes else ""
        )
