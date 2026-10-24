"""Retain a bounded primary-source retrieval register, never auto-approve legal rules."""

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.tax.catalogue import SOURCES as CT
from app.modules.vat.catalogue import SOURCES as VAT
from app.modules.dmtt.service import SOURCES as DMTT
from app.modules.tp.catalogue import SOURCES as TP

DIRECT = {
    "CT-RATES": "https://tax.gov.ae/Datafolder/Files/Legislation/Corporate%20Tax/Cabinet%20Decision%20No.%20116%20of%202022%20-%20for%20publishing.pdf",
    "CD142": DMTT["CD142"]["url"], "MD96": DMTT["MD96"]["url"],
    "MD229-2025": CT["MD229-2025"]["url"],
    "MD131-2026": CT["MD131-2026"]["url"],
    "VAT-ER": VAT["VAT-ER"]["url"],
    "FTA13-2026": VAT["FTA13-2026"]["url"],
    "CTGTP1": TP["CTGTP1"]["url"],
}


def retrieve(item):
    key, url = item
    row = {"source_id": key, "url": url, "retrieved_at": datetime.now(UTC).isoformat(),
           "issuing_authority": "UAE Ministry of Finance / Federal Tax Authority",
           "category": "official_guidance" if key == "CTGTP1" else "legislation",
           "professional_approval": "REQUIRED_SEPARATELY"}
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(url)
            row["http_status"] = response.status_code
            response.raise_for_status()
            content = response.content
        if not content.startswith(b"%PDF-") or len(content) > 20 * 1024 * 1024:
            raise ValueError("Expected bounded official PDF")
        destination = ROOT / ".local-runtime/connected-tax/legal-sources" / (key + ".pdf")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        row.update(retrieval_status="RETRIEVED", sha256=hashlib.sha256(content).hexdigest(),
                   retained_path=str(destination), bytes=len(content),
                   verification_status="RETRIEVAL_CONFIRMED_CONTENT_REVIEW_SCOPED_SEPARATELY")
    except (httpx.HTTPError, ValueError) as exc:
        row.update(retrieval_status="AWAITING_VERIFICATION", verification_status="UNVERIFIED",
                   issue=type(exc).__name__, dependent_conclusion="BLOCK_FILING_READINESS")
    return row


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(retrieve, DIRECT.items()))
    target = ROOT / "docs/engine-strengthening/phase2/source-retrieval.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"auto_approves_rules": False, "sources": rows}, indent=2) + "\n")
    print(json.dumps({row["source_id"]: row["retrieval_status"] for row in rows}))
