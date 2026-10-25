"""Synthetic numbered responses exercise real GSTR-2B readers and controls."""

import json
import uuid
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.gstr2b_parts import assemble
from app.modules.country_workflows.schemas import SourceInput
from tests.unit.test_india_gstr2b_source import document, options, payload
from tests.unit.test_india_invoice_source import SELLER


def bundle():
    manifest = payload()
    manifest.pop("docdata")
    manifest["fc"] = 2
    manifest["cpsumm"]["b2b"][0]["ttldocs"] = 2
    first, second = payload(), payload()
    second["docdata"]["b2b"][0]["inv"] = [document(inum="SYNTHETIC-2", txval=50, igst=9, val=59)]
    identifiers = [str(uuid.uuid4()), str(uuid.uuid4())]
    data = options(
        expected_rows=8,
        expected_documents=2,
        control_totals={"INR": "27"},
        gstr2b_expected_files=2,
        gstr2b_retrieval_assessment="Synthetic original numbered requests checked against the generation manifest",
        gstr2b_parts=[
            dict(
                file_number=index + 1,
                evidence_version_id=identifier,
                expected_documents=1,
                tax_total=str(tax),
                request_reference="SYNTHETIC-REQUEST-" + str(index + 1),
            )
            for index, (identifier, tax) in enumerate(zip(identifiers, (18, 9), strict=True))
        ],
    )
    return manifest, {identifiers[0]: first, identifiers[1]: second}, data


def run(manifest=None, parts=None, data=None):
    default_manifest, default_parts, default_data = bundle()
    return assemble(
        json.dumps(manifest if manifest is not None else default_manifest).encode(),
        {
            key: json.dumps(value).encode()
            for key, value in (parts if parts is not None else default_parts).items()
        },
        data or default_data,
    )


def test_complete_numbered_set_preserves_original_file_provenance_and_controls():
    manifest, parts, data = bundle()
    result = run(manifest, parts, data)
    assert result["row_count"] == 8 and result["control_totals"] == {"INR": "27"}
    assert result["allowed_source_roles"] == ["return"]
    assert {row["source_part_file_number"] for row in result["rows"]} == {1, 2}
    assert {row["source_part_evidence_version_id"] for row in result["rows"]} == set(parts)
    assert all(len(row["source_part_sha256"]) == 64 for row in result["rows"])
    assert result["native_metadata"]["counterparty_summary"]["b2b"][0]["ttldocs"] == 2
    assert result["native_metadata"]["provider_authenticity"] == "NOT_VERIFIED"


def test_missing_part_date_is_explicitly_bound_to_manifest_and_batch_review():
    manifest, parts, data = bundle()
    parts[str(data.gstr2b_parts[1].evidence_version_id)].pop("gendt")
    result = run(manifest, parts, data)
    assembly = result["native_metadata"]["assembly"]
    assert [part["generation_date_present"] for part in assembly["parts"]] == [True, False]
    assert "MANIFEST_AND_BATCH_REVIEW" in assembly["generation_binding"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("gendt", "14-08-2026"),
        ("rtnprd", "072026"),
        ("gstin", SELLER),
        ("version", "2.0"),
        ("file_number", 3),
        ("fc", 3),
    ],
)
def test_mixed_scope_generation_and_numbering_are_rejected(field, value):
    manifest, parts, data = bundle()
    parts[str(data.gstr2b_parts[0].evidence_version_id)][field] = value
    with pytest.raises(ValueError):
        run(manifest, parts, data)


def test_duplicate_bytes_and_duplicate_documents_cannot_complete_a_set():
    manifest, parts, data = bundle()
    parts[str(data.gstr2b_parts[1].evidence_version_id)] = deepcopy(
        parts[str(data.gstr2b_parts[0].evidence_version_id)]
    )
    with pytest.raises(ValueError, match="Duplicate original"):
        run(manifest, parts, data)
    parts[str(data.gstr2b_parts[1].evidence_version_id)]["chksum"] = "different-wrapper-metadata"
    # Give the second file a matching independent tax control, so document identity is the deciding check.
    values = data.model_dump(mode="json")
    values["gstr2b_parts"][1]["tax_total"] = "18"
    values["control_totals"] = {"INR": "36"}
    with pytest.raises(ValueError, match="Duplicate GSTR-2B document/component"):
        run(manifest, parts, SourceInput.model_validate(values))


@pytest.mark.parametrize(
    "mutation", ["missing-number", "repeated-id", "wrong-total", "missing-assessment"]
)
def test_request_manifest_cannot_omit_files_or_replace_independent_controls(mutation):
    _, _, data = bundle()
    values = data.model_dump(mode="json")
    if mutation == "missing-number":
        values["gstr2b_parts"][1]["file_number"] = 3
    elif mutation == "repeated-id":
        values["gstr2b_parts"][1]["evidence_version_id"] = values["gstr2b_parts"][0][
            "evidence_version_id"
        ]
    elif mutation == "wrong-total":
        values["control_totals"] = {"INR": "28"}
    else:
        values["gstr2b_retrieval_assessment"] = ""
    with pytest.raises(ValidationError):
        SourceInput.model_validate(values)


def test_per_file_and_whole_manifest_counts_are_independent_checks():
    manifest, parts, data = bundle()
    parts[str(data.gstr2b_parts[0].evidence_version_id)]["docdata"]["b2b"][0]["inv"][0]["igst"] = 19
    with pytest.raises(ValueError, match="control totals"):
        run(manifest, parts, data)
    manifest, parts, data = bundle()
    manifest["cpsumm"]["b2b"][0]["ttldocs"] = 3
    with pytest.raises(ValueError, match="counterparty document counts"):
        run(manifest, parts, data)


def test_successful_http_with_business_failure_and_token_pagination_are_rejected():
    manifest, parts, data = bundle()
    identifier = str(data.gstr2b_parts[0].evidence_version_id)
    parts[identifier] = {
        "code": 200,
        "data": {"status_cd": "0", "error": {"message": "Not available"}},
    }
    with pytest.raises(ValueError, match="successful supported"):
        run(manifest, parts, data)
    manifest, parts, data = bundle()
    manifest["next_token"] = "UNSUPPORTED"
    with pytest.raises(ValueError, match="Token/unknown"):
        run(manifest, parts, data)


def test_status_three_manifest_and_wrapped_parts_are_supported_without_authentication_claim():
    manifest, parts, data = bundle()
    manifest = {
        "code": 200,
        "data": {"status_cd": "3", "data": {"chksum": "DECLARED", "data": manifest}},
    }
    parts = {
        key: {"code": 200, "data": {"status_cd": "1", "data": {"chksum": "PART", "data": value}}}
        for key, value in parts.items()
    }
    result = run(manifest, parts, data)
    assert result["row_count"] == 8 and result["native_metadata"]["assembly"][
        "manifest_checksums"
    ] == ["DECLARED"]


def test_one_hundred_numbered_files_remain_within_existing_document_and_row_bounds():
    manifest, _, data = bundle()
    manifest["fc"] = 100
    manifest["cpsumm"]["b2b"][0]["ttldocs"] = 100
    originals = {}
    declarations = []
    for number in range(1, 101):
        identifier = str(uuid.uuid4())
        original = payload()
        original["docdata"]["b2b"][0]["inv"][0]["inum"] = "SYNTHETIC-" + str(number)
        originals[identifier] = original
        declarations.append(
            dict(
                file_number=number,
                evidence_version_id=identifier,
                expected_documents=1,
                tax_total="18",
                request_reference="SYNTHETIC-REQUEST-" + str(number),
            )
        )
    values = data.model_dump(mode="json")
    values.update(
        gstr2b_expected_files=100,
        gstr2b_parts=declarations,
        expected_documents=100,
        expected_rows=400,
        control_totals={"INR": "1800"},
    )
    result = run(manifest, originals, SourceInput.model_validate(values))
    assert result["row_count"] == 400 and result["control_totals"] == {"INR": "1800"}
    assert len(result["native_metadata"]["assembly"]["parts"]) == 100


def test_credit_notes_across_files_keep_their_signed_amounts_without_summary_netting():
    manifest, parts, data = bundle()
    second = str(data.gstr2b_parts[1].evidence_version_id)
    parts[second]["docdata"] = {
        "cdnr": [
            {
                "ctin": SELLER,
                "nt": [
                    {
                        "ntnum": "SYNTHETIC-CN",
                        "typ": "C",
                        "dt": "16-06-2026",
                        "txval": 50,
                        "igst": 9,
                        "cgst": 0,
                        "sgst": 0,
                        "cess": 0,
                    }
                ],
            }
        ]
    }
    manifest["cpsumm"]["b2b"][0]["ttldocs"] = 1
    values = data.model_dump(mode="json")
    values["gstr2b_parts"][1]["tax_total"] = "-9"
    values["control_totals"] = {"INR": "9"}
    result = run(manifest, parts, SourceInput.model_validate(values))
    assert result["control_totals"] == {"INR": "9"}
    credit = [row for row in result["rows"] if row["document_type"] == "credit-note"]
    assert (
        len(credit) == 4
        and next(row for row in credit if row["component"] == "IGST")["tax"] == "-9"
    )
