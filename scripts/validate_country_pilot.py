"""Read-only checks of declared pilot evidence; never a legal/professional approval."""

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from decimal import Decimal, DecimalException
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
COUNTRIES = {"AE": "UAE", "IN": "India"}


class InvalidPilot(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise InvalidPilot(code)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def invalid_number(value):
    raise InvalidPilot("NON_FINITE_JSON_NUMBER")


def json_document(raw):
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=object_pairs,
            parse_float=Decimal,
            parse_constant=invalid_number,
        )
    except (
        UnicodeError,
        json.JSONDecodeError,
        RecursionError,
        DecimalException,
    ) as error:
        raise InvalidPilot("INVALID_OR_TOO_DEEP_JSON") from error


def read(path):
    require(path.is_file(), "EVIDENCE_FILE_MISSING")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "EVIDENCE_FILE_TOO_LARGE")
    return raw


def retained(root, relative, category):
    require(
        isinstance(relative, str) and 0 < len(relative) <= 500, "INVALID_RELATIVE_PATH"
    )
    require("\\" not in relative and ":" not in relative, "INVALID_RELATIVE_PATH")
    pieces = relative.split("/")
    require(
        len(pieces) > 1
        and pieces[0] == category
        and all(p not in {"", ".", ".."} for p in pieces),
        "EVIDENCE_CATEGORY_OR_PATH_INVALID",
    )
    path = root.joinpath(*pieces)
    require(
        path.resolve().is_relative_to(root.resolve()), "EVIDENCE_PATH_ESCAPES_COUNTRY"
    )
    for candidate in [path, *path.parents]:
        if candidate == root:
            break
        require(
            not candidate.is_symlink() and not candidate.is_junction(),
            "LINKED_EVIDENCE_PATH",
        )
    return path


def sha(value):
    require(
        isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value),
        "INVALID_SHA256",
    )
    return value


def text(value):
    require(
        isinstance(value, str) and len(value.strip()) >= 3 and value == value.strip(),
        "MISSING_OR_INVALID_DECLARED_IDENTITY",
    )
    return value.casefold()


def day(value):
    require(
        isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
        "INVALID_DATE",
    )
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise InvalidPilot("INVALID_DATE") from error


def equal(expected, actual, depth=0):
    require(depth < 100, "COMPARISON_NESTING_LIMIT")
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    if isinstance(expected, (int, Decimal)) and isinstance(actual, (int, Decimal)):
        return expected == actual
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return expected.keys() == actual.keys() and all(
            equal(value, actual[key], depth + 1) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(
            equal(a, b, depth + 1) for a, b in zip(expected, actual, strict=True)
        )
    return expected == actual


def validate(manifest_path, country_root):
    require(
        country_root.is_dir()
        and not country_root.is_symlink()
        and not country_root.is_junction(),
        "INVALID_COUNTRY_ROOT",
    )
    raw = read(manifest_path)
    consumed = len(raw)

    def retained_bytes(path):
        nonlocal consumed
        content = read(path)
        consumed += len(content)
        require(consumed <= MAX_TOTAL_BYTES, "PILOT_TOTAL_BYTE_BOUND_EXCEEDED")
        return content

    manifest = json_document(raw)
    require(isinstance(manifest, dict), "MANIFEST_MUST_BE_OBJECT")
    country = manifest.get("country")
    require(country in COUNTRIES, "UNSUPPORTED_COUNTRY")
    require(
        manifest.get("dataset_kind") == "REAL_CLIENT_PILOT",
        "REAL_PILOT_DECLARATION_REQUIRED",
    )
    require(manifest.get("status") == "READY_FOR_LOCAL_COMPARISON", "PILOT_NOT_READY")
    require(
        manifest.get("review_status") == "INDEPENDENT_REVIEW_RECORDED",
        "REVIEW_NOT_RECORDED",
    )
    text(manifest.get("client_reference"))
    text(manifest.get("consent_or_authorized_use_reference"))
    start, end = day(manifest.get("period_start")), day(manifest.get("period_end"))
    require(start <= end, "UNORDERED_PILOT_PERIOD")
    sys.path.insert(0, str(ROOT / "backend"))
    from app.modules.country_workflows.catalogue import WORKFLOWS

    workflow = manifest.get("workflow")
    require(
        workflow in WORKFLOWS
        and (not WORKFLOWS[workflow][1] or country in WORKFLOWS[workflow][1]),
        "WORKFLOW_COUNTRY_MISMATCH",
    )
    people = [
        text(manifest.get(key))
        for key in (
            "expected_prepared_by",
            "actual_prepared_by",
            "independent_reviewer",
        )
    ]
    require(len(set(people)) == 3, "INDEPENDENT_PREPARER_AND_REVIEWER_REQUIRED")
    require(
        manifest.get("expected_basis") == "INDEPENDENT_EXTERNAL_CALCULATION",
        "EXPECTED_BASIS_REQUIRED",
    )
    files, hashes = manifest.get("input_files"), manifest.get("input_sha256")
    require(
        isinstance(files, list)
        and 0 < len(files) <= 100
        and all(isinstance(p, str) for p in files),
        "INPUT_POPULATION_REQUIRED",
    )
    require(
        len(set(files)) == len(files)
        and isinstance(hashes, dict)
        and set(hashes) == set(files),
        "INPUT_HASH_POPULATION_MISMATCH",
    )
    resolved: set[Path] = set()
    for name in files:
        path = retained(country_root, name, "redacted-inputs")
        require(
            path.resolve() not in resolved
            and all(not path.samefile(other) for other in resolved),
            "DUPLICATE_INPUT_FILE",
        )
        resolved.add(path.resolve())
        require(
            digest(retained_bytes(path)) == sha(hashes[name]),
            "INPUT_HASH_MISMATCH",
        )
    contents = {}
    for role, category in [
        ("expected_result", "independent-expected-results"),
        ("actual_result", "review-records"),
        ("review_record", "review-records"),
    ]:
        path = retained(country_root, manifest.get(role + "_file"), category)
        require(
            path.resolve() not in resolved
            and all(not path.samefile(other) for other in resolved),
            "DUPLICATE_EVIDENCE_ROLE",
        )
        resolved.add(path.resolve())
        content = retained_bytes(path)
        require(
            digest(content) == sha(manifest.get(role + "_sha256")),
            "RESULT_OR_REVIEW_HASH_MISMATCH",
        )
        contents[role] = json_document(content)
    review = contents["review_record"]
    require(isinstance(review, dict), "REVIEW_RECORD_MUST_BE_OBJECT")
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
    ]:
        require(review.get(key) == manifest.get(key), "REVIEW_SCOPE_OR_HASH_MISMATCH")
    require(
        review.get("decision") == "COMPARISON_AUTHORIZED", "REVIEW_DECISION_REQUIRED"
    )
    require(day(review.get("review_date")) <= date.today(), "FUTURE_REVIEW_DATE")
    text(review.get("assessment"))
    require(
        isinstance(contents["expected_result"], (dict, list))
        and bool(contents["expected_result"]),
        "NONEMPTY_STRUCTURED_EXPECTATIONS_REQUIRED",
    )
    matches = equal(contents["expected_result"], contents["actual_result"])
    return {
        "contract": "local-pilot-evidence-comparison/1",
        "status": "DECLARED_EVIDENCE_MATCHES"
        if matches
        else "EXPECTED_ACTUAL_MISMATCH",
        "country": country,
        "workflow": workflow,
        "input_file_count": len(files),
        "manifest_sha256": digest(raw),
        "validator_sha256": digest(Path(__file__).read_bytes()),
        "checked_on": date.today().isoformat(),
        "results_equal": matches,
        "professional_validation": "NOT_ESTABLISHED_BY_THIS_TOOL",
        "legal_or_production_qualification": "NOT_ESTABLISHED",
        "limits": "Hashes check retained bytes; declared consent, identities, independence and document meaning require human verification. Exact JSON comparison has no rounding, inferred missing values or array reordering. No provider or software execution is performed.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--country-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(args.manifest, args.country_root)
    except (InvalidPilot, OSError, ValueError, TypeError, RecursionError) as error:
        print(
            json.dumps(
                {
                    "status": "INVALID_PILOT_EVIDENCE",
                    "code": str(error)
                    if isinstance(error, InvalidPilot)
                    else "UNREADABLE_OR_INVALID_EVIDENCE",
                }
            )
        )
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["results_equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
