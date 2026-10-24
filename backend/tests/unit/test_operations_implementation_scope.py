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
