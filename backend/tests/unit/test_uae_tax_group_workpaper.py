import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.country_workflows.uae_tax_group_workpaper import (
    BINDING,
    CONTRACT,
    ENGINE_CONTRACT,
    TaxGroupWorkpaperInput,
    body_for,
    collection,
    parse_mapping,
    preview,
    validate_workpaper,
)
from app.modules.ifrs.uae_tax_group_statements import TaxGroupStatements
from tests.unit.test_uae_tax_group_statements import existing_group
from tests.unit.test_uae_tax_group_statements import sample as paper_sample


def sample(**changes):
    return {
        "profile": CONTRACT,
        "label": "SYNTHETIC retained Tax Group workpaper",
        "assessed_on": "2026-10-01",
        "adopted_from": "2025-01-01",
        "adopted_through": "2026-12-31",
        "operative_changes": "assessed_none",
        "legal_adoption_assessment": "SYNTHETIC separately assessed source adoption, no legal qualification",
        "rule_evidence_version_id": str(uuid4()),
        "clarification_evidence_version_id": str(uuid4()),
        "adoption_evidence_version_id": str(uuid4()),
        "adoption_sha256": "b" * 64,
        "mapping_evidence_version_id": str(uuid4()),
        "mapping_sha256": "c" * 64,
        **changes,
    }


def test_mapping_is_the_retained_input_not_reentered_or_generated_output():
    mapped = parse_mapping(json.dumps(paper_sample()).encode())
    data = TaxGroupWorkpaperInput.model_validate(sample())
    validate_workpaper(data, mapped)
    body = body_for(data, mapped)
    assert body["row_count"] == 11
    assert len(body["tax_group_source_lines"]) == 21
    assert len(body["tax_group_members"]) == 2
    assert len(body["tax_group_notes"]) == 4
    assert len(body["tax_group_checks"]) == 15
    assert body["tax_group_totals"][0]["assets"] == "220"
    assert not body["blocked"] and not body["validation"]["ready"]
    assert not body["source_binding_established"] and not body["statutory_issuance"]
    assert "workpaper" not in body["parameters"]


def test_published_mapping_schema_does_not_offer_fractional_json_numbers():
    from app.modules.country_workflows.uae_tax_group_workpaper import mapping_schema

    schema = mapping_schema()
    amount = schema["$defs"]["StatementLine"]["properties"]["amount"]
    assert [option["type"] for option in amount["anyOf"]] == ["integer", "string"]
    assert amount["anyOf"][1]["pattern"].startswith("^-")
    assert "total-digit checks" in amount["description"]


def test_country_workflow_fingerprint_includes_the_tax_group_calculation(monkeypatch):
    from pathlib import Path

    from app.core.operations_contracts import country_workflow_hash

    before = country_workflow_hash()
    original = Path.read_bytes

    def changed(path):
        content = original(path)
        return (
            content + b"\n# SYNTHETIC changed calculation"
            if path.as_posix().endswith("modules/ifrs/uae_tax_group_statements.py")
            else content
        )

    monkeypatch.setattr(Path, "read_bytes", changed)
    assert country_workflow_hash() != before


@pytest.mark.parametrize(
    "raw",
    [
        b'{"contract":"one","contract":"two"}',
        b'{"x":{"x":1,"x":2}}',
        b'{"x":NaN}',
        b'{"x":1.5}',
        b"\xff",
        b"[" * 34 + b"0" + b"]" * 34,
        b" " * (8 * 1024 * 1024 + 1),
    ],
    ids=[
        "duplicate-root",
        "duplicate-nested",
        "nonfinite",
        "fractional-number",
        "encoding",
        "deep",
        "oversized",
    ],
)
def test_untrusted_mapping_shape_and_numeric_boundaries(raw):
    with pytest.raises((ValueError, UnicodeError)):
        parse_mapping(raw)


@pytest.mark.parametrize(
    "changes",
    [
        {"assessed_on": "2025-07-15"},
        {"assessed_on": "2099-01-01"},
        {"adopted_through": "2026-01-01"},
        {"label": " "},
        {"legal_adoption_assessment": " " * 20},
        {"workpaper": {}},
    ],
)
def test_metadata_boundaries_and_reentered_values_are_rejected(changes):
    with pytest.raises(ValueError):
        TaxGroupWorkpaperInput.model_validate(sample(**changes))


def test_documents_have_distinct_roles_and_members_cannot_clone_an_authority():
    data = sample()
    data["mapping_evidence_version_id"] = data["adoption_evidence_version_id"]
    with pytest.raises(ValueError, match="separate"):
        TaxGroupWorkpaperInput.model_validate(data)
    data = TaxGroupWorkpaperInput.model_validate(sample())
    paper = paper_sample()
    paper["current"]["members"][0]["source_evidence_version_id"] = str(
        data.rule_evidence_version_id
    )
    with pytest.raises(ValueError, match="separate"):
        validate_workpaper(data, TaxGroupStatements.model_validate(paper))


def test_comparative_adoption_is_not_inferred_from_current_year():
    data = TaxGroupWorkpaperInput.model_validate(sample())
    with pytest.raises(ValueError, match="comparative"):
        validate_workpaper(data, TaxGroupStatements.model_validate(existing_group()))


def test_balanced_numbers_cannot_clear_unresolved_legal_changes():
    body = body_for(
        TaxGroupWorkpaperInput.model_validate(sample(operative_changes="unresolved")),
        TaxGroupStatements.model_validate(paper_sample()),
    )
    assert body["blocked"] and body["exception_count"] == 1
    assert body["tax_group_issues"] == [{"code": "OPERATIVE_RULE_CHANGES_UNRESOLVED"}]


def test_decimal_zero_checks_do_not_become_string_comparison_exceptions():
    paper = paper_sample()
    for member in paper["current"]["members"]:
        member["lines"][5]["amount"] = "0.00000000"
        member["lines"][8]["amount"] = "0.00000000"
    body = body_for(
        TaxGroupWorkpaperInput.model_validate(sample()), TaxGroupStatements.model_validate(paper)
    )
    assert all(check["state"] == "SUPPORTED" for check in body["tax_group_checks"])


def test_member_reference_cannot_replace_the_adjusted_group_reconciliations():
    paper = paper_sample()
    paper["current"]["members"][0]["member"] = "ADJUSTED_GROUP"
    paper["current"]["members"][1]["lines"][2]["counterparty_member"] = "ADJUSTED_GROUP"
    body = body_for(
        TaxGroupWorkpaperInput.model_validate(sample()), TaxGroupStatements.model_validate(paper)
    )
    assert len(body["tax_group_checks"]) == 15
    assert sum(check["scope"] == "adjusted_group" for check in body["tax_group_checks"]) == 5
    assert sum(check["member"] == "ADJUSTED_GROUP" for check in body["tax_group_checks"]) == 5


def test_collection_filters_and_previews_do_not_mutate_retained_values():
    data = TaxGroupWorkpaperInput.model_validate(sample(adopted_from="2024-01-01"))
    body = body_for(data, TaxGroupStatements.model_validate(existing_group()))
    assert len(collection(body, "statements", "comparative", "position")) == 4
    view = preview(body, limit=1)
    assert len(view["tax_group_source_lines"]) == 1
    assert len(body["tax_group_source_lines"]) == 42
    assert len(collection(body, "notes", "current")) == 4


@pytest.mark.parametrize("fault", ["contract", "engine_contract", "tax_group_document_binding"])
async def test_unbound_or_obsolete_results_cannot_remain_current_or_be_approved(fault):
    from app.modules.country_workflows.review import approval_error
    from app.modules.intelligence.service import current

    body = {
        "workflow": "uae-tax-group-statements",
        "contract": CONTRACT,
        "engine_contract": ENGINE_CONTRACT,
        "tax_group_document_binding": BINDING,
    }
    body[fault] = "obsolete"
    assert "Regenerate" in approval_error(body)
    tenant = uuid4()
    assert not await current(
        None,
        SimpleNamespace(tenant_id=tenant),
        SimpleNamespace(tenant_id=tenant, kind="country-workflow", body=body),
    )
