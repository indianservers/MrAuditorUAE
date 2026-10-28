"""Synthetic temporary files test mechanics only; no client validation is claimed."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest

API = runpy.run_path(str(Path(__file__).resolve().parents[3] / "scripts/validate_country_pilot.py"))
validate = API["validate"]
InvalidPilot = API["InvalidPilot"]


def saved(path, data, raw=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = data if raw else json.dumps(data).encode()
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


@pytest.fixture
def pilot(tmp_path):
    folder = tmp_path / "UAE"
    inputs = {
        "redacted-inputs/SYNTHETIC.csv": saved(
            folder / "redacted-inputs/SYNTHETIC.csv", b"synthetic", True
        )
    }
    manifest = {
        "dataset_kind": "REAL_CLIENT_PILOT",
        "country": "AE",
        "status": "READY_FOR_LOCAL_COMPARISON",
        "review_status": "INDEPENDENT_REVIEW_RECORDED",
        "client_reference": "SYNTHETIC CLIENT",
        "workflow": "bank-brs",
        "period_start": "2026-01-01",
        "period_end": "2026-12-31",
        "consent_or_authorized_use_reference": "SYNTHETIC authorization",
        "expected_prepared_by": "SYNTHETIC external preparer",
        "actual_prepared_by": "SYNTHETIC operator",
        "independent_reviewer": "SYNTHETIC reviewer",
        "expected_basis": "INDEPENDENT_EXTERNAL_CALCULATION",
        "input_files": list(inputs),
        "input_sha256": inputs,
        "expected_result_file": "independent-expected-results/SYNTHETIC.json",
        "actual_result_file": "review-records/SYNTHETIC-actual.json",
        "review_record_file": "review-records/SYNTHETIC-review.json",
    }
    for role in ("expected_result", "actual_result"):
        manifest[role + "_sha256"] = saved(
            folder / manifest[role + "_file"], {"amount": "100.00", "missing": None}
        )
    review = {
        key: manifest[key]
        for key in [
            "country",
            "workflow",
            "client_reference",
            "period_start",
            "period_end",
            "input_sha256",
            "expected_result_sha256",
            "actual_result_sha256",
            "independent_reviewer",
        ]
    }
    review.update(
        decision="COMPARISON_AUTHORIZED",
        review_date="2026-01-01",
        assessment="SYNTHETIC independently retained scope assessment",
    )
    manifest["review_record_sha256"] = saved(folder / manifest["review_record_file"], review)
    path = folder / "review-records/SYNTHETIC-manifest.json"
    saved(path, manifest)
    return folder, path, manifest, review


def test_exact_separate_file_match_never_claims_professional_qualification(pilot):
    folder, path, _, _ = pilot
    result = validate(path, folder)
    assert result["results_equal"] is True
    assert result["status"] == "DECLARED_EVIDENCE_MATCHES"
    assert result["professional_validation"] == "NOT_ESTABLISHED_BY_THIS_TOOL"
    assert "SYNTHETIC CLIENT" not in json.dumps(result)


@pytest.mark.parametrize(
    "fault,code",
    [
        ("template", "REAL_PILOT_DECLARATION_REQUIRED"),
        ("unreviewed", "REVIEW_NOT_RECORDED"),
        ("same-person", "INDEPENDENT_PREPARER_AND_REVIEWER_REQUIRED"),
        ("wrong-country", "WORKFLOW_COUNTRY_MISMATCH"),
        ("tampered-input", "INPUT_HASH_MISMATCH"),
        ("tampered-expected", "RESULT_OR_REVIEW_HASH_MISMATCH"),
        ("review-scope", "REVIEW_SCOPE_OR_HASH_MISMATCH"),
        ("future-review", "FUTURE_REVIEW_DATE"),
        ("unhashed-input", "INPUT_HASH_POPULATION_MISMATCH"),
        ("traversal", "EVIDENCE_CATEGORY_OR_PATH_INVALID"),
        ("windows-path", "INVALID_RELATIVE_PATH"),
        ("unreviewed-decision", "REVIEW_DECISION_REQUIRED"),
    ],
)
def test_incomplete_or_tampered_pilots_fail_closed(pilot, fault, code):
    folder, path, manifest, review = pilot
    if fault == "template":
        manifest["dataset_kind"] = "REAL_CLIENT_PILOT_TEMPLATE"
    elif fault == "unreviewed":
        manifest["review_status"] = "NOT_REVIEWED"
    elif fault == "same-person":
        manifest["independent_reviewer"] = manifest["expected_prepared_by"].upper()
    elif fault == "wrong-country":
        manifest["workflow"] = "india-msme-payment-timing"
    elif fault == "tampered-input":
        (folder / manifest["input_files"][0]).write_bytes(b"changed")
    elif fault == "tampered-expected":
        (folder / manifest["expected_result_file"]).write_bytes(b"{}")
    elif fault == "review-scope":
        review["period_start"] = "2025-01-01"
    elif fault == "future-review":
        review["review_date"] = "9999-01-01"
    elif fault == "unhashed-input":
        manifest["input_sha256"] = {}
    elif fault == "traversal":
        manifest["expected_result_file"] = (
            "independent-expected-results/../review-records/SYNTHETIC-actual.json"
        )
    elif fault == "windows-path":
        manifest["expected_result_file"] = "C:/outside.json"
    elif fault == "unreviewed-decision":
        review["decision"] = "DRAFT"
    manifest["review_record_sha256"] = saved(folder / manifest["review_record_file"], review)
    saved(path, manifest)
    with pytest.raises(InvalidPilot, match=code):
        validate(path, folder)


@pytest.mark.parametrize(
    "expected,actual,matches",
    [
        ({"a": "1"}, {"a": 1}, False),
        ({"a": None}, {"a": 0}, False),
        ({"a": True}, {"a": 1}, False),
        ({"a": "100.00"}, {"a": "100.01"}, False),
        ([1, 2], [2, 1], False),
        ({"a": 1}, {"a": 1, "b": 0}, False),
        ({"a": 1.0}, {"a": 1}, True),
    ],
)
def test_exact_comparison_preserves_missing_type_order_and_amounts(
    pilot, expected, actual, matches
):
    folder, path, manifest, review = pilot
    for role, value in [("expected_result", expected), ("actual_result", actual)]:
        manifest[role + "_sha256"] = saved(folder / manifest[role + "_file"], value)
        review[role + "_sha256"] = manifest[role + "_sha256"]
    manifest["review_record_sha256"] = saved(folder / manifest["review_record_file"], review)
    saved(path, manifest)
    assert validate(path, folder)["results_equal"] is matches


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_invalid_json_cannot_become_matching_evidence(raw):
    with pytest.raises(InvalidPilot):
        API["json_document"](raw)


def test_original_templates_remain_incomplete():
    root = Path(__file__).resolve().parents[3] / "pilot-data"
    for country in ("UAE", "India"):
        with pytest.raises(InvalidPilot, match="REAL_PILOT_DECLARATION_REQUIRED"):
            validate(root / country / "pilot-manifest.template.json", root / country)


@pytest.mark.parametrize(
    "country,workflow", [("AE", "bank-brs"), ("IN", "india-msme-payment-timing")]
)
def test_cli_returns_zero_only_for_matching_declared_evidence(pilot, country, workflow):
    import subprocess
    import sys

    folder, path, manifest, review = pilot
    manifest.update(country=country, workflow=workflow)
    review.update(country=country, workflow=workflow)
    manifest["review_record_sha256"] = saved(folder / manifest["review_record_file"], review)
    saved(path, manifest)
    script = Path(__file__).resolve().parents[3] / "scripts/validate_country_pilot.py"
    result = subprocess.run(
        [sys.executable, str(script), str(path), "--country-root", str(folder)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    body = json.loads(result.stdout)
    assert body["country"] == country and body["results_equal"] is True
    assert body["legal_or_production_qualification"] == "NOT_ESTABLISHED"
    assert "SYNTHETIC" not in result.stdout
    assert len(body["validator_sha256"]) == 64
    if country == "AE":
        manifest["actual_result_sha256"] = saved(
            folder / manifest["actual_result_file"], {"amount": "99"}
        )
        review["actual_result_sha256"] = manifest["actual_result_sha256"]
        manifest["review_record_sha256"] = saved(folder / manifest["review_record_file"], review)
        saved(path, manifest)
        result = subprocess.run(
            [sys.executable, str(script), str(path), "--country-root", str(folder)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1 and json.loads(result.stdout)["results_equal"] is False
        saved(path, {**manifest, "review_status": "NOT_REVIEWED"})
        result = subprocess.run(
            [sys.executable, str(script), str(path), "--country-root", str(folder)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 2 and json.loads(result.stdout)["code"] == "REVIEW_NOT_RECORDED"


def test_hardlinked_result_roles_cannot_self_corroborate(pilot):
    import os

    folder, path, manifest, _ = pilot
    actual = folder / manifest["actual_result_file"]
    actual.unlink()
    os.link(folder / manifest["expected_result_file"], actual)
    with pytest.raises(InvalidPilot, match="DUPLICATE_EVIDENCE_ROLE"):
        validate(path, folder)


def test_file_and_aggregate_size_limits_are_enforced(pilot, monkeypatch):
    folder, path, _, _ = pilot
    monkeypatch.setitem(validate.__globals__, "MAX_TOTAL_BYTES", 1)
    with pytest.raises(InvalidPilot, match="PILOT_TOTAL_BYTE_BOUND_EXCEEDED"):
        validate(path, folder)
    monkeypatch.setitem(validate.__globals__, "MAX_BYTES", 1)
    with pytest.raises(InvalidPilot, match="EVIDENCE_FILE_TOO_LARGE"):
        validate(path, folder)


@pytest.mark.parametrize("raw", [b"1e999999999999999999999999", b'{"amount":0,"amount":1}'])
def test_extreme_or_ambiguous_numbers_fail_closed(raw):
    with pytest.raises(InvalidPilot):
        API["json_document"](raw)


def test_result_bytes_count_towards_the_aggregate_bound(pilot, monkeypatch):
    folder, path, manifest, _ = pilot
    budget = path.stat().st_size + (folder / manifest["input_files"][0]).stat().st_size
    monkeypatch.setitem(validate.__globals__, "MAX_TOTAL_BYTES", budget)
    with pytest.raises(InvalidPilot, match="PILOT_TOTAL_BYTE_BOUND_EXCEEDED"):
        validate(path, folder)


def test_hardlinked_inputs_do_not_inflate_the_retained_population(pilot):
    import os

    folder, path, manifest, _ = pilot
    original = manifest["input_files"][0]
    duplicate = "redacted-inputs/SYNTHETIC-copy.csv"
    os.link(folder / original, folder / duplicate)
    manifest["input_files"].append(duplicate)
    manifest["input_sha256"][duplicate] = manifest["input_sha256"][original]
    saved(path, manifest)
    with pytest.raises(InvalidPilot, match="DUPLICATE_INPUT_FILE"):
        validate(path, folder)
