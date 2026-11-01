"""Build and execute explicitly synthetic UAE pilot files without external access.

Builder expectations come from authored literals, never calculation outputs.
No real-pilot manifest, legal approval or independent human signature is created.
"""

import argparse
import csv
import hashlib
import io
import json
import re
import runpy
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
DATASET = "SYNTHETIC-OFFLINE-2026-11-01"
KIND = "SYNTHETIC_UAE_OFFLINE_PILOT"
ROLES = ("redacted-inputs", "independent-expected-results", "review-records")
MAX_BYTES = 10 * 1024 * 1024


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative(role, name):
    return f"pilot-data/UAE/{role}/{DATASET}/{name}"


def retained(root, name):
    prefix = "pilot-data/UAE/"
    if not isinstance(name, str) or not name.startswith(prefix) or "\\" in name:
        raise ValueError("Synthetic pilot path outside the designated UAE folders")
    parts = name.split("/")
    if (
        len(parts) < 6
        or parts[2] not in ROLES
        or parts[3] != DATASET
        or any(p in {"", ".", ".."} for p in parts)
    ):
        raise ValueError("Synthetic pilot path must remain in its labelled dataset")
    path = root.joinpath(*parts)
    allowed = (root / "pilot-data/UAE" / parts[2] / DATASET).resolve()
    if not path.resolve().is_relative_to(allowed) or not allowed.is_relative_to(root.resolve()):
        raise ValueError("Synthetic pilot path escaped the workspace")
    for candidate in [path, *path.parents]:
        if candidate == root:
            break
        if candidate.is_symlink() or candidate.is_junction():
            raise ValueError("Synthetic pilot files cannot follow linked paths")
    return path


def save_original(root, name, raw):
    path = retained(root, name)
    if path.exists():
        if path.read_bytes() != raw:
            raise FileExistsError(
                f"Preserve the original synthetic file before changing it: {name}"
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return {"path": name, "sha256": sha(raw), "bytes": len(raw)}


def read_bound(root, record):
    path = retained(root, record["path"])
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or len(raw) != record["bytes"] or sha(raw) != record["sha256"]:
        raise ValueError("Synthetic original bytes differ from the manifest: " + record["path"])
    return raw


def authored_cases():
    source = ROOT / "backend/tests/unit/country_workflow_cases.py"
    cases = [
        dict(c, fixture_family="EXISTING_ENGINE_REGRESSION")
        for c in runpy.run_path(str(source))["CASES"]
        if c["country"] == "AE"
    ]
    new = runpy.run_path(str(ROOT / "scripts/uae_synthetic_pilot_cases.py"))["operating_cases"]()
    return cases + new


def build(root=ROOT, cases=None):
    from app.modules.country_workflows.catalogue import WORKFLOWS, catalogue

    root = Path(root).resolve()
    cases = authored_cases() if cases is None else cases
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Duplicate synthetic pilot case identity")
    entries = []
    for case in cases:
        identifier = case["id"]
        if not re.fullmatch(r"(?:RW-\d{3}|SYN-UAE-\d{3})", identifier) or case["country"] != "AE":
            raise ValueError("Only explicitly named UAE synthetic cases belong in this bundle")
        if "SYNTHETIC" not in case["title"]:
            title = "SYNTHETIC UAE regression: " + case["title"]
        else:
            title = case["title"]
        source_files = {}
        for role, rows in case["sources"].items():
            if not rows:
                raise ValueError("This fixture writer requires an explicit nonempty source table")
            table = WORKFLOWS[case["workflow"]][2][role]
            fields = list(dict.fromkeys(field for row in rows for field in row))
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(
                {
                    k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                    for k, v in row.items()
                }
                for row in rows
            )
            original = save_original(
                root,
                relative("redacted-inputs", f"{identifier}/{role}.csv"),
                buffer.getvalue().encode("utf-8"),
            )
            totals = {}
            for row in rows:
                field = "amount" if "amount" in row else "tax" if "tax" in row else None
                if field:
                    currency = row["currency"]
                    totals[currency] = totals.get(currency, Decimal(0)) + Decimal(str(row[field]))
            control = {
                "table_type": table,
                "expected_rows": len(rows),
                "control_totals": {k: str(v) for k, v in totals.items()},
            }
            if table == "gst-document-series":
                control["document_series_controls"] = {
                    k: sum(r[k] for r in rows) for k in ("issued", "cancelled", "net_issued")
                }
            source_files[role] = {**original, "controls": control}
        expected = save_original(
            root,
            relative("independent-expected-results", f"{identifier}/expected.json"),
            encoded(
                {
                    "dataset_kind": KIND,
                    "real_client_data": False,
                    "case_id": identifier,
                    "expected_basis": "AUTHOR_DEFINED_LITERALS_NOT_ENGINE_OUTPUT",
                    "independent_human_review": False,
                    "expected": case["expected"],
                    "arithmetic_basis": case.get(
                        "arithmetic_basis",
                        "Existing authored regression assertions; additional invariants are checked by the regression suite.",
                    ),
                }
            ),
        )
        entries.append(
            {
                "id": identifier,
                "title": title,
                "workflow": case["workflow"],
                "country": "AE",
                "fixture_family": case.get("fixture_family", "AUTHOR_DEFINED"),
                "as_of": "2026-06-30",
                "parameters": case["parameters"],
                "source_files": source_files,
                "expected_file": expected,
            }
        )
    manifest = {
        "dataset_kind": KIND,
        "real_client_data": False,
        "independent_professional_review": False,
        "dataset_date": "2026-11-01",
        "country": "AE",
        "case_count": len(entries),
        "entities": [
            {
                "reference": "SYN-ALNOOR-ENTITY",
                "name": "SYNTHETIC Al Noor Gulf Trading LLC",
                "business": "Fictional industrial supplies trader with a Jebel Ali warehouse and Dubai sales",
            },
            {
                "reference": "SYN-GULF-RELIEF-FOUNDATION",
                "name": "SYNTHETIC Gulf Community Relief Foundation",
                "business": "Separate fictional nonprofit for diligence scenarios",
            },
        ],
        "population_note": "Operating scenarios are separate from precision/regression cases. Cases are alternatives, not an additive company ledger. No case purports to be an actual government export, bank statement, WPS receipt or licensed registry response.",
        "available_uae_workflows": sorted(x["id"] for x in catalogue("AE") if x["available"]),
        "pilot_workflows": sorted({c["workflow"] for c in entries}),
        "cases": entries,
    }
    name = relative("redacted-inputs", "batch/manifest.json")
    save_original(root, name, encoded(manifest))
    return manifest


def equal_decimal(left, right):
    if left is None or isinstance(left, bool):
        return False
    a, b = Decimal(str(left)), Decimal(str(right))
    return a.is_finite() and b.is_finite() and a == b


def compare(result, expected):
    allowed = {
        "exceptions",
        "blocked",
        "state",
        "tax_difference",
        "stale",
        "icfr_states",
        "assertions",
        "rows_match",
    }
    if not expected or set(expected) - allowed:
        raise ValueError("Unsupported or empty authored expectation")
    issues = []
    for key in ("exceptions", "blocked", "state", "tax_difference", "stale"):
        if key not in expected:
            continue
        actual = (
            result["exception_count"]
            if key == "exceptions"
            else result.get(key)
            if key == "blocked"
            else result["rows"][0].get(key)
        )
        if type(actual) is not type(expected[key]) or actual != expected[key]:
            issues.append({"field": key, "expected": expected[key], "actual": actual})
    if "icfr_states" in expected:
        actual = [[r["kind"], r["duty"], r["state"]] for r in result["rows"]]
        if actual != expected["icfr_states"]:
            issues.append(
                {
                    "field": "icfr_states",
                    "expected": expected["icfr_states"],
                    "actual": actual,
                }
            )
    for assertion in expected.get("assertions", []):
        actual = result
        for key in assertion["path"]:
            actual = actual[key]
        operation = set(assertion) - {"path"}
        if len(operation) != 1 or not operation <= {
            "equals",
            "decimal_equals",
            "length",
        }:
            raise ValueError("Unsupported synthetic assertion operation")
        kind = next(iter(operation))
        target = assertion[kind]
        ok = (
            equal_decimal(actual, target)
            if kind == "decimal_equals"
            else len(actual) == target
            if kind == "length"
            else type(actual) is type(target) and actual == target
        )
        if not ok:
            issues.append(
                {
                    "path": assertion["path"],
                    "operation": kind,
                    "expected": target,
                    "actual": actual,
                }
            )
    for wanted in expected.get("rows_match", []):
        if not any(
            all(row.get(k) == v and type(row.get(k)) is type(v) for k, v in wanted.items())
            for row in result["rows"]
        ):
            issues.append({"row_not_found": wanted})
    for key, value in {
        "review_status": "UNVERIFIED",
        "professional_conclusion": "NOT_DETERMINED",
        "statutory_calculation_qualified": False,
    }.items():
        if result.get(key) != value:
            issues.append({"field": key, "expected": value, "actual": result.get(key)})
    return issues


def execute_case(root, case):
    from app.modules.country_workflows.calculations import calculate
    from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
    from app.modules.country_workflows.sources import parse_csv

    expected_doc = json.loads(read_bound(root, case["expected_file"]))
    if (
        expected_doc.get("dataset_kind") != KIND
        or expected_doc.get("case_id") != case["id"]
        or expected_doc.get("real_client_data") is not False
    ):
        raise ValueError("Expected results must retain their exact synthetic identity")
    expected = expected_doc["expected"]
    sources = {}
    for role, source in case["source_files"].items():
        data = SourceInput(
            evidence_version_id=uuid.uuid5(uuid.NAMESPACE_URL, case["id"] + ":" + role),
            label=case["title"][:200],
            **source["controls"],
        )
        sources[role] = parse_csv(read_bound(root, source), data)
    params = WorkflowInput(
        workflow=case["workflow"],
        title=case["title"][:200],
        rationale="SYNTHETIC offline pilot with authored expected outcomes; no external access or human approval",
        source_ids={r: uuid.uuid5(uuid.NAMESPACE_URL, case["id"] + ":" + r) for r in sources},
        as_of=case["as_of"],
        **case["parameters"],
    )
    try:
        result = calculate(params, "AE", sources)
    except ValueError as error:
        matched = (
            set(expected) == {"error"} and re.search(expected["error"], str(error)) is not None
        )
        return {
            "id": case["id"],
            "workflow": case["workflow"],
            "status": "PASS" if matched else "FAIL",
            "execution": "EXPECTED_REJECTION" if matched else "UNEXPECTED_REJECTION",
            "error": str(error),
        }
    if "error" in expected:
        return {
            "id": case["id"],
            "workflow": case["workflow"],
            "status": "FAIL",
            "execution": "EXPECTED_REJECTION_DID_NOT_OCCUR",
        }
    issues = compare(result, expected)
    return {
        "id": case["id"],
        "workflow": case["workflow"],
        "status": "FAIL" if issues else "PASS",
        "execution": "CALCULATED",
        "issues": issues,
        "actual": result,
    }


def run(root=ROOT):
    root = Path(root).resolve()
    path = retained(root, relative("redacted-inputs", "batch/manifest.json"))
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("Synthetic pilot manifest exceeds the bounded reader")
    manifest = json.loads(raw)
    if (
        manifest.get("dataset_kind") != KIND
        or manifest.get("real_client_data") is not False
        or manifest.get("country") != "AE"
    ):
        raise ValueError("This runner accepts only its explicitly synthetic UAE bundle")
    cases = manifest["cases"]
    if len(cases) != manifest["case_count"] or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Synthetic manifest case population differs")
    results = []
    for case in cases:
        if case.get("country") != "AE":
            raise ValueError("A UAE pilot case cannot switch country")
        try:
            result = execute_case(root, case)
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            ArithmeticError,
        ) as error:
            result = {
                "id": case["id"],
                "workflow": case["workflow"],
                "status": "FAIL",
                "execution": "INVALID_OR_UNREADABLE_FIXTURE",
                "error": str(error),
            }
        results.append(result)
    app_files = [
        {
            "path": p.relative_to(ROOT).as_posix(),
            "normalization": "LF",
            "sha256": sha(p.read_bytes().replace(b"\r\n", b"\n")),
        }
        for p in sorted((ROOT / "backend/app").rglob("*"))
        if p.is_file() and p.suffix in {".py", ".json"}
    ]
    report = {
        "app_tree_content_sha256": sha(encoded(app_files)),
        "app_tree_file_count": len(app_files),
        "runner_sha256": sha(Path(__file__).read_bytes().replace(b"\r\n", b"\n")),
        "dataset_kind": KIND,
        "real_client_data": False,
        "independent_professional_review": False,
        "executed_at": datetime.now(UTC).isoformat(),
        "manifest_sha256": sha(raw),
        "case_count": len(results),
        "passed": sum(r["status"] == "PASS" for r in results),
        "failed": sum(r["status"] != "PASS" for r in results),
        "expected_rejections": sum(r["execution"] == "EXPECTED_REJECTION" for r in results),
        "pilot_workflows": sorted({r["workflow"] for r in results}),
        "execution_scope": "Retained CSV parsing, typed controls and deterministic calculations only; API/storage/worker/review coverage comes from separately executed regressions",
        "results": [{k: v for k, v in r.items() if k != "actual"} for r in results],
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    folder = retained(root, relative("review-records", f"runs/{stamp}/comparison.json"))
    folder.parent.mkdir(parents=True, exist_ok=False)
    folder.write_bytes(encoded(report))
    for result in results:
        (folder.parent / (result["id"] + "-actual.json")).write_bytes(
            encoded(
                {
                    "dataset_kind": KIND,
                    "real_client_data": False,
                    "independent_professional_review": False,
                    **result,
                }
            )
        )
    return report, folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "run"])
    args = parser.parse_args()
    if args.action == "build":
        manifest = build()
        print(
            json.dumps(
                {
                    "dataset_kind": KIND,
                    "saved_cases": manifest["case_count"],
                    "workflow_count": len(manifest["pilot_workflows"]),
                }
            )
        )
        return 0
    report, path = run()
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "dataset_kind",
                    "case_count",
                    "passed",
                    "failed",
                    "expected_rejections",
                ]
            }
        )
    )
    print(path.relative_to(ROOT).as_posix())
    for result in report["results"]:
        if result["status"] != "PASS":
            print(json.dumps(result))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
