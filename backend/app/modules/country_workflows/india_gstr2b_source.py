"""Explicit GSTR-2B v1.0 document profiles from first-party GSP documentation.

An import retains documentary amounts and review flags. It does not authenticate
GSTN, net amendments against historic credits, or determine recoverable ITC.
"""

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal

from app.core.json_documents import read_json_document
from app.modules.country_workflows.india_invoice_source import gstin, money
from app.modules.country_workflows.schemas import TaxDocument

HEADS = ("igst", "cgst", "sgst", "cess")
SECTIONS = {
    "b2b",
    "b2ba",
    "cdnr",
    "cdnra",
    "isd",
    "isda",
    "impg",
    "impgsez",
    "ecom",
    "ecoma",
    "itcrev",
}
PAGINATION = {
    "fc",
    "file_count",
    "file_number",
    "next",
    "next_page",
    "next_token",
    "has_more",
    "hasMore",
    "nextPage",
}
PROFILES = [
    "https://developer.sandbox.co.in/api-reference/gst/compliance/endpoints/taxpayer/gstr-2b/document",
    "https://sandbox-docs.readme.io/reference/upload-gstr-2b",
]


def identifier(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("Invalid GSTR-2B document identifier")
    value = str(value)
    if not 1 <= len(value) <= 120 or not value.strip() or any(ord(ch) < 32 for ch in value):
        raise ValueError("Invalid GSTR-2B document identifier")
    return value


def day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}-\d{2}-\d{4}", value):
        raise ValueError("GSTR-2B dates must use DD-MM-YYYY")
    try:
        return datetime.strptime(value, "%d-%m-%Y").date()
    except ValueError:
        raise ValueError("Invalid GSTR-2B date") from None


def period(value):
    if not isinstance(value, str) or not re.fullmatch(r"(0[1-9]|1[0-2])\d{4}", value):
        raise ValueError("GSTR-2B return period must use MMYYYY")
    datetime.strptime(value, "%m%Y")
    return value[2:] + "-" + value[:2]


def array(value):
    if not isinstance(value, list) or len(value) > 1250:
        raise ValueError("GSTR-2B section must be a bounded array")
    return value


def unwrap(root):
    checksums: list[str] = []
    for depth in range(5):
        if not isinstance(root, dict):
            break
        if any(root.get(key) not in (None, False, "", 0) for key in PAGINATION):
            raise ValueError("Paged GSTR-2B responses require verified part assembly before import")
        if (
            root.get("code", 200) != 200
            or str(root.get("status_cd", "1")) != "1"
            or root.get("error")
            or root.get("errors")
        ):
            raise ValueError(
                "GSTR-2B provider/business response is not a complete successful document"
            )
        if "chksum" in root:
            checksum = root["chksum"]
            if not isinstance(checksum, str) or not 1 <= len(checksum) <= 512:
                raise ValueError("Invalid GSTR-2B checksum metadata")
            checksums.append(checksum)
        if "docdata" in root:
            if "data" in root:
                raise ValueError("Competing GSTR-2B payloads are ambiguous")
            return root, depth, checksums
        root = root.get("data")
    raise ValueError("Select a supported plain or transparently wrapped GSTR-2B document")


def amounts(document, *, net_available=True):
    def values(record):
        fields = {key: money(record.get(key, 0)) for key in HEADS}
        fields["txval"] = money(record["txval"]) if net_available else Decimal(0)
        if any(value < 0 for value in fields.values()):
            raise ValueError(
                "GSTR-2B amounts in this profile are unsigned; note direction is applied separately"
            )
        return fields

    if "items" not in document:
        return values(document), "invoice-totals"
    items = array(document["items"])
    if not items:
        raise ValueError("GSTR-2B item population is empty")
    totals = {key: Decimal(0) for key in (*HEADS, "txval")}
    serials = set()
    for item in items:
        serial = identifier(item["num"])
        if serial in serials:
            raise ValueError("Duplicate GSTR-2B item serial")
        serials.add(serial)
        for key, value in values(item).items():
            totals[key] += value
    for key, value in totals.items():
        if key in document and money(document[key]) != value:
            raise ValueError("GSTR-2B item totals differ from the document-level amount")
    return totals, "item-sums"


def summary_nonzero(node, depth=0):
    if depth > 20:
        raise ValueError("GSTR-2B summary nesting exceeds the supported profile")
    if isinstance(node, dict):
        return any(
            money(value) != 0
            if key in {*HEADS, "txval", "ttldocs"}
            else summary_nonzero(value, depth + 1)
            for key, value in node.items()
        )
    if isinstance(node, list):
        return any(summary_nonzero(value, depth + 1) for value in node)
    return False


def parse_gstr2b(content, data):
    if not data.gst_registration or not data.gst_period or data.expected_documents is None:
        raise ValueError("Select the recipient GSTIN, return month and independent document count")
    registration = gstin(data.gst_registration)
    root, depth, checksums = unwrap(read_json_document(content))
    if (
        root.get("version") != "1.0"
        or gstin(root.get("gstin")) != registration
        or period(root.get("rtnprd")) != data.gst_period
    ):
        raise ValueError(
            "GSTR-2B profile version, recipient GSTIN or reporting month differs from the selected scope"
        )
    generated = day(root.get("gendt"))
    documents = root["docdata"]
    if not isinstance(documents, dict) or not set(documents) <= SECTIONS:
        raise ValueError("Unsupported GSTR-2B document section; no population was imported")
    rows, seen = [], set()
    section_counts: Counter[str] = Counter()
    shapes: Counter[str] = Counter()
    section_totals: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    b2b_counts: Counter[tuple] = Counter()

    def emit(section, supplier, document, *, reversal=False, import_record=False):
        if sum(section_counts.values()) >= 1250:
            raise ValueError("GSTR-2B exceeds 1,250 documents / 5,000 component rows")
        flags = []
        amendment = section in {"b2ba", "cdnra", "isda", "ecoma"}
        net_available = section not in {"isd", "isda"}
        if import_record:
            port = identifier(document["portcode"])
            if not re.fullmatch(r"[A-Z0-9]{6}", port) or not re.fullmatch(
                r"\d{1,12}", identifier(document["boenum"])
            ):
                raise ValueError("Invalid GSTR-2B customs port or bill-of-entry identifier")
            counterparty = "CUSTOMS:" + port
            reference, when, doc_type = (
                identifier(document["boenum"]),
                day(document["boedt"]),
                "invoice",
            )
            if document.get("isamd") not in {"Y", "N"}:
                raise ValueError("GSTR-2B import amendment flag is required")
            amendment = document["isamd"] == "Y"
            if (
                document.get("isReversal") == "Y"
                or document.get("amendType") in {"A", "G"}
                or document.get("itcRedReq") == "Y"
                or any(key in document for key in ("declIgst", "declCess"))
            ):
                flags.append("CUSTOMS_GSTIN_OR_DECLARED_CREDIT_ADJUSTMENT_REVIEW")
        else:
            counterparty = gstin(supplier["ctin"])
            if section in {"isd", "isda"}:
                if document["doctyp"] not in {"ISDI", "ISDC"}:
                    raise ValueError("Unsupported GSTR-2B ISD document type")
                reference, when = identifier(document["docnum"]), day(document["docdt"])
                doc_type = "credit-note" if document["doctyp"] == "ISDC" else "invoice"
                flags.append("ISD_TAX_ALLOCATION_HAS_NO_TAXABLE_BASE")
            elif section in {"cdnr", "cdnra"}:
                if document["typ"] not in {"C", "D"}:
                    raise ValueError("GSTR-2B note direction must be C or D")
                reference, when = identifier(document["ntnum"]), day(document["dt"])
                doc_type = "credit-note" if document["typ"] == "C" else "debit-note"
            else:
                if document["typ"] not in {"R", "DE", "SEWP", "SEWOP", "CBW"}:
                    raise ValueError("Unsupported GSTR-2B invoice supply type")
                reference, when, doc_type = (
                    identifier(document["inum"]),
                    day(document["dt"]),
                    "invoice",
                )
        if when.strftime("%Y-%m") > data.gst_period or when > generated:
            raise ValueError("GSTR-2B document date is after its reporting or generation scope")
        if amendment:
            flags.append("AMENDMENT_REQUIRES_ORIGINAL_AND_CREDIT_HISTORY_REVIEW")
        if reversal:
            flags.append("ITC_REVERSAL_REQUIRES_SEPARATE_CREDIT_HISTORY_REVIEW")
        credit = document.get("itcavl", document.get("itcelg"))
        if credit not in (None, "Y", "N"):
            raise ValueError("Invalid GSTR-2B credit-availability flag")
        if credit == "N":
            flags.append("SOURCE_MARKS_CREDIT_UNAVAILABLE")
        ims = document.get("imsStatus")
        if ims is not None and (not isinstance(ims, str) or len(ims) > 20):
            raise ValueError("Invalid IMS action field")
        if ims not in (None, "A", "R", "P", "N"):
            flags.append("UNRECOGNISED_IMS_ACTION_REQUIRES_REVIEW")
        status = "rejected" if ims == "R" else "pending" if ims == "P" else "active"
        reverse_charge = document.get("rev")
        if reverse_charge not in (None, "Y", "N"):
            raise ValueError("Invalid GSTR-2B reverse-charge flag")
        original_reference = document.get("oinum", document.get("ontnum", document.get("odocnum")))
        original_date = document.get("oidt", document.get("ontdt", document.get("odocdt")))
        original_type = document.get("onttyp", document.get("odoctyp"))
        if original_reference is not None:
            original_reference = identifier(original_reference)
        if original_date is not None:
            original_date = day(original_date).isoformat()
        if original_type is not None:
            original_type = identifier(original_type)
            if original_type not in {"C", "D", "ISDI", "ISDC"}:
                flags.append("UNRECOGNISED_ORIGINAL_DOCUMENT_TYPE")
        is_reversal, amendment_type = document.get("isReversal"), document.get("amendType")
        if is_reversal not in (None, "Y", "N"):
            raise ValueError("Invalid GSTR-2B customs reversal flag")
        if amendment_type is not None:
            amendment_type = identifier(amendment_type)
            if amendment_type not in {"A", "G", "NA"}:
                flags.append("UNRECOGNISED_CUSTOMS_AMENDMENT_TYPE")
        identity = (section, reversal, counterparty, reference.casefold(), when, doc_type)
        if identity in seen:
            raise ValueError("Duplicate GSTR-2B document within the same section")
        seen.add(identity)
        values, shape = amounts(document, net_available=net_available)
        shapes[shape] += 1
        sign = -1 if doc_type == "credit-note" else 1
        section_key = ("itcrev/" if reversal else "") + section
        section_counts[section_key] += 1
        if section == "b2b" and not reversal:
            b2b_counts[(counterparty, supplier.get("supprd"))] += 1
        for head in HEADS:
            tax = values[head] * sign
            section_totals[section_key] += tax
            row = TaxDocument(
                id=f"gstr2b:{len(seen)}:{head}",
                registration=registration,
                counterparty=counterparty,
                reference=reference,
                period=data.gst_period,
                date=when,
                currency="INR",
                document_type=doc_type,
                net=values["txval"] * sign,
                tax=tax,
                component=head.upper(),
                status=status,
            ).model_dump(mode="json")
            row.update(
                source_section=section_key,
                source_review_reasons=flags,
                native_zero_component=tax == 0,
                net_available=net_available,
                source_itc_availability=credit,
                source_ims_status=ims,
                source_supplier_period=supplier.get("supprd"),
                source_reverse_charge=reverse_charge,
                original_document_type=original_type,
                source_declared_igst=str(money(document["declIgst"]))
                if "declIgst" in document
                else None,
                source_declared_cess=str(money(document["declCess"]))
                if "declCess" in document
                else None,
                source_is_reversal=is_reversal,
                source_amendment_type=amendment_type,
                original_reference=original_reference,
                original_date=original_date,
                import_port=document.get("portcode"),
                import_supplier=supplier.get("ctin") if import_record else None,
                credit_eligibility="NOT_DETERMINED",
                provider_authenticity="NOT_VERIFIED",
            )
            rows.append(row)

    def walk(sections, *, reversal=False):
        if not isinstance(sections, dict) or not set(sections) <= SECTIONS:
            raise ValueError("Unsupported GSTR-2B nested document section")
        for section, groups in sections.items():
            if section == "itcrev":
                if reversal:
                    raise ValueError("Nested credit-reversal populations are unsupported")
                for group in array(groups):
                    walk(group, reversal=True)
            elif section == "impg":
                for document in array(groups):
                    emit(section, {}, document, reversal=reversal, import_record=True)
            else:
                field = (
                    "boe"
                    if section == "impgsez"
                    else "doclist"
                    if section in {"isd", "isda"}
                    else "nt"
                    if section in {"cdnr", "cdnra"}
                    else "inv"
                )
                for supplier in array(groups):
                    if supplier.get("supprd") is not None:
                        period(supplier["supprd"])
                    if section == "impgsez":
                        gstin(supplier["ctin"])
                    for document in array(supplier[field]):
                        emit(
                            section,
                            supplier,
                            document,
                            reversal=reversal,
                            import_record=section == "impgsez",
                        )

    try:
        walk(documents)
        summaries = root.get("cpsumm", {})
        if isinstance(summaries, dict) and "b2b" in summaries:
            summary_counts: Counter[tuple] = Counter()
            for summary in array(summaries["b2b"]):
                count = summary["ttldocs"]
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    raise ValueError("Invalid GSTR-2B B2B counterparty count")
                summary_counts[(gstin(summary["ctin"]), summary.get("supprd"))] += count
            if summary_counts != b2b_counts:
                raise ValueError("GSTR-2B B2B counterparty document counts do not agree")
        if len(seen) != data.expected_documents:
            raise ValueError("GSTR-2B independent document-count control does not agree")
        if not seen and (
            summary_nonzero(root.get("itcsumm")) or summary_nonzero(root.get("cpsumm"))
        ):
            raise ValueError(
                "GSTR-2B summaries contain amounts/counts but its document population is empty"
            )
    except (KeyError, TypeError, AttributeError):
        raise ValueError(
            "Incomplete or malformed GSTR-2B document profile; inspect the retained file"
        ) from None
    return rows, {
        "currency": "INR",
        "recipient_gstin": registration,
        "return_period": data.gst_period,
        "generation_date": generated.isoformat(),
        "schema_version": root["version"],
        "transparent_wrapper_depth": depth,
        "document_count": len(seen),
        "section_document_counts": dict(section_counts),
        "amount_layout_counts": dict(shapes),
        "section_signed_tax_totals": {key: str(value) for key, value in section_totals.items()},
        "row_grain": "FOUR_TAX_COMPONENT_ROWS_PER_SOURCE_DOCUMENT",
        "control_total_basis": "SUM_OF_DOCUMENT_TAX_FIELDS_INCLUDING_REVERSALS_NOT_ITC_ENTITLEMENT",
        "taxable_base_basis": "REPEATED_BY_COMPONENT_ISD_UNAVAILABLE_NOT_ZERO_EVIDENCE",
        "itc_summary": json.loads(json.dumps(root.get("itcsumm"), default=str)),
        "counterparty_summary": json.loads(json.dumps(root.get("cpsumm"), default=str)),
        "summary_reconciliation": "B2B_COUNTERPARTY_COUNTS_WHEN_FLAT_SUMMARY_PRESENT_OTHER_SUMMARIES_NOT_RECONCILED",
        "source_checksum": root.get("chksum"),
        "wrapper_checksums": checksums,
        "provider_authenticity": "NOT_VERIFIED",
        "credit_eligibility": "NOT_DETERMINED",
        "profile_references": PROFILES,
    }
