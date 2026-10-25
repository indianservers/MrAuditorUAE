"""Artifact binding, evidence integrity and real CLI failures without deployment."""

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/release_gate.py"
spec = importlib.util.spec_from_file_location("release_gate", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
RELEASE = {
    "commit": "a" * 40,
    "image_digest": "sha256:" + "b" * 64,
    "environment": "synthetic-staging",
}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(root):
    raw = root / "proof/executed.txt"
    raw.parent.mkdir(parents=True)
    raw.write_text("SYNTHETIC executed proof only", encoding="utf-8")
    entries = {}
    for name in gate.REQUIRED:
        receipt = {
            "schema_version": 1,
            "gate": name,
            "release": RELEASE,
            "outcome": "PASS",
            "executed_at": datetime.now(UTC).isoformat(),
            "evidence": [
                {
                    "path": "proof/executed.txt",
                    "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                }
            ],
        }
        digest = save(root / f"proof/{name}.json", receipt)
        entries[name] = {
            "status": "VERIFIED",
            "open_blocker": False,
            "evidence": f"proof/{name}.json",
            "evidence_sha256": digest,
        }
    return {
        "schema_version": 2,
        "scope": "SYNTHETIC test fixture, not production approval",
        "release": RELEASE,
        "gates": entries,
    }


def assess(data, root, **changes):
    args = dict(
        root=root,
        expected_commit=RELEASE["commit"],
        expected_image_digest=RELEASE["image_digest"],
        expected_environment=RELEASE["environment"],
    )
    args.update(changes)
    return gate.assess(data, **args)


def mutate_receipt(root, data, change):
    item = data["gates"]["deployment_rollback"]
    path = root / item["evidence"]
    value = json.loads(path.read_text(encoding="utf-8"))
    change(value)
    item["evidence_sha256"] = save(path, value)


def test_only_artifact_bound_executed_receipts_can_pass(tmp_path):
    data = fixture(tmp_path)
    result = assess(data, tmp_path)
    assert result["decision"] == "GO"
    assert result["blocked_gates"] == []
    assert result["release"] == RELEASE
    assert set(gate.evaluate({})) == gate.REQUIRED
    assert (
        set(
            gate.evaluate(
                {
                    "gates": {
                        name: {"status": "VERIFIED", "evidence": "anything.json"}
                        for name in gate.REQUIRED
                    }
                }
            )
        )
        == gate.REQUIRED
    )


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "status",
        "open_blocker",
        "string_blocker",
        "missing_digest",
        "receipt_tampered",
        "raw_tampered",
        "empty_raw",
        "escaping_path",
        "absolute_path",
        "unknown_gate_field",
    ],
)
def test_gate_labels_cannot_hide_missing_blocking_or_modified_evidence(tmp_path, change):
    data = fixture(tmp_path)
    entry = data["gates"]["deployment_rollback"]
    if change == "missing":
        del data["gates"]["deployment_rollback"]
    elif change == "status":
        entry["status"] = "NOT_TESTED"
    elif change == "open_blocker":
        entry["open_blocker"] = True
    elif change == "string_blocker":
        entry["open_blocker"] = "false"
    elif change == "missing_digest":
        entry.pop("evidence_sha256")
    elif change == "receipt_tampered":
        (tmp_path / entry["evidence"]).write_text("{}", encoding="utf-8")
    elif change == "raw_tampered":
        (tmp_path / "proof/executed.txt").write_text("Modified proof", encoding="utf-8")
    elif change == "empty_raw":
        (tmp_path / "proof/executed.txt").write_bytes(b"")
    elif change == "escaping_path":
        entry["evidence"] = "../outside.json"
    elif change == "absolute_path":
        entry["evidence"] = str((tmp_path / entry["evidence"]).resolve())
    elif change == "unknown_gate_field":
        entry["verified_override"] = True
    result = assess(data, tmp_path)
    assert result["decision"] == "NO-GO"
    assert "deployment_rollback" in result["blocked_gates"]


@pytest.mark.parametrize(
    "change",
    [
        "other_gate",
        "other_commit",
        "other_image",
        "other_environment",
        "partial",
        "no_artifacts",
        "missing_artifact_hash",
        "naive_timestamp",
        "future_timestamp",
        "invalid_timestamp",
        "duplicate_artifact",
        "self_reference",
        "malformed_receipt",
    ],
)
def test_receipts_are_bound_to_exact_target_and_actual_retained_execution(tmp_path, change):
    data = fixture(tmp_path)

    def mutate(value):
        value["release"] = copy.deepcopy(value["release"])
        if change == "other_gate":
            value["gate"] = "financial_accuracy"
        elif change == "other_commit":
            value["release"]["commit"] = "c" * 40
        elif change == "other_image":
            value["release"]["image_digest"] = "sha256:" + "d" * 64
        elif change == "other_environment":
            value["release"]["environment"] = "another-region"
        elif change == "partial":
            value["outcome"] = "PARTIAL"
        elif change == "no_artifacts":
            value["evidence"] = []
        elif change == "missing_artifact_hash":
            value["evidence"][0].pop("sha256")
        elif change == "naive_timestamp":
            value["executed_at"] = "2026-10-25T00:00:00"
        elif change == "future_timestamp":
            value["executed_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        elif change == "invalid_timestamp":
            value["executed_at"] = "not-an-executed-date"
        elif change == "duplicate_artifact":
            value["evidence"] *= 2
        elif change == "self_reference":
            value["evidence"][0]["path"] = "proof/deployment_rollback.json"
        elif change == "malformed_receipt":
            value["schema_version"] = True

    mutate_receipt(tmp_path, data, mutate)
    result = assess(data, tmp_path)
    assert result["decision"] == "NO-GO"
    assert result["blocked_gates"] == ["deployment_rollback"]


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_commit": "c" * 40},
        {"expected_image_digest": "sha256:" + "c" * 64},
        {"expected_environment": "production"},
        {"expected_commit": "main"},
        {"expected_image_digest": "latest"},
        {"expected_environment": ""},
    ],
)
def test_selected_artifact_is_independent_of_manifest_labels(tmp_path, changes):
    result = assess(fixture(tmp_path), tmp_path, **changes)
    assert result["decision"] == "NO-GO"
    assert set(result["blocked_gates"]) == gate.REQUIRED


def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected():
    for raw in (b'{"outcome":"FAIL","outcome":"PASS"}', b'{"value":NaN}', b'{"value":Infinity}'):
        with pytest.raises(ValueError):
            gate.read_json(raw)


def test_real_cli_uses_selected_manifest_and_returns_nonzero_on_mismatch(tmp_path):
    data = fixture(tmp_path)
    script = tmp_path / "scripts/release_gate.py"
    script.parent.mkdir()
    shutil.copyfile(SCRIPT, script)
    save(tmp_path / "proof/release.json", data)
    args = [
        sys.executable,
        str(script),
        "proof/release.json",
        "--commit",
        RELEASE["commit"],
        "--image-digest",
        RELEASE["image_digest"],
        "--environment",
        RELEASE["environment"],
    ]
    ok = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert ok.returncode == 0 and json.loads(ok.stdout)["decision"] == "GO"
    args[-1] = "another-environment"
    mismatch = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert mismatch.returncode == 1 and json.loads(mismatch.stdout)["decision"] == "NO-GO"
    args[2] = "proof/missing.json"
    missing = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert missing.returncode == 1 and json.loads(missing.stdout)["decision"] == "NO-GO"


def test_manual_workflow_passes_inputs_as_quoted_environment_arguments():
    import yaml

    workflow = yaml.load(
        (SCRIPT.parent.parent / ".github/workflows/release-gate.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    step = next(
        item
        for item in workflow["jobs"]["evidence"]["steps"]
        if item.get("name") == "Validate reviewed artifact evidence"
    )
    assert step["env"] == {
        "RELEASE_EVIDENCE_MANIFEST": "${{ inputs.evidence_artifact }}",
        "RELEASE_SOURCE_COMMIT": "${{ inputs.source_commit }}",
        "RELEASE_IMAGE_DIGEST": "${{ inputs.image_digest }}",
        "RELEASE_TARGET_ENVIRONMENT": "${{ inputs.target_environment }}",
    }
    assert '"$RELEASE_EVIDENCE_MANIFEST"' in step["run"]
    for flag, name in (
        ("--commit", "RELEASE_SOURCE_COMMIT"),
        ("--image-digest", "RELEASE_IMAGE_DIGEST"),
        ("--environment", "RELEASE_TARGET_ENVIRONMENT"),
    ):
        assert f'{flag} "${name}"' in step["run"]
    assert "${{" not in step["run"]


def test_utc_z_execution_timestamp_is_accepted(tmp_path):
    data = fixture(tmp_path)
    mutate_receipt(
        tmp_path,
        data,
        lambda value: value.update(
            executed_at=datetime.now(UTC).isoformat().replace("+00:00", "Z")
        ),
    )
    assert assess(data, tmp_path)["decision"] == "GO"


def test_json_reads_are_bounded_before_parsing(tmp_path):
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (gate.MAX_JSON + 100))
    content = gate.small_file(path)
    assert len(content) == gate.MAX_JSON + 1
    with pytest.raises(ValueError, match="exceeds"):
        gate.read_json(content)


def test_historical_production_manifest_cannot_be_treated_as_artifact_bound(tmp_path):
    path = SCRIPT.parent.parent / "docs/phase-12/release-gates.json"
    historical = json.loads(path.read_text(encoding="utf-8"))
    result = assess(historical, tmp_path)
    assert result["decision"] == "NO-GO"
    assert set(result["blocked_gates"]) == gate.REQUIRED
    assert "version-2" in result["errors"]["manifest"]
