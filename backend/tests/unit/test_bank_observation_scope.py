"""Year-end account evidence coverage is separate from payment observation dates."""

import uuid
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.bank_observation_scope import CONTRACT, saved_scope
from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import WorkflowInput
from app.modules.intelligence.service import current
from tests.unit.test_bank_accounts import parameters, population, run
from tests.unit.test_country_workflows import parsed
from tests.unit.test_msme_tax import annual_population


def coverage(**changes):
    return {
        **dict(
            as_of="2027-03-31",
            bank_observation_from="2026-03-01",
            bank_observation_through="2027-04-05",
            bank_observation_assessment="Assessed retained register, ledger and bank evidence covering original and subsequent payment dates",
        ),
        **changes,
    }


def account(country="IN"):
    rows = population(country)
    for role in rows:
        rows[role][0].update(
            account="SYNTHETIC-ACCOUNT", valid_from="2026-03-01", valid_through="2027-04-05"
        )
    return run(rows, country, account="SYNTHETIC-ACCOUNT", **coverage())


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_explicit_cross_year_document_window_keeps_annual_cutoff_and_no_authentication(country):
    result = account(country)
    assert not result["blocked"] and result["as_of"] == "2027-03-31"
    assert result["bank_observation_scope"]["through"] == "2027-04-05"
    assert result["bank_observation_scope"]["contract"] == CONTRACT
    assert saved_scope(result) == result["bank_observation_scope"]
    assert result["bank_authentication_status"] == "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON"


@pytest.mark.parametrize(
    "changes",
    [
        {"bank_observation_from": None},
        {"bank_observation_through": None},
        {"bank_observation_assessment": "   "},
        {"bank_observation_from": "2027-04-01"},
        {"bank_observation_through": "2027-03-30"},
        {"bank_observation_from": "1900-01-01"},
        {"bank_observation_through": "2027-04-05T00:00:00"},
        {"bank_observation_from": True},
    ],
)
def test_incomplete_reversed_or_noncalendar_windows_are_rejected(changes):
    with pytest.raises(ValidationError):
        parameters("IN", **coverage(**changes))


@pytest.mark.parametrize("role", ["register", "ledger", "bank"])
def test_each_document_must_cover_the_full_window_and_failure_stays_a_current_exception(role):
    rows = population("IN")
    for r in rows.values():
        r[0].update(valid_from="2026-03-01", valid_through="2027-04-05")
    rows[role][0]["valid_through"] = "2027-03-31"
    result = run(rows, "IN", **coverage())
    assert result["blocked"] and saved_scope(result)
    assert (
        "ACCOUNT_EVIDENCE_OUTSIDE_VALIDITY"
        in next(r for r in result["rows"] if r["source_role"] == role)["exceptions"]
    )
    assert "Resolve missing evidence" in approval_error(result)


def tax_request():
    from app.modules.country_workflows.msme_tax_schemas import ROLES
    from app.modules.country_workflows.schemas import ROW_TYPES

    data, tables = annual_population()
    request = WorkflowInput(
        workflow="india-msme-annual-tax",
        source_ids={r: uuid.uuid4() for r in ROLES},
        title="SYNTHETIC linked annual tax",
        rationale="Independent original bank and full account coverage",
        bank_account_review_id=uuid.uuid4(),
        bank_account_scope_assessment="Assessed full original and post-year account coverage",
        **vars(data),
    )
    sources = {
        role: parsed(
            kind, [ROW_TYPES[kind].model_validate(r).model_dump(mode="json") for r in tables[role]]
        )
        for role, kind in ROLES.items()
    }
    return request, sources


def test_yearend_account_review_links_postyear_tax_payments_without_rewriting_sources():
    data, sources = tax_request()
    review = account()
    review["review_status"] = "REVIEWED"
    original = deepcopy(sources)
    receipt = dict(type="event", id=str(data.bank_account_review_id), version=2, sha256="a" * 64)
    result = calculate(data, "IN", sources, bank_account_review=(review, receipt))
    assert result["net_expected_tax_adjustment"] == "-35" and not result["blocked"]
    assert sources == original
    link = result["bank_account_evidence"]
    assert link["review_as_of"] == "2027-03-31" and link["window_end"] == "2027-04-05"
    assert link["observation_scope"]["through"] == "2027-04-05"
    assert link["status"] == "REVIEWED_ACCOUNT_DOCUMENTS_LINKED"


@pytest.mark.parametrize("fault", ["end", "start", "cutoff", "contract", "missing", "noncanonical"])
def test_wrong_scope_or_legacy_account_review_cannot_authorize_postyear_observations(fault):
    data, sources = tax_request()
    review = account()
    review["review_status"] = "REVIEWED"
    if fault == "end":
        review["bank_observation_scope"]["through"] = "2027-04-04"
    elif fault == "start":
        review["bank_observation_scope"]["from"] = "2026-04-01"
    elif fault == "cutoff":
        review["as_of"] = "2027-03-30"
    elif fault == "contract":
        review["bank_observation_scope"]["contract"] = "old"
    elif fault == "missing":
        review.pop("bank_observation_scope")
    else:
        review["bank_observation_scope"]["through"] = "20270405"
    receipt = dict(type="event", id=str(data.bank_account_review_id), version=2, sha256="a" * 64)
    with pytest.raises(ValueError):
        calculate(data, "IN", sources, bank_account_review=(review, receipt))


@pytest.mark.parametrize("fault", ["contract", "missing", "parameters"])
async def test_malformed_new_scope_is_stale_and_cannot_be_approved_but_legacy_scope_is_preserved(
    fault,
):
    body = account()
    if fault == "contract":
        body["bank_observation_scope"]["contract"] = "old"
    elif fault == "missing":
        body.pop("bank_observation_scope")
    else:
        body["parameters"]["bank_observation_through"] = "2027-04-06"
    assert "Regenerate complete account" in approval_error(body)
    tenant = uuid.uuid4()
    db = AsyncMock()
    assert not await current(
        db,
        SimpleNamespace(tenant_id=tenant),
        SimpleNamespace(tenant_id=tenant, kind="country-workflow", body=body, dependencies=[]),
    )
    db.get.assert_not_awaited()
    legacy = run()
    assert saved_scope(legacy) is None


def test_observation_fields_do_not_leak_into_other_workflows():
    data, _ = tax_request()
    with pytest.raises(ValidationError):
        WorkflowInput(
            **{**data.model_dump(), **{k: v for k, v in coverage().items() if k != "as_of"}}
        )


def test_uae_subsequent_clearance_reuses_explicit_account_window_at_original_cutoff():
    from tests.unit.native_source_examples import iban
    from tests.unit.test_bank_clearance import population as clearance_population

    rows = population("AE")
    for r in rows.values():
        r[0]["account"] = "BANK-1"
    review = run(
        rows,
        "AE",
        account="BANK-1",
        as_of="2026-06-30",
        bank_observation_from="2026-06-01",
        bank_observation_through="2026-08-31",
        bank_observation_assessment="Assessed bank documents covering the financial cutoff and all later clearance observations",
    )
    review["review_status"] = "REVIEWED"
    populations = clearance_population()
    populations["statement"][0]["account"] = iban()
    types = {
        "outstanding": "bank-outstanding",
        "statement": "transactions",
        "allocations": "bank-clearances",
    }
    sources = {role: parsed(types[role], r) for role, r in populations.items()}
    rid = uuid.uuid4()
    data = WorkflowInput(
        workflow="bank-subsequent-clearance",
        source_ids={role: uuid.uuid4() for role in sources},
        account="BANK-1",
        currency="AED",
        as_of="2026-06-30",
        review_through="2026-08-31",
        title="SYNTHETIC subsequent review",
        rationale="Independent account scope over original and subsequent dates",
        bank_account_review_id=rid,
        bank_account_scope_assessment="Assessed original account number and subsequent clearance window",
    )
    result = calculate(
        data,
        "AE",
        sources,
        bank_account_review=(review, dict(type="event", id=str(rid), version=2, sha256="a" * 64)),
    )
    assert result["bank_account_evidence"]["review_as_of"] == "2026-06-30"
    assert result["bank_account_evidence"]["window_end"] == "2026-08-31"
    assert result["bank_account_evidence"]["account_label_mapping_applied"]
    assert sources["statement"]["rows"][0]["account"] == iban()


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_saved_coverage_examples_preserve_original_bytes_and_country_scope(country):
    import hashlib
    import json
    from pathlib import Path

    from app.modules.country_workflows.schemas import SourceInput
    from app.modules.country_workflows.sources import parse_csv

    root = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-bank-observation"
    )
    manifest = json.loads((root / "controls.json").read_text(encoding="utf-8"))
    assert manifest["synthetic"] and not manifest["qualified_real_client"]
    case = manifest["cases"][country]
    sources = {}
    for role, spec in case["files"].items():
        raw = (root / spec["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == spec["sha256"]
        source = SourceInput(
            evidence_version_id=uuid.uuid4(),
            table_type=spec["table_type"],
            label="SYNTHETIC " + role,
            expected_rows=spec["expected_rows"],
            control_totals=spec["control_totals"],
        )
        sources[role] = parse_csv(raw, source)
    data = WorkflowInput(**case["parameters"], source_ids={role: uuid.uuid4() for role in sources})
    result = calculate(data, country, sources)
    for key in ("blocked", "exception_count", "as_of", "bank_authentication_status"):
        assert result[key] == case["expected"][key]
    assert result["bank_observation_scope"]["through"] == case["expected"]["coverage_through"]
    assert all(
        row["owner_country"] == country and row["owner_identifier"] == "00123"
        for row in result["rows"]
    )
