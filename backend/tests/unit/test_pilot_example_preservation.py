"""Unchanged synthetic examples retain their historical fixture hashes and bytes."""

import importlib.util
import json
from pathlib import Path

import pytest


def exporter(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "pilot_export", root / "scripts/export_country_pilot_examples.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "fixtures.py"
    source.write_text(
        "CASES = ["
        + repr(
            {
                "id": "RW-001",
                "country": "AE",
                "workflow": "synthetic",
                "sources": {},
                "expected": {"blocked": False},
                "parameters": {},
            }
        )
        + "]",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "SOURCE", source)
    monkeypatch.setattr(module, "DESTINATION", tmp_path / "examples")
    return module, source, tmp_path / "examples/UAE/RW-001.json"


def test_unchanged_cases_keep_original_bytes_when_fixture_file_evolves(tmp_path, monkeypatch):
    module, source, path = exporter(tmp_path, monkeypatch)
    module.export()
    before = path.read_bytes()
    original = json.loads(before)["source_fixture_sha256"]
    source.write_text(
        source.read_text(encoding="utf-8") + "\n# A later fixture source revision\n",
        encoding="utf-8",
    )
    module.export()
    catalog = json.loads((module.DESTINATION / "catalog.json").read_text(encoding="utf-8"))
    assert path.read_bytes() == before
    assert catalog["source_fixture_sha256"] != original
    assert catalog["cases"][0]["source_fixture_sha256"] == original


@pytest.mark.parametrize("change", ["case", "hash", "metadata"])
def test_different_case_or_unrecognized_metadata_is_never_overwritten(
    tmp_path, monkeypatch, change
):
    module, _, path = exporter(tmp_path, monkeypatch)
    module.export()
    document = json.loads(path.read_text(encoding="utf-8"))
    if change == "case":
        document["case"]["expected"]["blocked"] = True
    elif change == "hash":
        document["source_fixture_sha256"] = "invalid"
    else:
        document["unknown"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        module.export()
    assert path.read_bytes() == before
