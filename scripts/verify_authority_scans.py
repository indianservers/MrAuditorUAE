"""CI proof for exact public authority PDFs; no scanner bypass or document rewriting."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings
from app.modules.audit_execution.evidence import scan
from app.modules.country_workflows import uae_company_accounts
from app.modules.grc import adgm_accounts, dmcc_audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = [
        (
            "adgm-accounts-2026-10-31/adgm-companies-consolidated-ver20260626.pdf",
            adgm_accounts.REGULATIONS_SHA256,
        ),
        (
            "adgm-accounts-2026-10-31/adgm-annual-accounts-v2-20261014.pdf",
            adgm_accounts.GUIDANCE_SHA256,
        ),
        (
            "dmcc-audit-2026-10-30/dmcc-company-regulations-amended.pdf",
            dmcc_audit.REGULATIONS_SHA256,
        ),
        (
            "dmcc-audit-2026-10-30/dmcc-afs-guidelines-2025-04-29.pdf",
            dmcc_audit.GUIDELINE_SHA256,
        ),
        (
            "uae-company-law-2026-10-31/moet-hosted-companies-law32-2021-english.pdf",
            uae_company_accounts.LAW_SHA256,
        ),
        (
            "uae-company-law-2026-10-31/fdl20-2025-arabic-original.pdf",
            uae_company_accounts.AMENDMENT_SHA256,
        ),
    ]
    rows = []
    for relative, digest in sources:
        path = ROOT / "docs/country-workflows/authority-references" / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        started = time.monotonic()
        diagnostics = {}
        if actual != digest:
            status = "ORIGINAL_HASH_MISMATCH"
        else:
            with path.open("rb") as stream:
                status = scan(stream, diagnostics=diagnostics)
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": actual,
                "status": status,
                "scanner_reason": diagnostics.get("reason", "ORIGINAL_HASH_MISMATCH"),
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        )
        print(
            f"Original authority scan: {path.name}: {status} ({rows[-1]['elapsed_seconds']}s)",
            flush=True,
        )
        if status != "CLEAN":
            break
    passed = len(rows) == len(sources) and all(row["status"] == "CLEAN" for row in rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "contract": "original-authority-scans/1",
                "passed": passed,
                "scanner_budget_seconds": settings().evidence_clamav_timeout_seconds,
                "expected_sources": len(sources),
                "sources": rows,
                "scope": "Exact original public PDFs and configured real scanner only; not legal qualification, a complete malware-engine evaluation or external filing.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
