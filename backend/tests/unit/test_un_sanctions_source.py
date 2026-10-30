"""Synthetic source-layout controls; no client or legal qualification."""

import hashlib
import uuid
from pathlib import Path

import pytest

from app.modules.country_workflows.diligence_calculations import sanctions
from app.modules.country_workflows.native_sources import formats, parse_native
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput

XML = """<CONSOLIDATED_LIST dateGenerated="2026-06-29T23:00:00Z">
<INDIVIDUALS><INDIVIDUAL><DATAID>1</DATAID><FIRST_NAME>Synthetic</FIRST_NAME>
<SECOND_NAME>Person</SECOND_NAME><UN_LIST_TYPE>SYNTHETIC REGIME</UN_LIST_TYPE>
<REFERENCE_NUMBER>ZZi.001</REFERENCE_NUMBER><NAME_ORIGINAL_SCRIPT>شخص تجريبي</NAME_ORIGINAL_SCRIPT>
<INDIVIDUAL_ALIAS><QUALITY>Good</QUALITY><ALIAS_NAME>Example Alias</ALIAS_NAME></INDIVIDUAL_ALIAS>
<INDIVIDUAL_ALIAS><QUALITY>Low</QUALITY><ALIAS_NAME>Example Alias</ALIAS_NAME></INDIVIDUAL_ALIAS>
<INDIVIDUAL_ALIAS><QUALITY/><ALIAS_NAME>na</ALIAS_NAME></INDIVIDUAL_ALIAS>
</INDIVIDUAL></INDIVIDUALS><ENTITIES><ENTITY><DATAID>2</DATAID>
<FIRST_NAME>Synthetic Entity</FIRST_NAME><UN_LIST_TYPE>SYNTHETIC REGIME</UN_LIST_TYPE>
<REFERENCE_NUMBER>ZZe.002</REFERENCE_NUMBER><ENTITY_ALIAS><QUALITY>a.k.a.</QUALITY>
<ALIAS_NAME>Former Entity</ALIAS_NAME></ENTITY_ALIAS><ENTITY_ALIAS><ALIAS_NAME/></ENTITY_ALIAS>
</ENTITY></ENTITIES></CONSOLIDATED_LIST>""".encode()


def controls(**changes):
    return dict(
        generated_at="2026-06-29T23:00:00Z",
        individuals=1,
        entities=1,
        original_script_names=1,
        individual_alias_names=2,
        entity_alias_names=1,
        empty_alias_records=2,
        assessment="Independent synthetic subject, script and alias population assessment",
        **changes,
    )


def options(**changes):
    return SourceInput.model_validate(
        {
            "evidence_version_id": str(uuid.uuid4()),
            "file_format": "un-sc-consolidated-xml",
            "table_type": "sanctions-entries",
            "label": "SYNTHETIC UN layout",
            "expected_rows": 6,
            "un_sanctions_controls": controls(),
            **changes,
        }
    )


def test_browser_sample_preserves_the_exact_synthetic_population():
    sample = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-un-consolidated.xml"
    )
    assert sample.read_bytes() == XML


@pytest.mark.parametrize("country", ["AE", "IN", "GB"])
def test_shared_exact_population_aliases_original_script_and_no_clearance(country):
    parsed = parse_native(XML, options(), country, "synthetic.xml")
    assert next(f for f in formats(country) if f["id"] == "un-sc-consolidated-xml")["available"]
    assert parsed["row_count"] == 6
    assert parsed["review_status"] == "UNVERIFIED"
    assert parsed["allowed_source_roles"] == ["list"]
    assert parsed["allowed_workflows"] == ["sanctions-name-review"]
    assert parsed["control_totals"] == {}
    rows = parsed["rows"]
    assert [r["native_alias_quality"] for r in rows if r["name"] == "Example Alias"] == [
        "Good",
        "Low",
    ]
    assert rows[1]["name"] == "شخص تجريبي"
    assert rows[1]["native_name_origin"] == "original-script"
    assert len({r["id"] for r in rows}) == 6
    assert len({r["list_subject_id"] for r in rows}) == 2
    metadata = parsed["native_metadata"]
    assert metadata["list_version"] == "UN-SC:" + hashlib.sha256(XML).hexdigest()
    assert metadata["identity_or_legal_clearance"] == "NOT_DETERMINED"
    assert metadata["authenticity"] == "UPLOADED_SNAPSHOT_NOT_AUTHENTICATED"


@pytest.mark.parametrize(
    "field",
    [
        "individuals",
        "entities",
        "original_script_names",
        "individual_alias_names",
        "entity_alias_names",
        "empty_alias_records",
    ],
)
def test_each_independent_population_control_is_enforced(field):
    declared = controls()
    declared[field] += 1
    expected = sum(
        declared[k]
        for k in declared
        if k not in {"generated_at", "assessment", "empty_alias_records"}
    )
    with pytest.raises(ValueError, match="controls do not agree"):
        parse_native(
            XML, options(un_sanctions_controls=declared, expected_rows=expected), "AE", "test.xml"
        )


@pytest.mark.parametrize(
    "change",
    [
        {"un_sanctions_controls": None},
        {"expected_rows": 5},
        {"control_totals": {"AED": "0"}},
        {"table_type": "transactions"},
        {"un_sanctions_controls": {**controls(), "individuals": True}},
        {"un_sanctions_controls": {**controls(), "assessment": "          "}},
        {"un_sanctions_controls": {**controls(), "generated_at": "2026-06-29T23:00:00"}},
        {"file_format": "canonical-csv"},
    ],
)
def test_explicit_controls_cannot_be_omitted_coerced_or_attached_to_other_formats(change):
    with pytest.raises(ValueError):
        options(**change)


@pytest.mark.parametrize(
    "old,new",
    [
        (b"<DATAID>2", b"<DATAID>1"),
        (b"ZZe.002", b"ZZi.001"),
        (b"<QUALITY>Low", b"<QUALITY>Unknown"),
        (b"<FIRST_NAME>Synthetic Entity", b"<FIRST_NAME>"),
        (b"<SECOND_NAME>Person</SECOND_NAME>", b"<SECOND_NAME><nested/></SECOND_NAME>"),
        (b"<DATAID>1</DATAID>", b"<DATAID>1</DATAID><DATAID>3</DATAID>"),
        (b"<UN_LIST_TYPE>SYNTHETIC REGIME", b"<UN_LIST_TYPE>"),
        (b"</ENTITY>", b"<UNKNOWN/></ENTITY>"),
        (b"2026-06-29T23:00:00Z", b"2026-06-29T23:00:00"),
        (b"2026-06-29T23:00:00Z", b"2026-06-28T23:00:00Z"),
        (b"Synthetic Entity", b"x" * 201),
        (b"<ENTITIES>", b"<OTHER>"),
    ],
)
def test_malformed_or_changed_population_never_partially_imports(old, new):
    with pytest.raises(ValueError):
        parse_native(XML.replace(old, new), options(), "AE", "test.xml")


def test_entities_and_external_definitions_are_rejected_and_timezone_is_normalized():
    with pytest.raises(ValueError, match="without DTDs"):
        parse_native(
            b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///never-read">]>' + XML,
            options(),
            "AE",
            "test.xml",
        )
    equivalent = XML.replace(b"2026-06-29T23:00:00Z", b"2026-06-30T01:00:00+02:00")
    assert (
        parse_native(equivalent, options(), "IN", "test.xml")["rows"][0]["published_on"]
        == "2026-06-29"
    )


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_native_alias_context_survives_name_screening_and_version_freshness_blocks(country):
    native = parse_native(XML, options(), country, "test.xml")
    data = WorkflowInput(
        workflow="sanctions-name-review",
        source_ids={k: uuid.uuid4() for k in ("subjects", "list", "policy")},
        as_of="2026-06-30",
        title="Synthetic screening",
        rationale="Synthetic independent snapshot population",
    )
    tables = {
        "subjects": [{"id": "S1", "name": "Example Alias", "evidence_reference": "SYNTHETIC-ID"}],
        "list": native["rows"],
        "policy": [
            {
                "id": "P1",
                "list_version": native["native_metadata"]["list_version"],
                "maximum_list_age_days": 7,
                "minimum_similarity": "1",
            }
        ],
    }
    result = sanctions(data, tables, country)
    assert result["rows"][0]["state"] == "POTENTIAL_NAME_MATCH"
    hits = result["rows"][0]["candidates"]
    assert len(hits) == 2
    assert {h["native_alias_quality"] for h in hits} == {"Good", "Low"}
    assert all(h["native_reference_number"] == "ZZi.001" for h in hits)
    tables["policy"][0]["list_version"] = "OTHER-SNAPSHOT"
    assert sanctions(data, tables, country)["blocked"]
