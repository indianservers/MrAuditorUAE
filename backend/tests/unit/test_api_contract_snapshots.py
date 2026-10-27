"""Contracts expose real runtime entry points; snapshots are not workflow qualification."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.modules.country_workflows.schemas import ROW_TYPES
from app.modules.intelligence.schemas import OPERATIONS, JobInput

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "api_contract_export", ROOT / "scripts/export_api_contracts.py"
)
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def test_saved_contracts_match_current_runtime_models():
    assert export.outdated(ROOT, export.contracts()) == []


def test_rescan_and_workbook_contracts_are_discoverable():
    documents = export.contracts()
    api = documents["docs/phase-12/openapi.json"]
    route = api["paths"]["/api/v1/engagements/{eid}/audit/evidence-files/{rid}/{vid}/rescan"][
        "post"
    ]
    assert route["security"] and "201" in route["responses"]
    jobs = documents["docs/country-workflows/job-input-contracts.json"]
    assert (
        set(jobs["operations"])
        == set(OPERATIONS)
        == set(JobInput.model_json_schema()["properties"]["operation"]["enum"])
    )
    source = jobs["operations"]["workflow-source"]["payload_schema"]
    assert source["additionalProperties"] is False
    assert source["properties"]["expected_rows"]["maximum"] == 5000
    assert source["properties"]["workbook_sheet"]["anyOf"][0]["maxLength"] == 31
    assert "workbook_assessment" in source["properties"]
    assert jobs["runtime_validation_required"] is True
    assert set(jobs["source_rows"]) == set(ROW_TYPES)


def test_payload_definitions_are_self_contained():
    jobs = export.contracts()["docs/country-workflows/job-input-contracts.json"]

    def refs(value):
        if isinstance(value, dict):
            if "$ref" in value:
                yield value["$ref"]
            for child in value.values():
                yield from refs(child)
        elif isinstance(value, list):
            for child in value:
                yield from refs(child)

    schemas = [operation["payload_schema"] for operation in jobs["operations"].values()]
    for schema in [*schemas, *jobs["source_rows"].values()]:
        for ref in refs(schema):
            assert ref.startswith("#/$defs/")
            assert ref.removeprefix("#/$defs/") in schema["$defs"]


def test_checker_detects_missing_and_changed_files_without_overwriting(tmp_path):
    documents = {"snapshot.json": {"properties": {"workbook_sheet": {"type": "string"}}}}
    assert export.outdated(tmp_path, documents) == ["snapshot.json"]
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(documents["snapshot.json"]), encoding="utf-8")
    assert export.outdated(tmp_path, documents) == []
    changed = copy.deepcopy(documents)
    changed["snapshot.json"]["properties"] = {}
    before = path.read_bytes()
    assert export.outdated(tmp_path, changed) == ["snapshot.json"]
    assert path.read_bytes() == before


def test_check_cli_fails_closed_without_writing_missing_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "ROOT", tmp_path)
    monkeypatch.setattr(export, "contracts", lambda: {"missing.json": {"contract": "synthetic"}})
    monkeypatch.setattr(sys, "argv", ["export_api_contracts.py", "--check"])
    with pytest.raises(SystemExit, match="Stale API contract snapshots"):
        export.main()
    assert list(tmp_path.iterdir()) == []
