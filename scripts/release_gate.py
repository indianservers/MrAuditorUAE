"""Validate retained release receipts against the explicitly selected artifact."""

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

REQUIRED = {
    "tenant_isolation",
    "financial_accuracy",
    "professional_approvals",
    "critical_security",
    "migration",
    "recovery",
    "deployment_rollback",
    "ai_authorization",
    "audit_history",
    "demo_isolation",
}
MAX_JSON = 1024 * 1024
MAX_EVIDENCE = 100 * 1024 * 1024


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def read_json(content):
    if len(content) > MAX_JSON:
        raise ValueError("JSON evidence exceeds 1 MiB")
    return json.loads(
        content.decode("utf-8-sig"),
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError("Non-finite JSON value")
        ),
    )


def small_file(path):
    with path.open("rb") as stream:
        return stream.read(MAX_JSON + 1)


def relative_file(root, value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 2048
        or "\\" in value
        or ":" in value
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("Evidence must use a repository-relative file path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Evidence must stay inside the repository")
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError("Evidence file is missing or outside the repository")
    if not 0 < candidate.stat().st_size <= MAX_EVIDENCE:
        raise ValueError("Evidence file is empty or exceeds 100 MiB")
    return candidate


def digest_file(path, expected):
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Every evidence file requires its SHA-256")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError("Retained evidence SHA-256 does not agree")


def release_identity(value):
    if not isinstance(value, dict) or set(value) != {
        "commit",
        "image_digest",
        "environment",
    }:
        raise ValueError(
            "Release binding requires commit, image_digest and environment"
        )
    if not isinstance(value["commit"], str) or not re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", value["commit"]
    ):
        raise ValueError("Release commit must be an immutable Git object ID")
    if not isinstance(value["image_digest"], str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", value["image_digest"]
    ):
        raise ValueError("Release image must use its immutable sha256 digest")
    if not isinstance(value["environment"], str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", value["environment"]
    ):
        raise ValueError("Select an explicit target environment identifier")
    return value


def check_receipt(root, gate_name, gate, release, manifest_path):
    if not isinstance(gate, dict) or set(gate) - {
        "status",
        "evidence",
        "evidence_sha256",
        "open_blocker",
    }:
        raise ValueError("Gate has missing or unsupported fields")
    if (
        gate.get("status") != "VERIFIED"
        or type(gate.get("open_blocker", False)) is not bool
        or gate.get("open_blocker", False)
    ):
        raise ValueError("Gate is unverified or has an open blocker")
    path = relative_file(root, gate.get("evidence"))
    content = small_file(path)
    expected = gate.get("evidence_sha256")
    if (
        not isinstance(expected, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected)
        or hashlib.sha256(content).hexdigest() != expected
    ):
        raise ValueError("Retained receipt SHA-256 is missing or does not agree")
    receipt = read_json(content)
    if (
        not isinstance(receipt, dict)
        or set(receipt)
        != {"schema_version", "gate", "release", "outcome", "executed_at", "evidence"}
        or type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != 1
    ):
        raise ValueError("Gate requires a versioned executed-evidence receipt")
    if receipt["gate"] != gate_name or release_identity(receipt["release"]) != release:
        raise ValueError(
            "Receipt belongs to another gate, commit, image or environment"
        )
    if receipt["outcome"] != "PASS":
        raise ValueError("Receipt execution did not pass")
    stamp = receipt["executed_at"]
    if not isinstance(stamp, str) or len(stamp) > 60:
        raise ValueError("Receipt requires an executed timestamp with timezone")
    try:
        executed = datetime.fromisoformat(stamp)
    except ValueError:
        raise ValueError("Receipt execution timestamp is invalid") from None
    if (
        executed.tzinfo is None
        or executed.utcoffset() is None
        or executed > datetime.now(UTC) + timedelta(minutes=5)
    ):
        raise ValueError(
            "Receipt execution timestamp lacks timezone or is in the future"
        )
    artifacts = receipt["evidence"]
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 30:
        raise ValueError("Receipt requires one to thirty retained execution artifacts")
    seen = set()
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError("Execution artifacts require a path and SHA-256")
        original = relative_file(root, item["path"])
        if original in seen or original == path or original == manifest_path:
            raise ValueError(
                "Execution artifacts must be distinct from receipts and the manifest"
            )
        seen.add(original)
        digest_file(original, item["sha256"])


def assess(
    data,
    *,
    root,
    expected_commit,
    expected_image_digest,
    expected_environment,
    manifest_path=None,
):
    root = Path(root).resolve()
    errors = {}
    gates = data.get("gates") if isinstance(data, dict) else None
    names = set(gates) if isinstance(gates, dict) else set()
    blocked = REQUIRED - names
    for name in blocked:
        errors[name] = "Required release gate is missing"
    try:
        if (
            not isinstance(data, dict)
            or set(data) - {"schema_version", "scope", "release", "gates"}
            or type(data.get("schema_version")) is not int
            or data["schema_version"] != 2
        ):
            raise ValueError("Select a version-2 artifact-bound release manifest")
        expected = release_identity(
            {
                "commit": expected_commit,
                "image_digest": expected_image_digest,
                "environment": expected_environment,
            }
        )
        release = release_identity(data.get("release"))
        if release != expected:
            raise ValueError(
                "Manifest differs from the selected source commit, image or target environment"
            )
        if not isinstance(gates, dict) or not 1 <= len(gates) <= 30:
            raise ValueError("Release manifest requires bounded gate records")
    except (ValueError, TypeError) as exc:
        errors["manifest"] = str(exc)
        blocked.update(REQUIRED | names)
        return {"decision": "NO-GO", "blocked_gates": sorted(blocked), "errors": errors}
    for name, gate in gates.items():
        try:
            if not isinstance(name, str) or not re.fullmatch(
                r"[a-z][a-z0-9_]{1,80}", name
            ):
                raise ValueError("Invalid release gate identifier")
            check_receipt(root, name, gate, release, manifest_path)
        except (ValueError, TypeError, OSError, UnicodeError) as exc:
            blocked.add(name)
            errors[name] = (
                str(exc)
                if isinstance(exc, ValueError)
                else "Retained evidence could not be read"
            )
    return {
        "decision": "NO-GO" if blocked else "GO",
        "release": release,
        "blocked_gates": sorted(blocked),
        "errors": errors,
    }


def evaluate(data, **kwargs):
    """Legacy callers without an independently selected artifact remain closed."""
    return assess(
        data,
        root=kwargs.pop("root", Path(__file__).resolve().parents[1]),
        expected_commit=kwargs.pop("expected_commit", None),
        expected_image_digest=kwargs.pop("expected_image_digest", None),
        expected_environment=kwargs.pop("expected_environment", None),
        **kwargs,
    )["blocked_gates"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest", help="Reviewed repository-relative release manifest"
    )
    parser.add_argument(
        "--commit", required=True, help="Reviewed source artifact commit"
    )
    parser.add_argument(
        "--image-digest", required=True, help="Reviewed immutable image digest"
    )
    parser.add_argument(
        "--environment", required=True, help="Exact reviewed target environment"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        path = relative_file(root, args.manifest)
        result = assess(
            read_json(small_file(path)),
            root=root,
            expected_commit=args.commit,
            expected_image_digest=args.image_digest,
            expected_environment=args.environment,
            manifest_path=path,
        )
    except (ValueError, TypeError, OSError, UnicodeError):
        result = {
            "decision": "NO-GO",
            "blocked_gates": sorted(REQUIRED),
            "errors": {
                "manifest": "Release manifest is missing, malformed or outside the repository"
            },
        }
    print(json.dumps(result, sort_keys=True))
    return 1 if result["blocked_gates"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
