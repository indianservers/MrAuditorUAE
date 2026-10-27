"""Bounded, local PDF/image extraction. Text is untrusted evidence, never instructions."""

import hashlib
import importlib.metadata
import importlib.util
import io
import re
import threading
import zipfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

_PDFIUM_PREVIEW_LOCK = threading.Lock()

FIELDS = {
    "supplier": r"(?:Supplier|Vendor)\s*(?:Name)?\s*:\s*([^\n]+)",
    "customer": r"Customer\s*(?:Name)?\s*:\s*([^\n]+)",
    "invoice_number": r"Invoice\s*(?:No\.?|Number|#)\s*:\s*([A-Za-z0-9_/-]+)",
    "document_date": r"(?:Invoice|Document)\s*Date\s*:\s*([0-9/-]+)",
    "posting_date": r"Posting\s*Date\s*:\s*([0-9/-]+)",
    "gross_amount": r"(?:Gross\s*Amount|Grand\s*Total|Total\s*Amount)\s*:\s*([-()0-9.,]+)",
    "net_amount": r"(?:Net\s*Amount|Subtotal)\s*:\s*([-()0-9.,]+)",
    "tax_amount": r"(?:Tax\s*Amount|VAT\s*Amount)\s*:\s*([-()0-9.,]+)",
    "currency": r"Currency\s*:\s*([A-Z]{3})\b",
    "purchase_order": r"(?:Purchase\s*Order|PO)\s*(?:No\.?|Number)?\s*:\s*([A-Za-z0-9_/-]+)",
    "payment_reference": r"Payment\s*(?:Reference|Ref)\s*:\s*([A-Za-z0-9_/-]+)",
    "bank_account": r"(?:IBAN|Bank\s*Account)\s*:\s*([A-Z0-9 ]+)",
    "withholding_tax": r"(?:Withholding\s*Tax|TDS|TCS)\s*(?:Amount)?\s*:\s*([-()0-9.,]+)",
}
MONEY = {"gross_amount", "net_amount", "tax_amount", "withholding_tax", "cgst", "sgst", "igst"}
NUMERALS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬−", "01234567890123456789.,-")
ARABIC_FIELDS = {
    "supplier": r"(?:المورد|البائع)\s*:\s*([^\n]+)",
    "customer": r"(?:العميل|المشتري)\s*:\s*([^\n]+)",
    "invoice_number": r"رقم\s*(?:الفاتورة|الإشعار الدائن)\s*:\s*([^\s]+)",
    "document_date": r"تاريخ\s*(?:الفاتورة|المستند)\s*:\s*([0-9/-]+)",
    "gross_amount": r"(?:الإجمالي|المبلغ الإجمالي)\s*:\s*([-()0-9.,]+)",
    "net_amount": r"(?:صافي المبلغ|المجموع الفرعي)\s*:\s*([-()0-9.,]+)",
    "tax_amount": r"(?:مبلغ الضريبة|ضريبة القيمة المضافة)\s*:\s*([-()0-9.,]+)",
    "currency": r"العملة\s*:\s*([A-Z]{3})\b",
    "trn": r"رقم التسجيل الضريبي\s*:\s*(\d{15})",
}


def money(value, decimal_separator="."):
    value = value.translate(NUMERALS).strip().replace(" ", "")
    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]
    grouping, point = (r"\.", ",") if decimal_separator == "," else (",", r"\.")
    if not re.fullmatch(rf"[+-]?(?:\d{{1,3}}(?:{grouping}\d{{3}})+|\d+)(?:{point}\d+)?", value):
        raise ValueError("Amount does not follow the selected decimal/grouping convention")
    if decimal_separator == ",":
        value = value.replace(".", "").replace(",", ".")
    else:
        value = value.replace(",", "")
    result = Decimal(value)
    if not result.is_finite() or abs(result) >= Decimal("1e20"):
        raise ValueError("Amount exceeds supported precision")
    if int(result.as_tuple().exponent) < -8:
        raise ValueError("Amount exceeds supported precision")
    return str(result)


def structured(pages, country, decimal_separator=".", date_format="iso"):
    patterns = dict(FIELDS)
    if country == "IN":
        patterns.update(
            gstin=r"GSTIN\s*:\s*([A-Z0-9]{15})",
            cgst=r"CGST\s*(?:Amount)?\s*:\s*([-()0-9.,]+)",
            sgst=r"SGST\s*(?:Amount)?\s*:\s*([-()0-9.,]+)",
            igst=r"IGST\s*(?:Amount)?\s*:\s*([-()0-9.,]+)",
        )
    if country == "AE":
        patterns["trn"] = r"(?:Supplier\s*)?TRN\s*:\s*(\d{15})"
    fields: dict[str, Any] = {
        key: None for key in [*FIELDS, "gstin", "trn", "cgst", "sgst", "igst"]
    }
    locations = {}
    messages = []
    for key, pattern in patterns.items():
        found = []
        for page in pages:
            for block in page["blocks"]:
                candidates = [pattern]
                if key in ARABIC_FIELDS:
                    candidates.append(ARABIC_FIELDS[key])
                for match in (m for p in candidates for m in re.finditer(p, block["text"].translate(NUMERALS), re.I)):
                    found.append(
                        (
                            match.group(1).strip(),
                            {
                                "page": page["page"],
                                "block_id": block["id"],
                                "bbox": block.get("bbox"),
                                "raw_text": block["text"][match.start():match.end()],
                                "method": page.get("provider", "structured-text"),
                                "confidence": None,
                            },
                        )
                    )
        unique = {value for value, _ in found}
        if len(unique) > 1:
            messages.append(f"{key}: multiple conflicting values; human selection required")
            continue
        if not found:
            continue
        value, location = found[0]
        try:
            if key in MONEY:
                value = money(value, decimal_separator)
            elif key.endswith("date"):
                value = (
                    datetime.strptime(
                        value,
                        {"iso": "%Y-%m-%d", "dmy": "%d/%m/%Y", "mdy": "%m/%d/%Y"}[date_format],
                    )
                    .date()
                    .isoformat()
                )
            elif key == "currency":
                import pycountry

                value = value.upper()
                if pycountry.currencies.get(alpha_3=value) is None:
                    raise ValueError("Invalid ISO currency")
        except (ValueError, InvalidOperation):
            messages.append(f"{key}: parsing failed under selected convention")
            continue
        fields[key] = value
        locations[key] = location
    if all(fields[k] is not None for k in ["gross_amount", "net_amount", "tax_amount"]):
        if Decimal(fields["net_amount"]) + Decimal(fields["tax_amount"]) != Decimal(
            fields["gross_amount"]
        ):
            messages.append("Net plus tax does not equal gross")
    if fields["gstin"] or fields["trn"]:
        messages.append(
            "Tax identifier extracted only; authoritative registration verification has not been performed"
        )
    return {
        "fields": fields,
        "field_locations": locations,
        "validation_messages": messages,
        "decimal_separator": decimal_separator,
        "date_format": date_format,
        "review_status": "UNVERIFIED",
        "confidence_interpretation": "OCR recognition scores are raw model output, not calibrated accounting correctness probabilities",
        "language_limitations": "Arabic/English labeled fields only; scanned Arabic recognition depends on installed OCR models and requires review",
    }


def _image_blocks(image, engine, page):
    import numpy as np

    if image.width * image.height > 20_000_000:
        raise ValueError("Page exceeds pixel limit")
    result = engine(np.array(image.convert("RGB")))
    blocks = []
    if result.txts is not None:
        for index, text in enumerate(result.txts):
            blocks.append(
                {
                    "id": f"p{page}-b{index}",
                    "text": str(text),
                    "bbox": result.boxes[index].tolist(),
                    "recognition_score": float(result.scores[index]),
                    "coordinate_system": "pixels-top-left",
                }
            )
    return blocks


def _extract(path, media_type, country, options, expected_sha256):
    try:
        from PIL import Image

        with Path(path).open("rb") as source:
            original = source.read(options["max_bytes"] + 1)
        if len(original) > options["max_bytes"] or hashlib.sha256(original).hexdigest() != expected_sha256:
            raise ValueError("Original extraction document changed or exceeds its configured byte limit")
        Image.MAX_IMAGE_PIXELS = 20_000_000
        max_pages = options.get("max_pages", 20)
        engine = None

        def ocr(image, page):
            nonlocal engine
            if engine is None:
                from rapidocr import RapidOCR

                engine = RapidOCR(
                    params={
                        "Global.log_level": "error",
                        "EngineConfig.onnxruntime.intra_op_num_threads": 1,
                        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                    }
                )
            return _image_blocks(image, engine, page)

        pages: list[dict[str, Any]] = []

        def extract(data, kind, name="original"):
            if kind == "application/pdf":
                import pypdfium2 as pdfium
                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(data), strict=True)
                if reader.is_encrypted or len(reader.pages) > max_pages:
                    raise ValueError("Encrypted PDF or page limit exceeded")
                root: Any = reader.trailer["/Root"]
                if "/OpenAction" in root or "/JavaScript" in str(root.get("/Names", {})):
                    raise ValueError("Active PDF content is not supported")
                document = pdfium.PdfDocument(data)
                try:
                    for index in range(len(document)):
                        page = document[index]
                        textpage = page.get_textpage()
                        try:
                            text = textpage.get_text_range()
                            blocks = []
                            width, height = page.get_width(), page.get_height()
                            if text.strip() and not options.get("force_image"):
                                blocks = [
                                    {
                                        "id": f"p{len(pages) + 1}-b0",
                                        "text": text[:20000],
                                        "bbox": None,
                                        "coordinate_system": "digital-text-page",
                                        "recognition_score": None,
                                    }
                                ]
                                provider = "pdfium-text"
                            else:
                                scale = min(
                                    2.0,
                                    (20_000_000 / (page.get_width() * page.get_height())) ** 0.5,
                                )
                                bitmap = page.render(scale=scale)
                                try:
                                    image = bitmap.to_pil()
                                    width, height = image.size
                                    blocks = ocr(image, len(pages) + 1)
                                finally:
                                    bitmap.close()
                                provider = "rapidocr-local"
                            pages.append(
                                {
                                    "page": len(pages) + 1,
                                    "source_file": name,
                                    "source_page": index + 1,
                                    "width": width,
                                    "height": height,
                                    "blocks": blocks,
                                    "provider": provider,
                                }
                            )
                        finally:
                            textpage.close()
                            page.close()
                finally:
                    document.close()
            else:
                with Image.open(io.BytesIO(data)) as image:
                    if getattr(image, "n_frames", 1) > max_pages:
                        raise ValueError("Image page limit exceeded")
                    for index in range(getattr(image, "n_frames", 1)):
                        image.seek(index)
                        pages.append(
                            {
                                "page": len(pages) + 1,
                                "source_file": name,
                                "source_page": index + 1,
                                "width": image.width,
                                "height": image.height,
                                "blocks": ocr(image, len(pages) + 1),
                                "provider": "rapidocr-local",
                            }
                        )
            if len(pages) > max_pages:
                raise ValueError("Document batch exceeds page limit")

        if media_type == "application/zip":
            with zipfile.ZipFile(io.BytesIO(original)) as archive:
                entries = [e for e in archive.infolist() if not e.is_dir()]
                if len(entries) > 20 or sum(e.file_size for e in entries) > 100 * 1024 * 1024:
                    raise ValueError("ZIP limits exceeded")
                for entry in entries:
                    name = entry.filename
                    if (
                        ".." in Path(name).parts
                        or name.startswith(("/", "\\"))
                        or ":" in name
                        or entry.file_size / max(entry.compress_size, 1) > 200
                    ):
                        raise ValueError("Unsafe ZIP entry")
                    extension = Path(name).suffix.lower()
                    if extension not in {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
                        raise ValueError("Unsupported ZIP document")
                    if options.get("zip_member") and options["zip_member"] != name:
                        continue
                    extract(
                        archive.read(entry),
                        "application/pdf" if extension == ".pdf" else "image",
                        name,
                    )
        else:
            extract(original, media_type)
        if sum(len(b["text"]) for p in pages for b in p["blocks"]) > 200000:
            raise ValueError("Extracted text limit exceeded")
        if not any(p["blocks"] for p in pages):
            raise ValueError("No recognizable text; manual extraction required")
        model_spec = importlib.util.find_spec("rapidocr")
        if not model_spec or not model_spec.origin:
            raise ValueError("Local OCR provider installation is unavailable")
        output = {
            **structured(
                pages,
                country,
                options.get("decimal_separator", "."),
                options.get("date_format", "iso"),
            ),
            "pages": pages,
            "original_sha256": expected_sha256,
            "provider_versions": {
                name: importlib.metadata.version(name)
                for name in ["rapidocr", "onnxruntime", "pypdfium2"]
            },
            "model_artifacts": {
                model.name: hashlib.sha256(model.read_bytes()).hexdigest()
                for model in Path(model_spec.origin).parent.glob("models/*.onnx")
            },
            "human_review_required": True,
            "network_document_transfer": False,
        }
        names = sorted({p["source_file"] for p in pages})
        output["documents"] = [
            {
                "source_file": name,
                **structured(
                    [p for p in pages if p["source_file"] == name],
                    country,
                    options.get("decimal_separator", "."),
                    options.get("date_format", "iso"),
                ),
            }
            for name in names
        ]
        if len(names) > 1:
            output["fields"] = {key: None for key in output["fields"]}
            output["validation_messages"] = [
                "Multiple documents retained separately. Select a ZIP member for a separately reviewed vouching extraction."
            ]
        return {"result": output}
    except Exception as exc:
        return {"error": type(exc).__name__, "message": str(exc)[:300]}


def extract_document(path, media_type, country, options=None):
    from app.core.config import settings

    config = settings()
    if Path(path).stat().st_size > config.document_max_bytes:
        raise ValueError("OCR document exceeds configured byte limit")
    from app.modules.intelligence.extraction_runtime import extract

    options = {**(options or {}), "max_pages": config.document_max_pages, "max_bytes": config.document_max_bytes}
    return extract(path, media_type, country, options)


def preview_page(path, media_type, page_number, member=None):
    """Raster-only bounded preview; never serve an executable source document inline."""
    from PIL import Image

    from app.core.config import settings

    config = settings()
    if page_number < 1:
        raise ValueError("Page numbers start at one")
    if Path(path).stat().st_size > config.document_max_bytes:
        raise ValueError("Document preview exceeds configured byte limit")
    data = Path(path).read_bytes()
    if media_type == "application/zip":
        if not member:
            raise ValueError("Select a specific ZIP member")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo(member)
            if (
                info.file_size > 25 * 1024 * 1024
                or info.file_size / max(info.compress_size, 1) > 200
            ):
                raise ValueError("ZIP member preview limits exceeded")
            data = archive.read(info)
            media_type = "application/pdf" if Path(member).suffix.lower() == ".pdf" else "image"
    if media_type == "application/pdf":
        import pypdfium2 as pdfium

        with _PDFIUM_PREVIEW_LOCK, pdfium.PdfDocument(data) as document:
            if len(document) > config.document_max_pages or page_number > len(document):
                raise ValueError("PDF preview page out of bounds")
            page = document[page_number - 1]
            try:
                scale = min(2, (20_000_000 / max(1, page.get_width() * page.get_height())) ** 0.5)
                bitmap = page.render(scale=scale)
                try:
                    image = bitmap.to_pil().copy()
                finally:
                    bitmap.close()
            finally:
                page.close()
    else:
        Image.MAX_IMAGE_PIXELS = 20_000_000
        with Image.open(io.BytesIO(data)) as original:
            if getattr(original, "n_frames", 1) > config.document_max_pages:
                raise ValueError("Image preview page limit")
            original.seek(page_number - 1)
            if original.width * original.height > 20_000_000:
                raise ValueError("Image preview pixel limit")
            image = original.convert("RGB")
    output = io.BytesIO()
    image.save(output, format="PNG")
    image.close()
    return output.getvalue()
