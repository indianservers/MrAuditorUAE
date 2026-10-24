from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.catalogue import catalogue
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import WorkflowInput
from app.modules.country_workflows.withholding_schemas import WithholdingRecord
from tests.unit.test_shared_audit_workflows import source


def record(**changes):
    return {
        "id": "TX1",
        "registration": "SYN-ENTITY",
        "counterparty": "SYN-PARTY",
        "legal_role": "deductor",
        "tax_kind": "TDS",
        "rule_reference": "SYN-reviewed-rule-version-1",
        "tax_year_start": "2026-04-01",
        "tax_year_end": "2027-03-31",
        "period": "2026-05",
        "transaction_reference": "SYN-TRANSACTION-1",
        "transaction_date": "2026-05-15",
        "currency": "INR",
        "amount": "100",
        "record_status": "current",
        "source_reference": "SYN-ORIGINAL",
        "source_version": "1",
        "due_date": "2026-06-07",
        "payment_date": "2026-06-01",
        **changes,
    }


def population(legal_role="deductor"):
    roles = (
        ("expected", "withheld", "reported", "deposited")
        if legal_role in {"deductor", "collector"}
        else ("books", "statement", "certificate")
    )
    records = {
        role: [
            record(
                id=role + "1",
                legal_role=legal_role,
                tax_kind="TDS" if legal_role in {"deductor", "deductee"} else "TCS",
                source_reference="SYN-" + role,
            )
        ]
        for role in roles
    }
    assessed_role = "expected" if legal_role in {"deductor", "collector"} else "certificate"
    records[assessed_role][0].update(
        assessment_evidence_version_id="00000000-0000-0000-0000-000000000001",
        assessment_sha256="a" * 64,
        assessment_kind="rule" if assessed_role == "expected" else "certificate",
        assessment_period_start="2026-04-01",
        assessment_period_end="2027-03-31",
        assessment_amount_limit=None if assessed_role == "expected" else "1000",
    )
    return records


def run(populations, legal_role="deductor", country="IN", **changes):
    tables = {role: source("withholding-records", rows) for role, rows in populations.items()}
    data = WorkflowInput(
        workflow="india-withholding-liability"
        if legal_role in {"deductor", "collector"}
        else "india-withholding-credit",
        withholding_role=legal_role,
        source_ids={role: uuid4() for role in tables},
        as_of="2026-06-30",
        title="Synthetic separate withholding evidence",
        rationale="Explicitly assessed role and current version selection with original evidence",
        **changes,
    )
    return calculate(data, country, tables)


@pytest.mark.parametrize("legal_role", ["deductor", "collector", "deductee", "collectee"])
def test_legal_roles_run_separately_without_entitlement_or_rate_inference(legal_role):
    p = population(legal_role)
    original = deepcopy(p)
    out = run(p, legal_role)
    assert p == original
    assert out["rows"][0]["state"] == "MATCHED"
    assert out["rows"][0]["legal_role"] == legal_role
    assert out["rows"][0]["credit_entitlement"] == "NOT_DETERMINED"
    assert out["statutory_calculation_qualified"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("counterparty", "SYN-OTHER"),
        ("registration", "SYN-OTHER"),
        ("rule_reference", "SYN-different-rule"),
        ("transaction_reference", "SYN-other-tx"),
        ("transaction_date", "2026-05-16"),
        ("period", "2026-04"),
        ("tax_year_start", "2026-03-01"),
    ],
)
def test_key_scope_mismatch_never_clears_another_liability(field, value):
    p = population()
    p["deposited"][0][field] = value
    out = run(p)
    assert all(row["state"] == "MISSING_CURRENT_RECORD" for row in out["rows"])


def test_assessed_superseded_return_is_retained_and_never_added_to_current_amount():
    p = population()
    p["reported"].append(
        {
            **p["reported"][0],
            "id": "old-return",
            "source_version": "0",
            "amount": "150",
            "record_status": "superseded",
        }
    )
    out = run(p)
    row = out["rows"][0]
    assert row["amounts"]["reported"] == "100"
    assert row["excluded_source_ids"]["reported"] == ["old-return"]
    assert row["selected_source_references"]["reported"]["version"] == "1"
    assert out["selected_current_totals"]["reported"] == "100"


@pytest.mark.parametrize("status", ["superseded", "cancelled"])
def test_inactive_only_observation_is_missing_and_never_an_implicit_zero(status):
    p = population()
    p["reported"][0]["record_status"] = status
    row = run(p)["rows"][0]
    assert row["state"] == "MISSING_CURRENT_RECORD"
    assert row["amounts"]["reported"] is None
    assert row["differences_from_expected"]["reported"] is None


@pytest.mark.parametrize("status", ["current", "cancelled"])
def test_duplicate_source_version_or_conflicting_status_cannot_be_relabelled(status):
    p = population()
    p["reported"].append({**p["reported"][0], "id": "alias", "record_status": status})
    with pytest.raises(ValueError, match="Duplicate source observation"):
        run(p)


def test_multiple_current_amendments_must_be_resolved_instead_of_summed():
    p = population()
    p["reported"].append({**p["reported"][0], "id": "amended", "source_version": "2"})
    with pytest.raises(ValueError, match="Multiple current"):
        run(p)


@pytest.mark.parametrize("legal_role", ["deductee", "collector"])
def test_mixed_legal_role_sources_are_rejected(legal_role):
    p = population()
    p["deposited"][0].update(
        legal_role=legal_role, tax_kind="TDS" if legal_role == "deductee" else "TCS"
    )
    with pytest.raises(ValueError, match="selected legal role"):
        run(p)


@pytest.mark.parametrize(
    "payment,due,state",
    [
        (None, "2026-06-07", "TIMING_NOT_VERIFIED"),
        ("2026-06-01", None, "TIMING_NOT_VERIFIED"),
        ("2026-06-08", "2026-06-07", "LATE_DEPOSIT"),
    ],
)
def test_deposit_timing_uses_assessed_expected_due_date(payment, due, state):
    p = population()
    p["expected"][0]["due_date"] = due
    p["deposited"][0]["payment_date"] = payment
    assert run(p)["rows"][0]["state"] == state


def test_credit_amount_mismatch_is_not_an_automatic_recoverable_tax_conclusion():
    p = population("deductee")
    p["statement"][0]["amount"] = "90"
    row = run(p, "deductee")["rows"][0]
    assert row["state"] == "VARIANCE"
    assert row["differences_from_books"]["statement"] == "-10"
    assert row["credit_entitlement"] == "NOT_DETERMINED"


@pytest.mark.parametrize("country", ["AE", "GB"])
def test_domestic_india_workflow_is_not_enabled_by_other_country_context(country):
    with pytest.raises(ValueError, match="unavailable"):
        run(population(), country=country)


def test_legacy_aggregate_preview_cannot_be_approved_even_with_no_exceptions():
    assert approval_error({"workflow": "india-withholding", "rows": [], "blocked": False})
    assert not next(row for row in catalogue("IN") if row["id"] == "india-withholding")["available"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "AED"),
        ("amount", "-1"),
        ("amount", "NaN"),
        ("counterparty", " "),
        ("source_reference", ""),
        ("source_version", ""),
        ("tax_kind", "TCS"),
        ("record_status", "unknown"),
        ("tax_year_end", "2026-01-01"),
        ("period", "2027-04"),
    ],
)
def test_unresolved_or_invalid_source_scope_is_not_accepted(field, value):
    with pytest.raises(ValueError):
        WithholdingRecord.model_validate(record(**{field: value}))


@pytest.mark.parametrize("when", ["2026-07-01", "2026-05-14"])
def test_future_or_pretransaction_deposits_require_a_separate_bridge(when):
    p = population()
    p["deposited"][0]["payment_date"] = when
    with pytest.raises(ValueError, match="Future deposit|predates transaction"):
        run(p)


def test_role_must_be_selected_even_when_source_amounts_agree():
    with pytest.raises(ValueError, match="Explicit.*legal role"):
        WorkflowInput(
            workflow="india-withholding-liability",
            source_ids={"expected": uuid4()},
            as_of="2026-06-30",
            title="Unresolved role",
            rationale="Sources do not infer an organizational legal role",
        )


@pytest.mark.parametrize(
    "review_status,blocked", [("UNVERIFIED", False), ("REVIEWED", False), ("REVIEWED", True)]
)
async def test_retained_roleless_approvals_are_stale_even_without_execution_metadata(
    review_status, blocked
):
    from app.modules.intelligence.service import current

    obj = SimpleNamespace(
        tenant_id="tenant",
        kind="country-workflow",
        body={
            "workflow": "india-withholding",
            "review_status": review_status,
            "blocked": blocked,
        },
    )
    assert not await current(None, SimpleNamespace(tenant_id="tenant"), obj)


@pytest.mark.parametrize("legal_role", ["deductor", "deductee"])
def test_free_text_assessments_do_not_allow_approval_even_if_amounts_match(legal_role):
    p = population(legal_role)
    assessed = p["expected" if legal_role == "deductor" else "certificate"][0]
    assessed["assessment_evidence_version_id"] = None
    assessed["assessment_sha256"] = None
    out = run(p, legal_role)
    assert out["blocked"]
    assert out["rows"][0]["comparison_state"] == "MATCHED"
    assert out["rows"][0]["state"] == "ASSESSMENT_NOT_SUPPORTED"
    assert "RETAINED_ASSESSMENT_DOCUMENT_MISSING" in out["rows"][0]["assessment_issues"]
    assert approval_error(out)


@pytest.mark.parametrize("legal_role", ["deductor", "deductee"])
def test_transaction_outside_declared_assessment_coverage_blocks_approval(legal_role):
    p = population(legal_role)
    p["expected" if legal_role == "deductor" else "certificate"][0]["assessment_period_end"] = (
        "2026-04-30"
    )
    out = run(p, legal_role)
    assert out["blocked"]
    assert "TRANSACTION_OUTSIDE_ASSESSED_COVERAGE" in out["rows"][0]["assessment_issues"]


def pooled_certificate_population():
    p = population("deductee")
    p["certificate"][0]["assessment_amount_limit"] = "150"
    for rows in p.values():
        rows.append({**rows[0], "id": rows[0]["id"] + "-2", "transaction_reference": "SYN-TX-2"})
    return p


def test_shared_certificate_limit_is_checked_across_transactions_not_per_row():
    out = run(pooled_certificate_population(), "deductee")
    assert out["blocked"] and len(out["rows"]) == 2
    assert all(
        "CERTIFICATE_SHARED_AMOUNT_LIMIT_EXCEEDED" in row["assessment_issues"]
        for row in out["rows"]
    )
    assert all(row["comparison_state"] == "MATCHED" for row in out["rows"])
    assert all(
        row["assessment_provenance"]["certificate_scope_used_amount"] == "200"
        for row in out["rows"]
    )


def test_equal_numeric_limits_with_different_decimal_scale_do_not_conflict():
    p = pooled_certificate_population()
    p["certificate"][0]["assessment_amount_limit"] = "200"
    p["certificate"][1]["assessment_amount_limit"] = "200.0"
    out = run(p, "deductee")
    assert not out["blocked"] and out["exception_count"] == 0


def test_certificate_scope_cannot_be_relabelled_per_line_to_increase_cap():
    p = pooled_certificate_population()
    p["certificate"][1]["assessment_amount_limit"] = "200"
    with pytest.raises(ValueError, match="Conflicting certificate scope"):
        run(p, "deductee")


def test_superseded_certificate_observation_does_not_consume_current_cap():
    p = population("deductee")
    p["certificate"][0]["assessment_amount_limit"] = "100"
    p["certificate"].append(
        {
            **p["certificate"][0],
            "id": "old-certificate",
            "source_version": "0",
            "record_status": "superseded",
            "amount": "900",
        }
    )
    out = run(p, "deductee")
    assert not out["blocked"] and out["rows"][0]["amounts"]["certificate"] == "100"


@pytest.mark.parametrize("workflow", ["india-withholding-liability", "india-withholding-credit"])
async def test_retained_pre_assessment_contract_results_cannot_feed_actions(workflow):
    from app.modules.intelligence.service import current

    obj = SimpleNamespace(tenant_id="tenant", kind="country-workflow", body={"workflow": workflow})
    assert not await current(None, SimpleNamespace(tenant_id="tenant"), obj)


@pytest.mark.parametrize(
    "field,value",
    [
        ("assessment_sha256", None),
        ("assessment_evidence_version_id", None),
        ("assessment_period_start", None),
        ("assessment_period_end", "2026-03-31"),
        ("assessment_amount_limit", "100"),
    ],
)
def test_incomplete_or_contradictory_rule_assessment_metadata_is_rejected(field, value):
    assessed = population()["expected"][0]
    assessed[field] = value
    with pytest.raises(ValueError):
        WithholdingRecord.model_validate(assessed)


def test_certificate_coverage_cannot_be_supplied_without_an_amount_limit():
    assessed = population("deductee")["certificate"][0]
    assessed["assessment_amount_limit"] = None
    with pytest.raises(ValueError, match="shared amount limit"):
        WithholdingRecord.model_validate(assessed)


@pytest.mark.parametrize("legal_role", ["deductor", "deductee"])
def test_rule_and_certificate_assessments_cannot_replace_each_other(legal_role):
    p = population(legal_role)
    assessed = p["expected" if legal_role == "deductor" else "certificate"][0]
    assessed["assessment_kind"] = "certificate" if legal_role == "deductor" else "rule"
    assessed["assessment_amount_limit"] = "1000" if legal_role == "deductor" else None
    out = run(p, legal_role)
    assert out["blocked"] and out["rows"][0]["comparison_state"] == "MATCHED"
    assert "ASSESSMENT_KIND_MISSING_OR_DIFFERENT" in out["rows"][0]["assessment_issues"]
