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


def test_explicit_new_version_preserves_historical_examples(tmp_path, monkeypatch):
    module, source, path = exporter(tmp_path, monkeypatch)
    module.export()
    before = path.read_bytes()
    source.write_text(
        source.read_text(encoding="utf-8").replace("'blocked': False", "'blocked': True"),
        encoding="utf-8",
    )
    destination = tmp_path / "pilot-data" / "synthetic-examples" / "versions" / "corrected-currency"
    module.export(destination)
    assert path.read_bytes() == before
    assert (
        json.loads((destination / "UAE/RW-001.json").read_text(encoding="utf-8"))["case"][
            "expected"
        ]["blocked"]
        is True
    )
    with pytest.raises(ValueError):
        module.export(tmp_path / "outside")


def test_synthetic_exports_cannot_enter_real_pilot_input_folders(tmp_path, monkeypatch):
    module, _, _ = exporter(tmp_path, monkeypatch)
    destination = tmp_path / "pilot-data" / "UAE" / "redacted-inputs"
    with pytest.raises(ValueError):
        module.export(destination)
    assert not destination.exists()


def test_source_snapshots_preserve_original_line_endings_and_history(tmp_path, monkeypatch):
    module, source, path = exporter(tmp_path, monkeypatch)
    source.write_bytes(
        (source.read_bytes() + b"\n").replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    )
    original = source.read_bytes()
    module.export()
    first = json.loads(path.read_bytes())["source_fixture_sha256"]
    retained = module.DESTINATION / "fixture-sources" / (first + ".txt")
    assert retained.read_bytes() == original and b"\r\n" in original
    source.write_bytes(original + b"# A later source version\r\n")
    module.export()
    catalog = json.loads((module.DESTINATION / "catalog.json").read_bytes())
    assert len(catalog["source_fixture_snapshots"]) == 2
    assert {item["status"] for item in catalog["source_fixture_snapshots"]} == {"RETAINED"}
    assert retained.read_bytes() == original
    assert json.loads(path.read_bytes())["source_fixture_sha256"] == first


def test_tampered_source_snapshot_is_never_replaced(tmp_path, monkeypatch):
    module, _, path = exporter(tmp_path, monkeypatch)
    module.export()
    original = path.read_bytes()
    catalog_path = module.DESTINATION / "catalog.json"
    original_catalog = catalog_path.read_bytes()
    item = json.loads(original_catalog)["source_fixture_snapshots"][0]
    snapshot = module.DESTINATION / item["file"]
    snapshot.write_bytes(b"changed retained source")
    with pytest.raises(FileExistsError, match="fixture-source snapshot"):
        module.export()
    assert snapshot.read_bytes() == b"changed retained source"
    assert path.read_bytes() == original and catalog_path.read_bytes() == original_catalog


def test_legacy_fixture_hash_without_original_bytes_remains_explicit(tmp_path, monkeypatch):
    module, source, path = exporter(tmp_path, monkeypatch)
    module.export()
    historical = json.loads(path.read_bytes())["source_fixture_sha256"]
    (module.DESTINATION / "fixture-sources" / (historical + ".txt")).unlink()
    source.write_bytes(source.read_bytes() + b"\n# New source version\n")
    module.export()
    catalog = json.loads((module.DESTINATION / "catalog.json").read_bytes())
    item = next(s for s in catalog["source_fixture_snapshots"] if s["sha256"] == historical)
    assert item["status"] == "HISTORICAL_BYTES_NOT_RETAINED" and item["file"] is None
    assert json.loads(path.read_bytes())["source_fixture_sha256"] == historical
