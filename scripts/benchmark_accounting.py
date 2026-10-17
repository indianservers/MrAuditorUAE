"""Repeatable synthetic file/engine benchmark. No performance figures are assumed.
Run: cd backend; uv run python ../scripts/benchmark_accounting.py --sizes 10000 100000 1000000
This measures file parsing/normalization and transient analytics, not PostgreSQL commit throughput.
"""

import argparse
import csv
import json
import platform
import sys
import tempfile
import threading
import time
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.modules.accounting.calculations import reconcile, trial_balance
from app.modules.accounting.schemas import ImportOptions
from app.modules.audit_analytics.engine import COLUMNS, AnalyticsEngine
from app.modules.audit_analytics.schemas import AnalyticsRequest
from app.modules.ingestion.parser import normalize, rows

parser = argparse.ArgumentParser()
parser.add_argument("--sizes", nargs="+", type=int, default=[10000, 100000, 1000000])
args = parser.parse_args()
evidence = {
    "synthetic": True,
    "mode": "streamed file normalization + DuckDB analytics; excludes PostgreSQL writes",
    "hardware": {
        "platform": platform.platform(),
        "cpu_count": psutil.cpu_count(),
        "memory_bytes": psutil.virtual_memory().total,
        "python": platform.python_version(),
    },
    "runs": [],
}
for size in args.sizes:
    stop = threading.Event()
    peak = [0]

    def memory():
        while not stop.wait(0.02):
            peak[0] = max(peak[0], psutil.Process().memory_info().rss)

    monitor = threading.Thread(target=memory, daemon=True)
    monitor.start()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "SYNTHETIC-ledger.csv"
        normalized = Path(directory) / "normalized.csv"
        controls = {"A": Decimal(0), "B": Decimal(0)}
        with path.open("w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "account_code",
                    "account_name",
                    "journal_ref",
                    "posting_date",
                    "debit",
                    "credit",
                    "source_id",
                    "currency",
                ]
            )
            for index in range(size):
                amount = Decimal(index // 2 % 1000 + 1) / 100
                controls["A" if index % 2 == 0 else "B"] += amount if index % 2 == 0 else -amount
                writer.writerow(
                    [
                        "A" if index % 2 == 0 else "B",
                        "Synthetic account",
                        str(index // 2),
                        "2026-06-01",
                        amount if index % 2 == 0 else 0,
                        amount if index % 2 else 0,
                        str(index),
                        "AED",
                    ]
                )
        options = ImportOptions(
            client_id=uuid.uuid4(), entity_id=uuid.uuid4(), period_id=uuid.uuid4()
        )
        start = time.perf_counter()
        count = 0
        with normalized.open("w", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    *COLUMNS,
                    "account_name",
                    "base_debit",
                    "base_credit",
                    "functional_currency",
                    "opening",
                ],
                extrasaction="ignore",
            )
            writer.writeheader()
            for index, raw in rows(path, path.name, options):
                canonical, _ = normalize(
                    raw, options, date(2026, 1, 1), date(2026, 12, 31), "AED", index
                )
                canonical["id"] = str(uuid.UUID(int=count + 1))
                writer.writerow(canonical)
                count += 1
        ingestion = time.perf_counter() - start
        start = time.perf_counter()
        with normalized.open() as file:
            tb = trial_balance(csv.DictReader(file), "AED", precision=8)
        validation = time.perf_counter() - start
        start = time.perf_counter()
        report = reconcile(controls, {r["account_code"]: r["closing"] for r in tb})
        reconciliation = time.perf_counter() - start
        start = time.perf_counter()
        with normalized.open() as file:
            engine = AnalyticsEngine(csv.DictReader(file))
        try:
            results = engine.evaluate(
                AnalyticsRequest(
                    snapshot_id=uuid.UUID(int=1), holidays=[], materiality=Decimal("100000")
                )
            )
            flagged = sum(r["flagged_count"] for r in results)
        finally:
            engine.close()
        analytics = time.perf_counter() - start
        stop.set()
        monitor.join()
        run = {
            "lines": size,
            "ingestion_seconds": ingestion,
            "validation_tb_seconds": validation,
            "reconciliation_seconds": reconciliation,
            "analytics_seconds": analytics,
            "peak_process_rss_bytes": peak[0],
            "source_bytes": path.stat().st_size,
            "rules": len(results),
            "rules_not_testable": sum(r["status"] == "not_testable" for r in results),
            "flags": flagged,
            "rows_processed": count,
            "independent_source_reconciliation": report["status"],
        }
        evidence["runs"].append(run)
        print(json.dumps(run), flush=True)
        out = Path(__file__).resolve().parents[1] / "docs/evidence/phase-2-benchmarks.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
