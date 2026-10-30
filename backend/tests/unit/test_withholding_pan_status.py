"""Missing-PAN markers preserve amounts and need an explicitly scoped retained assessment."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.withholding_pan import current
from app.modules.country_workflows.withholding_schemas import WithholdingRecord
from tests.unit.test_withholding_workflows import pooled_certificate_population, population
from tests.unit.test_withholding_workflows import run as run_comparison


def run(records, role="deductor"):
    prepared = deepcopy(records)
    for rows in prepared.values():
        for row in rows:
            if isinstance(row.get("pan_treatment"), dict):
                row["pan_treatment"] = json.dumps(row["pan_treatment"])
    return run_comparison(prepared, role)


def treatment(marker="PANNOTAVBL", **changes):
    return {
        "marker": marker,
        "party_reference": "SYN-ASSESSSED-PARTY-01",
        "treatment_reference": "SYN-reviewed-rule-version-1",
        "assessed_on": "2026-06-01",
        "assessment": "SYNTHETIC independently assessed identity and missing-PAN rule/certificate treatment; not registry authentication",
        **changes,
    }


def treated(role="deductor", marker="PANNOTAVBL", **changes):
    records = population(role)
    for rows in records.values():
        for row in rows:
            row["counterparty"] = marker
    record = records["expected" if role in {"deductor", "collector"} else "certificate"][0]
    record["pan_treatment"] = treatment(marker, **changes)
    return records


@pytest.mark.parametrize("role", ["deductor", "collector", "deductee", "collectee"])
@pytest.mark.parametrize("marker", ["PANNOTAVBL", "PANAPPLIED", "PANINVALID"])
def test_equal_amounts_cannot_clear_an_unassessed_missing_pan_marker(role, marker):
    records = population(role)
    for rows in records.values():
        for row in rows:
            row["counterparty"] = marker
    out = run(records, role)
    assert out["blocked"] is True
    row = out["rows"][0]
    assert row["comparison_state"] == "MATCHED"
    assert row["state"] == "PAN_TREATMENT_NOT_SUPPORTED"
    assert "PAN_TREATMENT_ASSESSMENT_MISSING" in row["pan_issues"]
    assert set(row["amounts"].values()) == {"100"}


@pytest.mark.parametrize("role", ["deductor", "collector", "deductee", "collectee"])
@pytest.mark.parametrize("marker", ["PANNOTAVBL", "PANAPPLIED", "PANINVALID"])
def test_scoped_retained_treatment_can_support_reconciliation_without_authenticating_pan(
    role, marker
):
    records = treated(role, marker)
    before = deepcopy(records)
    out = run(records, role)
    assert records == before
    row = out["rows"][0]
    assert row["comparison_state"] == row["state"] == "MATCHED"
    assert not out["blocked"] and not row["pan_issues"]
    assert row["pan_authentication"] == "NOT_PERFORMED" and row["pan_status"] == marker
    assert row["pan_treatment_state"] == "DOCUMENTED_ON_RETAINED_ASSESSMENT"
    assert row["pan_treatment"]["party_reference"] == "SYN-ASSESSSED-PARTY-01"
    assert current(out) and approval_error(out) is None


@pytest.mark.parametrize("role", ["deductor", "collector", "deductee", "collectee"])
def test_future_treatment_or_missing_document_cannot_clear_matching_amounts(role):
    future = run(treated(role, assessed_on="2026-07-01"), role)
    assert (
        future["blocked"]
        and "PAN_TREATMENT_ASSESSMENT_AFTER_CUTOFF" in future["rows"][0]["pan_issues"]
    )
    records = treated(role)
    record = records["expected" if role in {"deductor", "collector"} else "certificate"][0]
    record["assessment_evidence_version_id"] = record["assessment_sha256"] = None
    missing = run(records, role)
    assert (
        missing["blocked"]
        and "PAN_TREATMENT_RETAINED_ASSESSMENT_NOT_SUPPORTED" in missing["rows"][0]["pan_issues"]
    )
    assert approval_error(missing)
    missing["rows"][0]["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(missing)


@pytest.mark.parametrize(
    "changes",
    [
        {"marker": "PANINVALID"},
        {"party_reference": "PANNOTAVBL"},
        {"party_reference": " "},
        {"treatment_reference": "another-rule"},
        {"assessed_on": 1234567890},
        {"assessed_on": "2026-06-01T00:00:00Z"},
        {"assessment": "          "},
    ],
)
def test_treatment_rejects_other_markers_rules_empty_party_references_or_implicit_dates(changes):
    records = treated()
    records["expected"][0]["pan_treatment"].update(changes)
    with pytest.raises(ValueError):
        WithholdingRecord.model_validate(records["expected"][0])


def test_structured_csv_treatment_retains_exact_fields_and_legacy_rows_stay_unchanged():
    record = treated()["expected"][0]
    record["pan_treatment"] = json.dumps(record["pan_treatment"])
    validated = WithholdingRecord.model_validate(record).model_dump(mode="json")
    assert validated["pan_treatment"] == treatment()
    assert "pan_treatment" not in WithholdingRecord.model_validate(
        population()["expected"][0]
    ).model_dump(mode="json")


@pytest.mark.parametrize("role", ["deductor", "deductee"])
async def test_retained_pre_control_missing_pan_results_cannot_feed_new_actions(role):
    from app.modules.intelligence.service import current as event_current

    body = run(treated(role), role)
    assert current(body)
    body.pop("withholding_pan_contract")
    body["review_status"] = "REVIEWED"
    assert not current(body) and "Regenerate" in approval_error(body)
    obj = SimpleNamespace(tenant_id="tenant", kind="country-workflow", body=body)
    assert not await event_current(None, SimpleNamespace(tenant_id="tenant"), obj)


def test_saved_claim_of_documented_treatment_without_the_document_or_context_is_not_current():
    body = run(treated())
    body["rows"][0]["assessment_provenance"]["assessment_sha256"] = None
    assert not current(body)
    body = run(treated())
    body["rows"][0]["pan_treatment"] = {}
    assert not current(body)


@pytest.mark.parametrize("role", ["deductee", "collectee"])
def test_certificate_caps_stay_pooled_for_the_same_assessed_party_but_not_different_parties(role):
    records = pooled_certificate_population()
    for rows in records.values():
        for row in rows:
            row.update(
                counterparty="PANNOTAVBL",
                legal_role=role,
                tax_kind="TDS" if role == "deductee" else "TCS",
            )
    for row in records["certificate"]:
        row["pan_treatment"] = treatment()
    for row in records["certificate"]:
        row["assessment_amount_limit"] = "150"
    result = run(records, role)
    assert result["blocked"]
    assert all(
        "CERTIFICATE_SHARED_AMOUNT_LIMIT_EXCEEDED" in row["assessment_issues"]
        for row in result["rows"]
    )
    for row in records["certificate"]:
        row["assessment_amount_limit"] = "200"
    assert not run(records, role)["blocked"]
    records["certificate"][1]["pan_treatment"]["party_reference"] = "SYN-OTHER-PARTY"
    with pytest.raises(ValueError, match="Conflicting certificate scope"):
        run(records, role)


@pytest.mark.parametrize("role", ["deductor", "collectee"])
def test_zero_amounts_do_not_make_an_unassessed_pan_marker_verified(role):
    records = population(role)
    for rows in records.values():
        for row in rows:
            row.update(counterparty="PANNOTAVBL", amount="0")
    result = run(records, role)
    assert result["blocked"] and result["rows"][0]["pan_authentication"] == "NOT_PERFORMED"
    assert set(result["rows"][0]["amounts"].values()) == {"0"}
