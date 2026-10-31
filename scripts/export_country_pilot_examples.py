"""Save existing synthetic input/expected-result fixtures without claiming client data."""

import hashlib
import json
import re
import runpy
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/tests/unit/country_workflow_cases.py"
DESTINATION = ROOT / "pilot-data/synthetic-examples"
COUNTRIES = {"AE": "UAE", "IN": "India"}


def export(destination=None):
    if destination is None:
        destination = DESTINATION
    else:
        destination = Path(destination).resolve()
        synthetic_root = (ROOT / "pilot-data/synthetic-examples").resolve()
        if destination == synthetic_root or not destination.is_relative_to(
            synthetic_root
        ):
            raise ValueError(
                "Explicit exports require a separate version inside pilot-data/synthetic-examples"
            )
    source_bytes = SOURCE.read_bytes()
    cases = runpy.run_path(str(SOURCE))["CASES"]
    if SOURCE.read_bytes() != source_bytes:
        raise RuntimeError(
            "Fixture source changed during export; retry the unchanged source"
        )
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    snapshots = destination / "fixture-sources"
    snapshot = snapshots / (source_hash + ".txt")
    if snapshot.exists() and snapshot.read_bytes() != source_bytes:
        raise FileExistsError(
            "Preserve and investigate the changed fixture-source snapshot"
        )
    counts = Counter()
    index = []
    for case in cases:
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]+", case["id"])
            or case["country"] not in COUNTRIES
        ):
            raise ValueError("Unsupported synthetic scenario identity or country")
        country = COUNTRIES[case["country"]]
        folder = destination / country
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (case["id"] + ".json")
        document = {
            "dataset_kind": "SYNTHETIC_ENGINE_FIXTURE",
            "real_client_data": False,
            "professional_validation": "NOT_ESTABLISHED",
            "source_fixture": SOURCE.relative_to(ROOT).as_posix(),
            "source_fixture_sha256": source_hash,
            "case": case,
        }
        content = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        retained_hash = source_hash
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            retained_hash = existing.get("source_fixture_sha256", "")
            if (
                not isinstance(retained_hash, str)
                or not re.fullmatch(r"[a-f0-9]{64}", retained_hash)
                or {
                    key: value
                    for key, value in existing.items()
                    if key != "source_fixture_sha256"
                }
                != {
                    key: value
                    for key, value in document.items()
                    if key != "source_fixture_sha256"
                }
            ):
                raise FileExistsError(
                    f"Preserve the existing example before regenerating: {path}"
                )
        else:
            path.write_text(content, encoding="utf-8")
        assert json.loads(path.read_text(encoding="utf-8"))["case"] == case
        counts[country] += 1
        index.append(
            {
                "id": case["id"],
                "country": case["country"],
                "workflow": case["workflow"],
                "file": f"{country}/{path.name}",
                "source_fixture_sha256": retained_hash,
            }
        )
    snapshots.mkdir(parents=True, exist_ok=True)
    if not snapshot.exists():
        snapshot.write_bytes(source_bytes)
    retained_sources = []
    for retained_hash in sorted(
        {item["source_fixture_sha256"] for item in index} | {source_hash}
    ):
        retained = snapshots / (retained_hash + ".txt")
        if (
            retained.exists()
            and hashlib.sha256(retained.read_bytes()).hexdigest() != retained_hash
        ):
            raise FileExistsError(
                "Preserve and investigate the changed fixture-source snapshot"
            )
        retained_sources.append(
            {
                "sha256": retained_hash,
                "file": retained.relative_to(destination).as_posix()
                if retained.exists()
                else None,
                "normalization": "ORIGINAL_BYTES",
                "status": "RETAINED"
                if retained.exists()
                else "HISTORICAL_BYTES_NOT_RETAINED",
            }
        )
    (destination / "catalog.json").write_text(
        json.dumps(
            {
                "dataset_kind": "SYNTHETIC_ENGINE_FIXTURES_NOT_CLIENT_PILOTS",
                "fixture_hash_policy": "Per-file original fixture hashes are preserved for unchanged cases; the root hash identifies this generator run source version",
                "source_fixture_sha256": source_hash,
                "scenario_count": len(cases),
                "counts_by_country": dict(counts),
                "source_fixture_snapshots": retained_sources,
                "cases": index,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Saved and verified {len(cases)} synthetic input/expected-result cases: {dict(counts)}"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination",
        help="Separate version folder inside pilot-data/synthetic-examples",
    )
    export(parser.parse_args().destination)
