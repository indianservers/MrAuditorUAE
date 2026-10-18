"""Bounded text-layer extraction. This is not image OCR or visual invoice verification."""

import multiprocessing
import re
from pathlib import Path


def _extract(path, queue):
    try:
        from pypdf import PdfReader

        reader = PdfReader(path, strict=True)
        if reader.is_encrypted or len(reader.pages) > 5:
            raise ValueError("Only unencrypted PDFs up to5pages supported")
        text = "\n".join((page.extract_text() or "")[:12000] for page in reader.pages)
        if not text.strip():
            raise ValueError("No usable PDF text layer; image OCR is not configured")
        fields = {}
        patterns = {
            "invoice_number": r"Invoice\s*(?:No\.?|Number)\s*:\s*([A-Za-z0-9_-]+)",
            "supplier_trn": r"Supplier\s*TRN\s*:\s*(\d{15})",
            "declared_tax": r"VAT\s*Amount\s*:\s*([\d,.]+)",
            "declared_gross": r"Gross\s*Amount\s*:\s*([\d,.]+)",
        }
        for key, pattern in patterns.items():
            matches = re.findall(pattern, text, re.I)
            if len(matches) == 1:
                fields[key] = matches[0]
        queue.put(
            {
                "fields": fields,
                "text_excerpt": text[:12000],
                "pages": len(reader.pages),
                "state": "TEXT_PDF_EXTRACTED_UNVERIFIED",
                "visual_verification": False,
                "human_review_required": True,
            }
        )
    except Exception:
        queue.put({"error": "PDF could not be safely extracted; verify original document manually"})


def extract_text_pdf(path):
    path = Path(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Extraction limited to2MiB PDFs")
    context = multiprocessing.get_context("spawn")
    queue = context.Queue(maxsize=1)
    process = context.Process(target=_extract, args=(str(path), queue), daemon=True)
    process.start()
    try:
        try:
            result = queue.get(timeout=6)
        except Exception:
            raise ValueError("PDF extraction timed out or failed") from None
        if "error" in result:
            raise ValueError(result["error"])
        return result
    finally:
        process.join(timeout=0.5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
        queue.close()
