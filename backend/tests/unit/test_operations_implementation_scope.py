from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import operations_contracts as contracts


def test_reader_fingerprint_isolated_from_unrelated_calculations(tmp_path, monkeypatch):
    # Use synthetic files, never edit the live implementation to simulate a rollout.
    app = tmp_path / "app"
    core = app / "core/operations_contracts.py"
    core.parent.mkdir(parents=True)
    monkeypatch.setattr(contracts, "__file__", str(core))
    for name in contracts.SUPPORTING_TABLE_PATHS:
        target = app / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"reader implementation")
    original = contracts.supporting_table_hash()
    unrelated = app / "modules/ifrs/calculations.py"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(b"changed ECL arithmetic")
    assert contracts.supporting_table_hash() == original
    (app / "modules/ingestion/parser.py").write_bytes(b"changed numeric reader")
    assert contracts.supporting_table_hash() != original


def test_reader_library_version_is_part_of_fingerprint(monkeypatch):
    original = contracts.supporting_table_hash()
    monkeypatch.setattr(contracts, "version", lambda name: "different-release")
    assert contracts.supporting_table_hash() != original


@pytest.mark.parametrize(
    "contract,scope,kind,expected",
    [
        ("audit-operations/2", "supporting-table/1", "source-table", True),
        ("audit-operations/2", "supporting-table/1", "country-workflow", False),
        ("audit-operations/2", "user-chosen", "source-table", False),
        ("audit-operations/3", "supporting-table/1", "source-table", False),
        (None, "supporting-table/1", "source-table", False),
    ],
)
def test_scope_cannot_be_relabelled(contract, scope, kind, expected):
    saved = {
        "contract_version": contract,
        "kind": "source-table",
        "implementation_scope": scope,
        "implementation_sha256": contracts.supporting_table_hash(),
    }
    assert contracts.implementation_current(saved, kind) is expected


def test_legacy_receipts_keep_global_guard(monkeypatch):
    saved = {"contract_version": "audit-operations/1", "implementation_sha256": "original"}
    monkeypatch.setattr(contracts, "implementation_hash", lambda: "original")
    assert contracts.implementation_current(saved, "source-table")
    monkeypatch.setattr(contracts, "implementation_hash", lambda: "changed")
    assert not contracts.implementation_current(saved, "source-table")


@pytest.mark.asyncio
async def test_scoped_receipt_still_checks_entity_and_period():
    ctx = SimpleNamespace(tenant_id="tenant")
    eng = SimpleNamespace(id="engagement", entity_id="entity", period_id="period")
    entity = SimpleNamespace(version=2, functional_currency="AED")
    period = SimpleNamespace(start_date="2026-01-01", end_date="2026-12-31")
    db = SimpleNamespace(get=AsyncMock(side_effect=[entity, period]))
    saved = await contracts.receipt(db, ctx, kind="source-table", body={}, eng=eng)
    assert saved["contract_version"] == "audit-operations/2"
    obj = SimpleNamespace(
        kind="source-table", engagement_id=eng.id, body={"operations_execution": saved}
    )
    db.get.side_effect = [eng, entity, period]
    assert await contracts.current(db, ctx, obj)
    entity.version += 1
    db.get.side_effect = [eng, entity, period]
    assert not await contracts.current(db, ctx, obj)
    entity.version -= 1
    period.end_date = "2026-11-30"
    db.get.side_effect = [eng, entity, period]
    assert not await contracts.current(db, ctx, obj)


def country_tree(tmp_path, monkeypatch):
    app = tmp_path / "app"
    core = app / "core/operations_contracts.py"
    monkeypatch.setattr(contracts, "__file__", str(core))
    for name in contracts.COUNTRY_WORKFLOW_PATHS:
        path = app / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic shared runtime")
    for directory in ("country_workflows", "vat"):
        path = app / "modules" / directory
        path.mkdir(parents=True, exist_ok=True)
        (path / "engine.py").write_bytes(b"synthetic engine")
    return app


def test_shared_benefit_parameters_participate_in_country_freshness(tmp_path, monkeypatch):
    app = country_tree(tmp_path, monkeypatch)
    original = contracts.country_workflow_hash()
    (app / "modules/regulatory/benefit_profiles.py").write_bytes(b"changed profile contract")
    assert contracts.country_workflow_hash() != original


@pytest.mark.parametrize(
    "module",
    [
        "mt940_pages.py",
        "bank_clearance.py",
        "bank_outstanding_source.py",
        "india_gstr2b_source.py",
        "pack/scenarios.json",
    ],
)
def test_new_country_modules_are_covered_without_a_hand_maintained_file_list(
    tmp_path, monkeypatch, module
):
    app = country_tree(tmp_path, monkeypatch)
    original = contracts.country_workflow_hash()
    added = app / "modules/country_workflows" / module
    added.parent.mkdir(parents=True, exist_ok=True)
    added.write_bytes(b"synthetic first implementation")
    first = contracts.country_workflow_hash()
    assert first != original
    added.write_bytes(b"synthetic corrected implementation")
    assert contracts.country_workflow_hash() not in {original, first}
    added.unlink()
    assert contracts.country_workflow_hash() == original


def test_country_scope_covers_shared_readers_and_vat_but_ignores_unrelated_outputs(
    tmp_path, monkeypatch
):
    app = country_tree(tmp_path, monkeypatch)
    original = contracts.country_workflow_hash()
    for name in (
        "modules/ml/unrelated.py",
        "modules/country_workflows/__pycache__/reader.pyc",
        "modules/country_workflows/receipt.xml",
    ):
        path = app / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not executable country code")
    assert contracts.country_workflow_hash() == original
    for name in (
        "core/json_documents.py",
        "modules/vat/engine.py",
        "modules/intelligence/matching.py",
        "modules/ingestion/parser.py",
        "modules/reconciliation/service.py",
        "modules/regulatory/conversion.py",
    ):
        path = app / name
        saved = path.read_bytes()
        path.write_bytes(b"synthetic changed relevant runtime")
        assert contracts.country_workflow_hash() != original
        path.write_bytes(saved)
    assert contracts.country_workflow_hash() == original


def test_country_library_versions_are_part_of_saved_fingerprint(monkeypatch):
    original = contracts.country_workflow_hash()
    monkeypatch.setattr(contracts, "version", lambda name: "synthetic-upgraded-library")
    assert contracts.country_workflow_hash() != original


def test_country_fingerprint_reuses_only_the_active_transaction_snapshot(monkeypatch):
    calls = []
    monkeypatch.setattr(
        contracts, "country_workflow_hash", lambda: calls.append(1) or str(len(calls))
    )
    holder = SimpleNamespace(transaction=object())
    db = SimpleNamespace(
        info={}, sync_session=SimpleNamespace(get_transaction=lambda: holder.transaction)
    )
    assert contracts.country_workflow_fingerprint(db) == "1"
    assert contracts.country_workflow_fingerprint(db) == "1"
    assert len(calls) == 1
    holder.transaction = object()
    assert contracts.country_workflow_fingerprint(db) == "2"
    holder.transaction = None
    assert contracts.country_workflow_fingerprint(db) == "3"
    assert contracts.country_workflow_fingerprint(db) == "4"


@pytest.mark.parametrize("kind", ["workflow-source", "country-workflow"])
@pytest.mark.asyncio
async def test_country_receipts_use_server_scope_and_reject_scope_or_kind_relabelling(kind):
    ctx = SimpleNamespace(tenant_id="tenant")
    eng = SimpleNamespace(id="engagement", entity_id="entity", period_id="period")
    entity = SimpleNamespace(version=2, functional_currency="AED")
    period = SimpleNamespace(start_date="2026-01-01", end_date="2026-12-31")
    db = SimpleNamespace(get=AsyncMock(side_effect=[entity, period]))
    saved = await contracts.receipt(db, ctx, kind=kind, body={}, eng=eng)
    assert saved["contract_version"] == "audit-operations/2"
    assert saved["implementation_scope"] == "country-workflows/1"
    assert contracts.implementation_current(saved, kind)
    obj = SimpleNamespace(kind=kind, engagement_id=eng.id, body={"operations_execution": saved})
    db.get.side_effect = [eng, entity, period]
    assert await contracts.current(db, ctx, obj)
    entity.functional_currency = "INR"
    db.get.side_effect = [eng, entity, period]
    assert not await contracts.current(db, ctx, obj)
    assert not contracts.implementation_current(
        {**saved, "implementation_scope": "supporting-table/1"}, kind
    )
    assert not contracts.implementation_current({**saved, "kind": "source-table"}, kind)
    assert not contracts.implementation_current(saved, "source-table")
