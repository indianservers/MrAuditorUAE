"""Explicit GSP invoice/note sections; request context remains assessed evidence."""

import calendar
import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.json_documents import read_json_document
from app.modules.country_workflows.gstr1_schemas import SECTIONS
from app.modules.country_workflows.india_invoice_source import gstin, money
from app.modules.country_workflows.schemas import TaxDocument

HEADS = {"igst": "iamt", "cgst": "camt", "sgst": "samt", "cess": "csamt"}
DOC_FIELDS = {
    "b2b": set(
        [
            "cflag",
            "chksum",
            "diff_percent",
            "etin",
            "idt",
            "inum",
            "inv_typ",
            "irn",
            "irngendate",
            "itms",
            "opd",
            "pos",
            "rchrg",
            "srctyp",
            "updby",
            "val",
        ]
    ),
    "b2ba": set(
        [
            "cflag",
            "chksum",
            "diff_percent",
            "etin",
            "idt",
            "inum",
            "inv_typ",
            "itms",
            "oidt",
            "oinum",
            "opd",
            "pos",
            "rchrg",
            "updby",
            "val",
        ]
    ),
    "b2cl": set(["chksum", "diff_percent", "etin", "idt", "inum", "inv_typ", "itms", "val"]),
    "b2cla": set(
        [
            "chksum",
            "diff_percent",
            "etin",
            "flag",
            "idt",
            "inum",
            "inv_typ",
            "itms",
            "oidt",
            "oinum",
            "val",
        ]
    ),
    "cdnr": set(
        [
            "cflag",
            "chksum",
            "d_flag",
            "diff_percent",
            "flag",
            "idt",
            "inum",
            "inv_typ",
            "irn",
            "irngendate",
            "itms",
            "nt_dt",
            "nt_num",
            "ntty",
            "opd",
            "p_gst",
            "pos",
            "rchrg",
            "srctyp",
            "updby",
            "val",
        ]
    ),
    "cdnra": set(
        [
            "cflag",
            "chksum",
            "d_flag",
            "diff_percent",
            "flag",
            "idt",
            "inum",
            "inv_typ",
            "itms",
            "nt_dt",
            "nt_num",
            "ntty",
            "ont_dt",
            "ont_num",
            "opd",
            "p_gst",
            "pos",
            "rchrg",
            "updby",
            "val",
        ]
    ),
    "cdnur": set(
        [
            "chksum",
            "d_flag",
            "diff_percent",
            "flag",
            "idt",
            "inum",
            "irn",
            "irngendate",
            "itms",
            "nt_dt",
            "nt_num",
            "ntty",
            "p_gst",
            "pos",
            "srctyp",
            "typ",
            "val",
        ]
    ),
    "cdnura": set(
        [
            "chksum",
            "d_flag",
            "diff_percent",
            "flag",
            "idt",
            "inum",
            "itms",
            "nt_dt",
            "nt_num",
            "ntty",
            "ont_dt",
            "ont_num",
            "p_gst",
            "pos",
            "typ",
            "val",
        ]
    ),
    "exp": set(
        [
            "chksum",
            "diff_percent",
            "flag",
            "idt",
            "inum",
            "irn",
            "irngendate",
            "itms",
            "sbdt",
            "sbnum",
            "sbpcode",
            "srctyp",
            "val",
        ]
    ),
    "expa": set(
        [
            "chksum",
            "diff_percent",
            "flag",
            "idt",
            "inum",
            "itms",
            "oidt",
            "oinum",
            "sbdt",
            "sbnum",
            "sbpcode",
            "val",
        ]
    ),
}


def text(value, label, maximum=200):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError(f"Invalid GSTR-1 {label}")
    return value


def reference(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9/\-]{1,16}", value):
        raise ValueError("Invalid GSTR-1 invoice/note reference")
    return value


def day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}-\d{2}-\d{4}", value):
        raise ValueError("GSTR-1 dates require DD-MM-YYYY")
    return datetime.strptime(value, "%d-%m-%Y").date()


def numeric(value):
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ValueError("GSTR-1 native amounts must be unsigned JSON numbers")
    result = money(value)
    if result < 0:
        raise ValueError(
            "GSTR-1 profile requires unsigned values; credit-note sign is applied once"
        )
    return result


def array(value):
    if not isinstance(value, list) or len(value) > 1250:
        raise ValueError("GSTR-1 populations require bounded arrays")
    return value


def month_end(period):
    begin = datetime.strptime(period, "%Y-%m").date()
    return begin.replace(day=calendar.monthrange(begin.year, begin.month)[1])


def parse_gstr1(content, data):
    registration = gstin(data.gst_registration)
    end = month_end(data.gst_period)
    controls = {c.section: c for c in data.gstr1_section_controls}
    root = read_json_document(content)
    depth = 0
    while isinstance(root, dict) and not (set(root) & SECTIONS) and "data" in root and depth < 2:
        if (
            set(root) - {"data", "code", "status_cd", "timestamp", "transaction_id"}
            or root.get("code", 200) != 200
            or root.get("status_cd", "1") != "1"
        ):
            raise ValueError("Unsupported or unsuccessful GSTR-1 response wrapper")
        root = root["data"]
        depth += 1
    if not isinstance(root, dict) or set(root) != set(controls):
        raise ValueError(
            "Retain exactly the declared GSTR-1 invoice/note sections; aggregate sections and pagination require separate profiles"
        )
    rows = []
    documents = []
    seen = set()
    totals: dict[str, dict[str, Any]] = {
        section: {"document_count": 0, **{field: Decimal(0) for field in ("taxable_base", *HEADS)}}
        for section in controls
    }
    item_count = 0

    def emit(section, group, document, counterparty):
        nonlocal item_count
        if not isinstance(document, dict) or set(document) - DOC_FIELDS[section]:
            raise ValueError(
                "Unknown GSTR-1 document field; retain a supported complete section response"
            )
        note = section.startswith("cdn")
        amendment = section.endswith("a")
        required = {
            "chksum",
            "itms",
            "val",
            "nt_num" if note else "inum",
            "nt_dt" if note else "idt",
        }
        if note:
            required.add("ntty")
        if amendment:
            required.update({"ont_num", "ont_dt"} if note else {"oinum", "oidt"})
        if not required <= set(document):
            raise ValueError("Incomplete GSTR-1 invoice/note or amendment identity")
        ref = reference(document["nt_num" if note else "inum"])
        when = day(document["nt_dt" if note else "idt"])
        if when > end:
            raise ValueError("GSTR-1 document date is after its declared reporting month")
        typ = document.get("ntty") if note else "INV"
        if typ not in {"INV", "C", "D"}:
            raise ValueError(
                "GSTR-1 refund/reversal document types require a separately assessed profile"
            )
        document_type = {"INV": "invoice", "C": "credit-note", "D": "debit-note"}[typ]
        sign = -1 if typ == "C" else 1
        key = (section, counterparty, ref.casefold(), when, document_type)
        if key in seen:
            raise ValueError("Duplicate GSTR-1 document within the same section")
        seen.add(key)
        if len(seen) > 1250:
            raise ValueError("GSTR-1 exceeds 1,250 source documents")
        flags = []
        for field in ("flag", "cfs"):
            if field in group:
                text(group[field], field, 20)
        if group.get("flag") not in (None, "N"):
            flags.append("SOURCE_GROUP_FLAG_REQUIRES_REVIEW")
        if document.get("inv_typ") not in (None, "R", "DE", "SEWP", "SEWOP", "CBW"):
            flags.append("UNRECOGNISED_OUTWARD_INVOICE_TYPE_REQUIRES_REVIEW")
        original_ref = reference(document["ont_num" if note else "oinum"]) if amendment else None
        original_date = day(document["ont_dt" if note else "oidt"]) if amendment else None
        if original_date and original_date > end:
            raise ValueError("Original GSTR-1 amendment date is after the reporting month")
        if amendment:
            flags.append("OUTWARD_AMENDMENT_REQUIRES_ORIGINAL_POPULATION_RESOLUTION")
        for field in ("cflag", "flag"):
            if field in document:
                value = text(document[field], field, 20)
                if value != "N":
                    flags.append("SOURCE_RECORD_FLAG_REQUIRES_REVIEW")
        if document.get("d_flag") is not None:
            if document["d_flag"] != "Y":
                raise ValueError("Invalid GSTR-1 note de-link indicator")
            flags.append("SOURCE_NOTE_DELINK_REQUIRES_LINKAGE_REVIEW")
        if document.get("updby") not in (None, "S"):
            flags.append("SOURCE_UPDATER_REQUIRES_REVIEW")
        if document.get("rchrg") not in (None, "N", "Y"):
            raise ValueError("Invalid GSTR-1 reverse-charge indicator")
        if document.get("rchrg") == "Y":
            flags.append("REVERSE_CHARGE_REQUIRES_SEPARATE_ASSESSMENT")
        if document.get("p_gst") not in (None, "N", "Y"):
            raise ValueError("Invalid GSTR-1 pre-GST indicator")
        if document.get("p_gst") == "Y":
            flags.append("PRE_GST_DOCUMENT_REQUIRES_SEPARATE_ASSESSMENT")
        if "pos" in document and not re.fullmatch(r"\d{2}", str(document["pos"])):
            raise ValueError("Invalid GSTR-1 place of supply")
        for field in set(document) - {"itms", "val", "diff_percent"}:
            text(document[field], field, 512 if field in {"chksum", "irn"} else 200)
        if "diff_percent" in document:
            numeric(document["diff_percent"])
        values = {field: Decimal(0) for field in ("taxable_base", *HEADS)}
        item_ids = set()
        for item in array(document["itms"]):
            item_count += 1
            if item_count > 20000:
                raise ValueError("GSTR-1 exceeds 20,000 rate/item records")
            if section.startswith("exp"):
                detail = item
                if not isinstance(detail, dict) or set(detail) - {"rt", "txval", "iamt", "csamt"}:
                    raise ValueError("Unsupported GSTR-1 export rate item")
            else:
                if not isinstance(item, dict) or set(item) != {"num", "itm_det"}:
                    raise ValueError("GSTR-1 items require explicit rate/item identities")
                number = numeric(item["num"])
                if number < 1 or number != number.to_integral_value() or number in item_ids:
                    raise ValueError("Duplicate or invalid GSTR-1 item number")
                item_ids.add(number)
                detail = item["itm_det"]
                if not isinstance(detail, dict) or set(detail) - {"rt", "txval", *HEADS.values()}:
                    raise ValueError("Unknown GSTR-1 item amount field")
            if not {"rt", "txval"} <= set(detail):
                raise ValueError("GSTR-1 rate item lacks taxable value or rate")
            numeric(detail["rt"])
            values["taxable_base"] += numeric(detail["txval"])
            for head, field in HEADS.items():
                values[head] += numeric(detail.get(field, 0))
        if not document["itms"]:
            raise ValueError("GSTR-1 document has no rate/item population")
        gross = numeric(document["val"])
        gross_difference = (
            gross - values["taxable_base"] - sum((values[h] for h in HEADS), Decimal(0))
        )
        if counterparty == "EXPORT:WOPAY" and any(values[h] for h in HEADS):
            flags.append("EXPORT_WITHOUT_PAYMENT_TAX_VALUES_REQUIRE_REVIEW")
        if gross_difference:
            flags.append("INVOICE_VALUE_REQUIRES_ADDITIONAL_AMOUNT_ASSESSMENT")
        totals[section]["document_count"] += 1
        for field, value in values.items():
            totals[section][field] += value * sign
        source_metadata = json.loads(
            json.dumps(
                {
                    "group": {k: v for k, v in group.items() if k not in {"inv", "nt"}},
                    "document": {k: v for k, v in document.items() if k != "itms"},
                },
                default=str,
            )
        )
        for head in HEADS:
            row = TaxDocument(
                id=f"gstr1:{len(seen)}:{head}",
                registration=registration,
                counterparty=counterparty,
                reference=ref,
                period=data.gst_period,
                date=when,
                currency="INR",
                document_type=document_type,
                net=values["taxable_base"] * sign,
                tax=values[head] * sign,
                component=head.upper(),
            ).model_dump(mode="json")
            row.update(
                source_section=section,
                source_review_reasons=sorted(set(flags)),
                native_zero_component=values[head] == 0,
                source_reverse_charge=document.get("rchrg"),
                original_reference=original_ref,
                original_date=original_date.isoformat() if original_date else None,
                source_document_metadata=source_metadata,
                source_declared_invoice_value=str(gross),
                source_invoice_value_difference=str(gross_difference),
                source_counterparty_basis="REGISTERED_COUNTERPARTY"
                if section in {"b2b", "b2ba", "cdnr", "cdnra"}
                else "DECLARED_UNREGISTERED_OR_EXPORT_CATEGORY_NOT_CUSTOMER_IDENTITY",
            )
            rows.append(row)
        documents.append(
            {
                "section": section,
                "reference": ref,
                "date": when.isoformat(),
                "counterparty": counterparty,
                "source_item_count": len(document["itms"]),
                "rate_items": json.loads(json.dumps(document["itms"], default=str)),
            }
        )

    for section, groups in root.items():
        for group in array(groups):
            if not isinstance(group, dict):
                raise ValueError("Malformed GSTR-1 section group")
            if section in {"cdnur", "cdnura"}:
                category = group.get("typ")
                if category not in {"B2CL", "EXPWP", "EXPWOP"}:
                    raise ValueError("Unsupported GSTR-1 unregistered-note category")
                pos = group.get("pos")
                if category == "B2CL" and (
                    not isinstance(pos, str) or not re.fullmatch(r"\d{2}", pos)
                ):
                    raise ValueError(
                        "Unregistered B2CL notes require explicit place-of-supply scope"
                    )
                party = (
                    "UNREGISTERED:POS:" + str(pos)
                    if category == "B2CL"
                    else "EXPORT:" + {"EXPWP": "WPAY", "EXPWOP": "WOPAY"}[category]
                )
                emit(section, {}, group, party)
                continue
            allowed = (
                {"inv", "nt", "ctin", "cfs", "flag"}
                if section in {"b2b", "b2ba", "cdnr", "cdnra"}
                else {"pos", "inv"}
                if section in {"b2cl", "b2cla"}
                else {"exp_typ", "inv"}
            )
            if set(group) - allowed:
                raise ValueError("Unknown GSTR-1 grouping field")
            if section in {"b2b", "b2ba", "cdnr", "cdnra"}:
                party = gstin(group.get("ctin"))
            elif section in {"b2cl", "b2cla"}:
                pos = group.get("pos")
                if not isinstance(pos, str) or not re.fullmatch(r"\d{2}", pos):
                    raise ValueError("B2CL requires explicit place-of-supply scope")
                party = "UNREGISTERED:POS:" + pos
            else:
                category = group.get("exp_typ")
                if category not in {"WPAY", "WOPAY"}:
                    raise ValueError("Unsupported GSTR-1 export category")
                party = "EXPORT:" + category
            for doc in array(group.get("nt" if section.startswith("cdn") else "inv")):
                emit(section, group, doc, party)
    for section, control in controls.items():
        if totals[section] != control.model_dump(exclude={"section"}):
            raise ValueError(
                "Independent GSTR-1 section document/base/component controls do not agree"
            )
    if len(seen) != data.expected_documents:
        raise ValueError("Independent GSTR-1 whole-source document count does not agree")
    return rows, {
        "currency": "INR",
        "supplier_gstin": registration,
        "return_period": data.gst_period,
        "direction": "sale",
        "declared_section_controls": [
            c.model_dump(mode="json") for c in data.gstr1_section_controls
        ],
        "document_count": len(seen),
        "rate_item_count": item_count,
        "original_rate_records": documents,
        "transparent_wrapper_depth": depth,
        "context_evidence_version_id": str(data.gstr1_context_evidence_version_id),
        "retrieval_scope_assessment": data.gstr1_retrieval_assessment,
        "filing_status": "NOT_ESTABLISHED_BY_DOCUMENT_RESPONSE",
        "provider_authenticity": "NOT_VERIFIED",
        "irp_authenticity": "NOT_VERIFIED",
        "source_population_scope": "DECLARED_RETAINED_INVOICE_NOTE_SECTIONS_NOT_COMPLETE_GSTR1_RETURN",
        "profile_references": [
            f"https://developer.sandbox.co.in/api-reference/gst/compliance/endpoints/taxpayer/gstr-1/documents/{section}"
            for section in sorted(controls)
        ],
    }
