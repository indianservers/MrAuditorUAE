"""Actual saved synthetic CSV/expectation comparison; no independent human claim."""

import json
import runpy
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
API = runpy.run_path(str(ROOT / "scripts/uae_synthetic_pilot.py"))
build, run, retained = API["build"], API["run"], API["retained"]
operating = runpy.run_path(str(ROOT / "scripts/uae_synthetic_pilot_cases.py"))["operating_cases"]


def test_all_authored_uae_pilot_cases_roundtrip_saved_sources_and_expectations(tmp_path):
    manifest = build(tmp_path)
    assert manifest["case_count"] == 123
    assert len(manifest["available_uae_workflows"]) == 53
    assert len(manifest["pilot_workflows"]) == 12
    report, path = run(tmp_path)
    assert report["passed"] == 123 and report["failed"] == 0
    assert report["expected_rejections"] == 10
    assert report["independent_professional_review"] is False
    assert path.is_file() and json.loads(path.read_bytes())["dataset_kind"] == API["KIND"]
    for case in manifest["cases"]:
        expected = json.loads(retained(tmp_path, case["expected_file"]["path"]).read_bytes())
        assert expected["expected_basis"] == "AUTHOR_DEFINED_LITERALS_NOT_ENGINE_OUTPUT"
        assert expected["independent_human_review"] is False


def test_incorrect_authored_expected_amount_is_a_comparison_failure(tmp_path):
    case = operating()[0]
    case["expected"]["assertions"][1]["decimal_equals"] = "255396.00"
    build(tmp_path, [case])
    report, _ = run(tmp_path)
    assert report["passed"] == 0 and report["failed"] == 1
    issue = report["results"][0]["issues"][0]
    assert issue["actual"] == "255395.00" and issue["expected"] == "255396.00"


@pytest.mark.parametrize("role", ["source", "expected"])
def test_changed_original_file_is_detected_before_comparison(tmp_path, role):
    manifest = build(tmp_path, [operating()[0]])
    entry = manifest["cases"][0]
    record = (
        next(iter(entry["source_files"].values())) if role == "source" else entry["expected_file"]
    )
    p = retained(tmp_path, record["path"])
    p.write_bytes(p.read_bytes() + b" ")
    report, _ = run(tmp_path)
    assert report["failed"] == 1 and report["passed"] == 0
    assert "original bytes differ" in report["results"][0]["error"]


def test_originals_are_not_replaced_by_regeneration(tmp_path):
    cases = [operating()[0]]
    manifest = build(tmp_path, cases)
    p = retained(tmp_path, manifest["cases"][0]["expected_file"]["path"])
    original = p.read_bytes()
    build(tmp_path, cases)
    assert p.read_bytes() == original
    changed = deepcopy(cases)
    changed[0]["expected"]["exceptions"] = 99
    with pytest.raises(FileExistsError, match="Preserve the original"):
        build(tmp_path, changed)
    assert p.read_bytes() == original


def test_other_country_and_real_pilot_paths_are_rejected(tmp_path):
    for name in [
        "pilot-data/India/redacted-inputs/real.csv",
        "pilot-data/UAE/redacted-inputs/client.csv",
        "pilot-data/UAE/redacted-inputs/" + API["DATASET"] + "/../private.csv",
    ]:
        with pytest.raises(ValueError):
            retained(tmp_path, name)
    wrong = operating()[0]
    wrong["country"] = "IN"
    with pytest.raises(ValueError, match="UAE synthetic"):
        build(tmp_path, [wrong])


def test_declared_damaged_stock_reaches_condition_review_without_losing_nrv():
    from app.modules.country_workflows.schemas import Stock

    row = operating()[11]["sources"]["count"][1]
    assert row["condition"] == "damaged"
    parsed = Stock.model_validate(row)
    assert parsed.condition == "damaged" and str(parsed.unit_nrv) == "320.00"
