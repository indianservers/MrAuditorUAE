"""Serial, synthetic fresh-process extraction observations, not a capacity benchmark."""

import json
import multiprocessing
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    from app.modules.intelligence.documents import extract_document
    from app.modules.intelligence.extraction_runtime import CONTRACT

    observations = []
    process = multiprocessing.current_process()
    prior_daemon = process.daemon
    try:
        for iteration in range(3):
            process.daemon = iteration % 2 == 1
            for country in ("AE", "IN"):
                folder = (
                    ROOT
                    / "docs/country-workflows/sample-inputs/SYNTHETIC-document-worker"
                    / country
                )
                expected = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
                for kind in ("digital", "pdf-ocr", "scan", "zip-selected", "zip-batch"):
                    filename = (
                        "digital.pdf"
                        if kind in {"digital", "pdf-ocr"}
                        else "scan.png"
                        if kind == "scan"
                        else "documents.zip"
                    )
                    media = (
                        "application/pdf"
                        if kind in {"digital", "pdf-ocr"}
                        else "image/png"
                        if kind == "scan"
                        else "application/zip"
                    )
                    started = time.perf_counter()
                    result = extract_document(
                        folder / filename,
                        media,
                        country,
                        dict(zip_member="invoice.pdf")
                        if kind == "zip-selected"
                        else dict(force_image=True)
                        if kind == "pdf-ocr"
                        else {},
                    )
                    assert result["original_sha256"] == expected["sha256"][filename]
                    assert result["local_worker_contract"] == CONTRACT
                    assert (
                        result["review_status"] == "UNVERIFIED"
                        and not result["network_document_transfer"]
                    )
                    if kind == "zip-batch":
                        assert all(value is None for value in result["fields"].values())
                        assert {
                            doc["fields"]["invoice_number"] for doc in result["documents"]
                        } == set(expected["batch_invoice_numbers"])
                    else:
                        assert all(
                            result["fields"][field] == value
                            for field, value in expected["fields"].items()
                        )
                    observations.append(
                        dict(
                            iteration=iteration + 1,
                            country=country,
                            kind=kind,
                            daemon=process.daemon,
                            seconds=round(time.perf_counter() - started, 6),
                            original_sha256=result["original_sha256"],
                            pages=len(result["pages"]),
                            providers=sorted({page["provider"] for page in result["pages"]}),
                            status="PASSED",
                        )
                    )
    finally:
        process.daemon = prior_daemon
        receipt = dict(
            synthetic=True,
            platform=platform.system(),
            python=platform.python_version(),
            contract=CONTRACT,
            expected_extractions=30,
            completed=len(observations),
            observations=observations,
            scope="Serial extraction only; no concurrency, hosted pool, capacity, malware-service or professional/client accuracy qualification",
        )
        (ROOT / "docs/phase-12/document-worker-stress.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
    print(
        "Verified 30 fresh native extractions across UAE then India, including the daemon context"
    )


if __name__ == "__main__":
    main()
