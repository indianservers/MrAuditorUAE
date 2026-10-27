"""Synthetic matching measurements; oversized populations exercise rejection only."""

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def measure(engine, size, distribution):
    import psutil

    from app.modules.intelligence.matching import reconcile_transactions

    if engine == "baseline":
        from tests.unit.transaction_matching_baseline import reconcile_transactions
    started = time.perf_counter()

    def population(prefix):
        return [
            dict(
                id=prefix + str(i),
                reference=f"REF-{i}" if distribution == "references" else "SHARED",
                counterparty="SYNTHETIC"
                if distribution == "references"
                else f"SYNTHETIC Party {i}",
                date="2026-06-01",
                amount="1",
                currency="AED",
            )
            for i in range(size)
        ]

    left, right = population("L"), population("R")
    generation = time.perf_counter() - started
    started = time.perf_counter()
    try:
        result = reconcile_transactions(left, right)
    except ValueError as exc:
        elapsed = time.perf_counter() - started
        if size <= 20000 or "20,000 rows" not in str(exc):
            raise
        output = dict(
            status="REJECTED_BY_DECLARED_BOUND",
            matching_executed=False,
            decision_sha256=None,
            matches=None,
            candidate_checks=None,
        )
    else:
        elapsed = time.perf_counter() - started
        assert (
            size <= 20000
            and len(result["matches"]) == size
            and not result["unmatched_left"]
            and not result["unmatched_right"]
        )
        assert result["source_totals"] == result["destination_totals"] == {"AED": str(size)}
        output = dict(
            status="CONTROLLED_SYNTHETIC_MATCHED",
            matching_executed=True,
            matches=size,
            candidate_checks=result.get("candidate_checks"),
            decision_sha256=hashlib.sha256(
                json.dumps(result["matches"], sort_keys=True).encode()
            ).hexdigest(),
        )
    memory = psutil.Process().memory_info()
    return dict(
        output,
        engine=engine,
        rows_per_side=size,
        distribution=distribution,
        population_build_seconds=round(generation, 6),
        matching_or_bound_check_seconds=round(elapsed, 6),
        peak_process_rss_bytes=getattr(memory, "peak_wset", None),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["baseline", "indexed"])
    parser.add_argument("--size", type=int, default=1000)
    parser.add_argument("--distribution", choices=["references", "parties"], default="references")
    args = parser.parse_args()
    if args.engine:
        print(json.dumps(measure(args.engine, args.size, args.distribution)))
        return

    def child(engine, size, distribution):
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--engine",
                engine,
                "--size",
                str(size),
                "--distribution",
                distribution,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return json.loads(result.stdout)

    paired = [
        child(engine, 1000, "references") for _ in range(3) for engine in ("baseline", "indexed")
    ]
    assert len({item["decision_sha256"] for item in paired}) == 1
    supported = [
        child("indexed", 20000, distribution) for distribution in ("references", "parties")
    ]
    unsupported = [child("indexed", size, "references") for size in (100000, 1000000)]
    assert all(item["status"] == "REJECTED_BY_DECLARED_BOUND" for item in unsupported)
    receipt = dict(
        synthetic=True,
        scope="In-process matching or explicit size rejection; excludes CSV/native ingestion, DB, worker queues, network, concurrency and professional accuracy",
        baseline_commit="f547bb7",
        paired_1000_rows=paired,
        paired_median_matching_seconds={
            engine: statistics.median(
                item["matching_or_bound_check_seconds"]
                for item in paired
                if item["engine"] == engine
            )
            for engine in ("baseline", "indexed")
        },
        supported_20000_rows=supported,
        unsupported_size_probes=unsupported,
        large_population_qualification="100k and 1m matching/ingestion capacity remains NOT QUALIFIED; only the bound rejection was exercised",
    )
    (ROOT / "docs/phase-12/matching-performance.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print("Saved paired matching measurements, two 20k cases and explicit 100k/1m rejection probes")


if __name__ == "__main__":
    main()
