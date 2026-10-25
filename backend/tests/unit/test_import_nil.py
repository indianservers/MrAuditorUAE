"""Nil means an explicit assessed population, never an omitted Box 7."""

import uuid
from copy import deepcopy

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.import_vat import import_vat
from app.modules.country_workflows.import_vat_source import ImportVATSourceInput, source_rows
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_import_vat import line


def parameters(**changes):
    return WorkflowInput.model_validate({
        "workflow": "uae-import-vat",
        "source_ids": {role: uuid.uuid4() for role in ("customs", "portal", "books")},
        "as_of": "2026-06-30", "title": "SYNTHETIC nil imports",
        "rationale": "Independently assessed synthetic nil population",
        "import_nil_scope": {
            "registration": "100000000000001", "period_start": "2026-04-01",
            "period_end": "2026-06-30", "kinds": ["declaration", "adjustment"],
            "context_evidence_version_id": str(uuid.uuid4()), "context_sha256": "a" * 64,
            "assessment": "Synthetic independent no-import and no-adjustment evidence",
        }, **changes,
    })


def output(kinds=None, receipt=True, tables=None):
    data = parameters()
    if kinds is not None:
        data.import_nil_scope.kinds = kinds
    return import_vat(data, tables or {role: [] for role in data.source_ids},
                      nil_receipt={"type": "evidence", "id": str(data.import_nil_scope.context_evidence_version_id), "sha256": "a"*64} if receipt else None)


def controls(boxes=("6", "7")):
    return ImportVATSourceInput.model_validate({
        "source_role": "books", "label": "SYNTHETIC nil import boxes",
        "assessment": "Independently checked zero population, base and tax controls",
        "boxes": {box: {"expected_rows": 0, "taxable_amount": "0", "tax": "0"} for box in boxes},
    })


def test_all_empty_nil_requires_verified_context_and_preserves_no_fabricated_rows():
    body = output()
    assert body["rows"] == [] and not body["blocked"]
    rows, totals = source_rows(body, controls())
    assert totals == {"AED": "0"}
    assert [row["box"] for row in rows] == ["6", "7"]
    assert all(row["tax"] == "0" and row["source_import_detail_ids"] == [] and row["nil_context_receipt"] for row in rows)
    assert output(receipt=False)["blocked"]
    with pytest.raises(ValueError, match="absence is not a verified nil"):
        source_rows(output(receipt=False), controls())


def test_only_declared_kind_becomes_zero_other_kind_remains_unknown():
    body = output(kinds=["declaration"])
    assert body["role_totals"]["books"]["adjustment"]["net"] is None
    assert source_rows(body, controls(("6",)))[0][0]["tax"] == "0"
    with pytest.raises(ValueError, match="absence is not a verified nil"):
        source_rows(body, controls(("7",)))


def test_nonempty_declarations_can_coexist_with_explicit_nil_adjustments():
    body = output(kinds=["adjustment"], tables={role: [line()] for role in parameters().source_ids})
    assert body["role_totals"]["books"]["declaration"]["tax"] == "50"
    assert source_rows(body, controls(("7",)))[0][0]["tax"] == "0"


@pytest.mark.parametrize("status", ["current", "cancelled", "superseded"])
def test_any_observed_history_contradicts_nil_even_if_not_current(status):
    with pytest.raises(ValueError, match="contradicts"):
        output(tables={role: [line(version_status=status)] for role in parameters().source_ids})


@pytest.mark.parametrize("field,value", [("expected_rows", 1), ("taxable_amount", "1"), ("tax", "-0.01")])
def test_independent_nil_controls_must_be_exact_zero(field, value):
    data = controls().model_dump(mode="json")
    data["boxes"]["6"][field] = value
    with pytest.raises(ValueError, match="controls do not agree"):
        source_rows(output(), ImportVATSourceInput.model_validate(data))


def test_nil_and_observed_scopes_cannot_differ():
    with pytest.raises(ValueError, match="one VAT registration"):
        output(kinds=["adjustment"], tables={role: [line(registration="100000000000002")] for role in parameters().source_ids})


@pytest.mark.parametrize("change", ["period", "duplicate", "registration", "workflow"])
def test_scope_validation(change):
    data = parameters().model_dump(mode="json")
    if change == "period":
        data["import_nil_scope"]["period_end"] = "2026-07-01"
    elif change == "duplicate":
        data["import_nil_scope"]["kinds"] = ["declaration", "declaration"]
    elif change == "registration":
        data["import_nil_scope"]["registration"] = "١" * 15
    else:
        data["workflow"] = "bank-brs"
    with pytest.raises(ValueError):
        WorkflowInput.model_validate(data)


def test_country_exclusion_still_applies_to_nil_and_absence_is_not_default_nil():
    sources = {role: {"table_type": "import-vat-lines", "rows": [], "control_totals": {"AED": "0"}, "nil_reason": "Synthetic empty retained source"} for role in parameters().source_ids}
    with pytest.raises(ValueError, match="unavailable"):
        calculate(parameters(), "IN", sources)
    data = parameters().model_copy(update={"import_nil_scope": None})
    with pytest.raises(ValueError, match="one VAT registration"):
        calculate(data, "AE", sources)
    assert calculate(parameters(), "AE", deepcopy(sources))["blocked"]


def test_wrong_retained_context_receipt_cannot_verify_a_nil_claim():
    data = parameters()
    with pytest.raises(ValueError, match="receipt differs"):
        import_vat(data, {role: [] for role in data.source_ids}, nil_receipt={"type": "evidence", "id": str(uuid.uuid4()), "sha256": "a" * 64})
