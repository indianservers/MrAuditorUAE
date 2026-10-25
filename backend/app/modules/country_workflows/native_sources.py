"""Native evidence readers; never infer payment execution or statutory eligibility.

CAMT statement-level booked entries are retained once (not added to their detail
records). MT940 accepts complete statements assembled from sequenced messages. The WPS profile implements
the bank-published EDR records followed by one SCR control trailer.
"""

import csv
import hashlib
import io
import re
from datetime import date, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as safe_xml
from pydantic import ValidationError

from app.modules.country_workflows.schemas import Transaction
from app.modules.country_workflows.sources import MAX_BYTES

FORMATS: list[dict[str, Any]] = [
    {"id": "india-gstr1-document-series-json", "label": "India GSTR-1 document issue series JSON", "countries": ["IN"], "table_type": "gst-document-series", "description": "Retained Table 13 ranges and issued/cancelled/net counts; no inferred continuity or filing proof", "source": "https://whitebooks.in/developer/gst-api/put-gstr1-retsave"},
    {"id":"india-gstr1-documents-json","label":"India GSTR-1 outward invoice/note JSON","countries":["IN"],"table_type":"tax-documents","description":"Ten declared invoice/note sections, independent head/base/count controls and retained request context; amendments stay unresolved, no filing conclusion","source":"https://developer.sandbox.co.in/api-reference/gst/compliance/endpoints/taxpayer/gstr-1/documents/b2b"},
    {"id": "india-gstr1-summary-json", "label": "India GSTR-1 summary JSON - explicit hierarchy metrics", "countries": ["IN"], "table_type": "gst-summary-metrics", "description": "Preserves section/subsection/counterparty metrics and independent count/INR controls; no netting across hierarchy or filing conclusion", "source": "https://developer.sandbox.co.in/api-reference/gst/compliance/endpoints/taxpayer/gstr-1/documents/gstr_1"},
    {"id": "india-epfo-arrear-ecr-v2", "label": "India EPFO ECR 2.0 arrears - eight-field text",
     "countries": ["IN"], "table_type": "obligations",
     "description": "Explicit arrear layout; independent wage/contribution controls and retained month/disbursement context; no filing, bank payment or current portal compatibility qualification",
     "source": "https://www.epfindia.gov.in/site_docs/PDFs/EPFOUnifiedPortal/Introduction_ECR2.0.pdf"},
    {
        "id": "uae-wps-sif-evp",
        "label": "UAE WPS SIF - Emirates Islamic EDR / EVP / SCR",
        "countries": ["AE"], "table_type": "obligations",
        "description": "Explicit variable-pay profile with adjacent employee/routing binding and independent seven-component controls; instructions do not establish payment",
        "source": "https://www.emiratesislamic.ae/-/media/ei/pdfs/business-online/salary-and-utility-payments/ei_businessonline_salary_wps_file_creation_user_guide.pdf",
    },
    {
        "id": "india-gstr2b-json",
        "label": "India GSTR-2B v1.0 document JSON",
        "countries": ["IN"],
        "table_type": "tax-documents",
        "description": "Explicit item/total profiles; four component rows per document; preserves notes, amendments, ISD, imports and reversals; credit eligibility is not determined",
        "source": "https://developer.sandbox.co.in/api-reference/gst/compliance/endpoints/taxpayer/gstr-2b/document",
    },
    {
        "id": "india-epfo-ecr",
        "label": "India EPFO monthly ECR text",
        "countries": ["IN"],
        "table_type": "obligations",
        "description": "Eleven #~# fields; declared establishment/month/member controls; return text does not prove filing, payment or statutory rate correctness",
        "source": "https://www.epfindia.nic.in/site_docs/PDFs/MiscPDFs/User-Manual-ReECR_v3.0.pdf",
    },
    {
        "id": "india-inv01-json",
        "label": "India INV-01 1.1 invoice JSON",
        "countries": ["IN"],
        "table_type": "tax-documents",
        "description": "Plain registered-party invoices, credit and debit notes; five component rows per document; IRP authenticity and ITC eligibility are not verified",
        "source": "https://einvoice6.gst.gov.in/content/notified-e-invoice-schema/",
    },
    {
        "id": "canonical-csv",
        "label": "Controlled canonical CSV",
        "countries": [],
        "table_type": None,
        "description": "Explicit field contract with declared row counts and currency controls",
    },
    {
        "id": "camt053",
        "label": "ISO 20022 CAMT.053 bank statement",
        "countries": [],
        "table_type": "transactions",
        "description": "Booked entries and single-file statement pages with explicit sequence, interim balance and whole-statement controls; select a statement when several are present",
        "source": "https://www.swift.com/sites/default/files/files/pmpg-interbank-statement-creation-market-practice-final-version.pdf",
    },
    {
        "id": "swift-mt940",
        "label": "SWIFT MT940 complete bank statement",
        "countries": [],
        "table_type": "transactions",
        "description": "One complete statement across up to 100 sequenced messages; missing pages, broken balance carry-forward and mixed accounts fail closed",
        "source": "https://www.swift.com/sites/default/files/files/pmpg-interbank-statement-creation-market-practice-final-version.pdf",
    },
    {
        "id": "uae-wps-sif",
        "label": "UAE WPS SIF — EDR / SCR trailer",
        "countries": ["AE"],
        "table_type": "obligations",
        "description": "Bank-published trailer layout; employee count and fixed/variable salary totals checked; instructions are not payment confirmation",
        "source": "https://netbanking.mashreqbank.com/B001/WPSFileUploadGuidelines_eng.html",
    },
]
CAMT_VERSIONS = {"02", "04", "08", "09", "10", "11", "12", "13"}


def formats(country):
    return [dict(f, available=not f["countries"] or country in f["countries"]) for f in FORMATS]


def number(value, *, comma=False, places=8):
    value = str(value).strip()
    separator = "," if comma else r"\."
    pattern = rf"\d{{1,20}}(?:{separator}\d{{1,{places}}})?"
    if not re.fullmatch(pattern, value):
        raise ValueError("Invalid native decimal amount")
    return Decimal(value.replace(",", "."))


def iso_date(value):
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        raise ValueError("Invalid native ISO date") from None


def single(elements, label):
    if len(elements) != 1:
        raise ValueError(f"Exactly one {label} is required in the selected statement")
    return elements[0]


def camt(content, data):
    from app.modules.country_workflows.camt_pages import assemble

    return assemble(content, data, _camt_single)


def _camt_single(content, data, *, booking_window=None, allow_interim=False):
    try:
        root = safe_xml.fromstring(
            content, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except Exception:
        raise ValueError("Invalid or unsafe CAMT XML") from None
    found = re.fullmatch(
        r"\{(urn:iso:std:iso:20022:tech:xsd:camt\.053\.001\.(\d{2}))\}Document", root.tag
    )
    if not found or found[2] not in CAMT_VERSIONS:
        raise ValueError("Unsupported CAMT.053 namespace version")
    ns = {"c": found[1]}

    def find(element, path):
        return element.find("/".join("c:" + part for part in path.split("/")), ns)

    def all_(element, path):
        return element.findall("/".join("c:" + part for part in path.split("/")), ns)

    def value(element, path, default=None):
        node = find(element, path)
        return node.text.strip() if node is not None and node.text else default

    def entry_date(element, path):
        parents = all_(element, path)
        if not parents:
            return None
        choices = [*all_(element, path + "/Dt"), *all_(element, path + "/DtTm")]
        if len(parents) != 1 or len(choices) != 1 or len(parents[0]) != 1 or not choices[0].text:
            raise ValueError("CAMT entry requires one unambiguous booking/value date choice")
        return iso_date(choices[0].text.strip())

    for pagination in all_(root, "BkToCstmrStmt/GrpHdr/MsgPgntn"):
        if (
            value(pagination, "LastPgInd") not in {None, "true", "1"}
            or value(pagination, "PgNb", "1") != "1"
        ):
            raise ValueError("Paged CAMT files require complete-page assembly before import")
    statements = all_(root, "BkToCstmrStmt/Stmt")
    if not statements or len(statements) > 100:
        raise ValueError("CAMT statement selection is missing or exceeds the file bound")
    ids = [value(s, "Id") for s in statements]
    if None in ids or len(set(ids)) != len(ids):
        raise ValueError("Missing or duplicated CAMT statement identifiers")
    selected = statements
    if data.statement_identifier:
        selected = [s for s in selected if value(s, "Id") == data.statement_identifier]
    if data.account_identifier:
        selected = [
            s
            for s in selected
            if (value(s, "Acct/Id/IBAN") or value(s, "Acct/Id/Othr/Id")) == data.account_identifier
        ]
    statement = single(selected, "unambiguous CAMT statement selection")
    account = value(statement, "Acct/Id/IBAN") or value(statement, "Acct/Id/Othr/Id")
    currency = value(statement, "Acct/Ccy")
    if not account or not re.fullmatch("[A-Z]{3}", currency or ""):
        raise ValueError("CAMT account identifier and account currency are required")
    pagination = find(statement, "StmtPgntn")
    if pagination is not None and (
        value(pagination, "LastPgInd") not in {"true", "1"} or value(pagination, "PgNb") != "1"
    ):
        raise ValueError("Paged CAMT statements require complete-page assembly before import")

    def balance(code):
        node = single(
            [b for b in all_(statement, "Bal") if value(b, "Tp/CdOrPrtry/Cd") == code],
            code + " balance",
        )
        if find(node, "Tp/SubTp") is not None and not allow_interim:
            raise ValueError("Interim CAMT balances require complete-page assembly")
        amt = find(node, "Amt")
        if amt is None or amt.attrib.get("Ccy") != currency:
            raise ValueError("CAMT balance currency differs from the selected account")
        direction = value(node, "CdtDbtInd")
        if direction not in {"CRDT", "DBIT"}:
            raise ValueError("Invalid CAMT balance direction")
        when = value(node, "Dt/Dt") or value(node, "Dt/DtTm")
        if not when:
            raise ValueError("CAMT balance date is required")
        return number(amt.text) * (1 if direction == "CRDT" else -1), iso_date(when)

    opening, start = balance("OPBD")
    closing, end = balance("CLBD")
    if end < start:
        raise ValueError("CAMT balance dates are reversed")
    entries = all_(statement, "Ntry")
    if len(entries) > 5000:
        raise ValueError("Native bank source exceeds 5,000 entries")
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, 1):
        status = value(entry, "Sts/Cd") or value(entry, "Sts")
        if status != "BOOK":
            raise ValueError(
                "Only booked CAMT entries are supported; pending records cannot be silently omitted"
            )
        reversal_nodes = all_(entry, "RvslInd")
        reversal = value(entry, "RvslInd") if reversal_nodes else "false"
        if len(reversal_nodes) > 1 or reversal not in {"true", "false", "1", "0"}:
            raise ValueError("Unsupported CAMT reversal indicator; assess the original bank entry")
        amt = find(entry, "Amt")
        direction = value(entry, "CdtDbtInd")
        when = entry_date(entry, "BookgDt")
        valued = entry_date(entry, "ValDt")
        if (
            amt is None
            or amt.attrib.get("Ccy") != currency
            or direction not in {"CRDT", "DBIT"}
            or not when
        ):
            raise ValueError(
                f"Invalid amount, currency, direction or booking date in CAMT entry {index}"
            )
        booked = when
        window_start, window_end = booking_window or (start, end)
        if not window_start <= booked <= window_end:
            raise ValueError("CAMT booking date lies outside the statement balance dates")
        details = all_(entry, "NtryDtls/TxDtls")
        refs = [value(t, "Refs/EndToEndId") for t in details]
        reference = (
            refs[0]
            if len(refs) == 1 and refs[0] not in {None, "NOTPROVIDED"}
            else value(entry, "AcctSvcrRef") or value(entry, "NtryRef") or ""
        )
        party = ""
        if len(details) == 1:
            side = "Dbtr" if direction == "CRDT" else "Cdtr"
            party = (
                value(details[0], "RltdPties/" + side + "/Nm")
                or value(details[0], "RltdPties/" + side + "/Pty/Nm")
                or ""
            )
        row = Transaction(
            id=f"{value(statement, 'Id')}:entry:{index}",
            account=account,
            reference=reference,
            date=booked,
            bank_booking_date=booked,
            bank_value_date=valued,
            bank_date_basis="BOOKING_DATE",
            currency=currency,
            amount=number(amt.text) * (1 if direction == "CRDT" else -1),
            counterparty=party,
        ).model_dump(mode="json")
        row.update(
            source_row=index,
            source_credit_debit_indicator=direction,
            is_reversal=reversal in {"true", "1"},
            detail_count=len(details),
        )
        rows.append(row)
    count = value(statement, "TxsSummry/TtlNtries/NbOfNtries")
    if count is not None and (not count.isdigit() or int(count) != len(rows)):
        raise ValueError("CAMT embedded entry-count control does not agree")
    if opening + sum((Decimal(r["amount"]) for r in rows), Decimal(0)) != closing:
        raise ValueError("CAMT opening plus booked entries does not agree to closing balance")
    return rows, {
        "statement_id": value(statement, "Id"),
        "account": account,
        "currency": currency,
        "opening": str(opening),
        "closing": str(closing),
        "from": start.isoformat(),
        "through": end.isoformat(),
        "file_statement_count": len(statements),
        "entry_grain": "BOOKED_ENTRY_ONCE_NOT_ENTRY_PLUS_DETAILS",
        "format_namespace": found[1],
        "bank_identity_verified": False,
    }


def mt940(content, data):
    from app.modules.country_workflows.mt940_pages import assemble

    return assemble(content, data, _mt940_page)


def _mt940_page(content, data, *, intermediate=False):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError(
            "MT940 must be UTF-8; select a verified encoding conversion before importing"
        ) from None
    # A single standard FIN envelope is accepted; the message body is parsed as tags.
    if text.startswith("{"):
        match = re.fullmatch(
            r"\{1:[^{}]*\}\{2:[^{}]*\}(?:\{3:.*?\})?\{4:\s*(.*?)\s*-\}(?:\{5:.*\})?\s*", text, re.S
        )
        if not match:
            raise ValueError("Unsupported MT940 FIN envelope")
        text = match[1]
    records = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r":(\d{2}[A-Z]?):(.*)", line)
        if match:
            records.append([match[1], match[2]])
        elif records and records[-1][0] in {"61", "86"} and len(records[-1][1]) + len(line) < 4000:
            records[-1][1] += "\n" + line
        else:
            raise ValueError("Unsupported MT940 line or field continuation")
    if len(records) > 15010 or any(len(value) > 4000 for tag, value in records):
        raise ValueError("MT940 field bound exceeded")
    allowed = {"20", "21", "25", "28C", "60F", "61", "86", "62F", "64", "65", "13D"}
    if intermediate:
        allowed |= {"60M", "62M"}
    if any(tag not in allowed for tag, value in records):
        raise ValueError("Partial or unsupported MT940 statement fields")

    def field(tag):
        return single([v.strip() for t, v in records if t == tag], "MT940 " + tag)

    statement = field("20")
    account = field("25")
    sequence = field("28C")
    if (
        not 1 <= len(statement) <= 16
        or not 1 <= len(account) <= 35
        or not re.fullmatch(r"\d{1,5}(?:/\d{1,5})?", sequence)
    ):
        raise ValueError("Invalid MT940 message reference, account or statement sequence format")
    if not intermediate and "/" in sequence and sequence.split("/")[-1].lstrip("0") != "1":
        raise ValueError("Multi-page MT940 statement requires page assembly")
    if data.account_identifier and data.account_identifier != account:
        raise ValueError("MT940 account differs from the explicitly selected account")
    if data.statement_identifier and data.statement_identifier != statement:
        raise ValueError("MT940 statement identifier differs from the selection")

    def short_date(value):
        try:
            return datetime.strptime(value, "%y%m%d").date()
        except ValueError:
            raise ValueError("Invalid MT940 YYMMDD date") from None

    def balance(value):
        m = re.fullmatch(r"([CD])(\d{6})([A-Z]{3})(\d{1,20}(?:,\d{1,8})?)", value)
        if not m:
            raise ValueError("Invalid MT940 balance field")
        return number(m[4], comma=True) * (1 if m[1] == "C" else -1), short_date(m[2]), m[3]

    opening_tag = single(
        [tag for tag, value in records if tag in {"60F", "60M"}], "MT940 opening balance"
    )
    closing_tag = single(
        [tag for tag, value in records if tag in {"62F", "62M"}], "MT940 closing balance"
    )
    opening, start, currency = balance(field(opening_tag))
    closing, end, closing_currency = balance(field(closing_tag))
    if currency != closing_currency or end < start:
        raise ValueError("MT940 balance currencies or dates are inconsistent")
    tags = [tag for tag, value in records]
    opening_index, closing_index = tags.index(opening_tag), tags.index(closing_tag)
    if (
        tags[0] != "20"
        or not tags.index("20")
        < tags.index("25")
        < tags.index("28C")
        < opening_index
        < closing_index
        or any(
            (tag == "61" and not opening_index < i < closing_index)
            or (tag == "86" and i < opening_index)
            or (tag in {"64", "65"} and i < closing_index)
            for i, tag in enumerate(tags)
        )
    ):
        raise ValueError("MT940 booking fields must lie between opening and closing balances")
    for optional in ("21", "64", "13D"):
        if tags.count(optional) > 1:
            raise ValueError("Duplicate MT940 optional header or balance field")
    if sum(tag == "86" and index > closing_index for index, tag in enumerate(tags)) > 1:
        raise ValueError("Duplicate MT940 closing statement information")
    if "21" in tags and len(field("21")) > 16:
        raise ValueError("Invalid MT940 related-reference width")
    if "13D" in tags:
        timestamp = field("13D")
        if (
            not re.fullmatch(r"\d{10}[+-]\d{4}", timestamp)
            or int(timestamp[-4:-2]) > 23
            or int(timestamp[-2:]) > 59
        ):
            raise ValueError("Invalid MT940 date/time indication")
        try:
            datetime.strptime(timestamp[:10], "%y%m%d%H%M")
        except ValueError:
            raise ValueError("Invalid MT940 date/time indication") from None
    if "21" in tags and not tags.index("20") < tags.index("21") < tags.index("25"):
        raise ValueError("Invalid MT940 related-reference placement")
    auxiliary = []
    for index, (tag, value) in enumerate(records):
        if tag in {"64", "65"}:
            if balance(value.strip())[2] != currency:
                raise ValueError("MT940 available balance currency differs from booked currency")
        if tag in {"21", "64", "65", "13D"} or (tag == "86" and index > closing_index):
            auxiliary.append(
                {
                    "tag": tag,
                    "value": value,
                    "source_message_field": index + 1,
                    "basis": "NOT_A_BOOKED_TRANSACTION",
                }
            )
            if len(auxiliary) > 100:
                raise ValueError("MT940 auxiliary field bound exceeded")
    rows: list[dict[str, Any]] = []
    for index, (tag, value) in enumerate(records):
        if tag == "86" and opening_index < index < closing_index:
            if not rows:
                raise ValueError("MT940 transaction information has no preceding statement line")
            information = rows[-1].setdefault("source_mt940_information", [])
            if sum(map(len, information)) + len(value) > 4000:
                raise ValueError("MT940 transaction information exceeds supported bound")
            information.append(value)
        if tag != "61":
            continue
        m = re.fullmatch(
            r"(\d{6})(\d{4})?(RC|RD|C|D)([A-Z])?(\d{1,20}(?:,\d{1,8})?)([A-Z][A-Z0-9]{3})([^\n]*)(?:\n.*)?",
            value,
            re.S,
        )
        if not m:
            raise ValueError("Unsupported MT940 transaction field")
        value_date = short_date(m[1])
        booked = value_date
        if m[2]:
            month, day = int(m[2][:2]), int(m[2][2:])
            year = value_date.year + (
                1 if month < value_date.month - 6 else -1 if month > value_date.month + 6 else 0
            )
            try:
                booked = date(year, month, day)
            except ValueError:
                raise ValueError("Invalid MT940 entry date") from None
        if not intermediate and not start <= booked <= end:
            raise ValueError("MT940 entry date lies outside the complete statement period")
        reference = m[7].split("//")[0].strip()
        if reference in {"NONREF", "NOTPROVIDED"}:
            reference = m[7].split("//", 1)[1].strip() if "//" in m[7] else ""
        row = Transaction(
            id=f"{statement}:entry:{len(rows) + 1}",
            account=account,
            reference=reference,
            date=booked,
            bank_booking_date=booked if m[2] else None,
            bank_value_date=value_date,
            bank_date_basis="ENTRY_DATE_INFERRED_YEAR" if m[2] else "VALUE_DATE_FALLBACK",
            currency=currency,
            amount=number(m[5], comma=True) * (1 if m[3] in {"C", "RD"} else -1),
            counterparty="",
        ).model_dump(mode="json")
        row.update(
            source_row=index + 1,
            is_reversal=m[3].startswith("R"),
            source_mt940_entry=value,
        )
        rows.append(row)
        if len(rows) > 5000:
            raise ValueError("Native bank source exceeds 5,000 entries")
    if opening + sum((Decimal(r["amount"]) for r in rows), Decimal(0)) != closing:
        raise ValueError("MT940 opening plus transactions does not agree to closing balance")
    return rows, {
        "statement_id": statement,
        "opening_tag": opening_tag,
        "closing_tag": closing_tag,
        "field_count": len(records),
        "auxiliary_fields": auxiliary,
        "statement_sequence": sequence,
        "account": account,
        "currency": currency,
        "opening": str(opening),
        "closing": str(closing),
        "from": start.isoformat(),
        "through": end.isoformat(),
        "bank_identity_verified": False,
    }


def wps(content, data, filename):
    try:
        records = list(csv.reader(io.StringIO(content.decode("utf-8-sig"), newline="")))
    except (UnicodeDecodeError, csv.Error):
        raise ValueError("Invalid WPS SIF encoding or CSV records") from None
    if not 1 <= len(records) <= 5001 or any(
        len(r) != 10 or any(len(v) > 4000 for v in r) for r in records
    ):
        raise ValueError("The supported WPS profile requires ten fields per EDR/SCR record")
    if records[-1][0] != "SCR" or any(r[0] != "EDR" for r in records[:-1]):
        raise ValueError(
            "The supported WPS profile requires EDR records followed by exactly one SCR trailer"
        )
    scr = [v.strip() for v in records[-1]]
    _, employer, routing, created, clock, month, count, total, currency, reference = scr
    if (
        not re.fullmatch(r"\d{1,13}", employer)
        or not re.fullmatch(r"\d{9}", routing)
        or currency != "AED"
    ):
        raise ValueError("Invalid WPS employer identifier, routing code or payment currency")
    if data.employer_registration and data.employer_registration != employer:
        raise ValueError("WPS employer differs from the selected registration")
    if (
        not re.fullmatch(r"\d{4}-\d{2}-\d{2}", created)
        or not re.fullmatch(r"\d{4}", clock)
        or not re.fullmatch(r"\d{6}", month)
        or len(reference) > 35
        or len(count) > 10
        or len(total) > 15
    ):
        raise ValueError("WPS SCR field widths or formats do not match the selected profile")
    try:
        creation = datetime.strptime(created + clock, "%Y-%m-%d%H%M")
        salary_month = datetime.strptime(month, "%m%Y").strftime("%Y-%m")
    except ValueError:
        raise ValueError("Invalid WPS creation timestamp or salary month") from None
    stem = Path(filename).stem
    expected_prefix = employer.zfill(13) + creation.strftime("%y%m%d%H%M")
    if (
        Path(filename).suffix.lower() != ".sif"
        or not re.fullmatch(r"\d{25}", stem)
        or stem[:23] != expected_prefix
        or int(stem[-2:]) > 59
    ):
        raise ValueError(
            "WPS SIF filename does not agree with the employer and SCR creation timestamp"
        )
    if not count.isdigit() or int(count) != len(records) - 1:
        raise ValueError("WPS SCR employee-count control does not agree")
    rows: list[dict[str, Any]] = []
    subjects = set()
    fixed_total = variable_total = Decimal(0)
    for index, record in enumerate(records[:-1], 1):
        _, employee, agent, account, start, end, days, fixed, variable, unpaid = [
            v.strip() for v in record
        ]
        if (
            not re.fullmatch("[A-Z0-9]{14}", employee)
            or employee in subjects
            or not re.fullmatch(r"\d{9}", agent)
        ):
            raise ValueError(
                f"Invalid or duplicated employee identifier or agent routing at WPS row {index}"
            )
        if not (re.fullmatch("[A-Z0-9]{16}", account) or re.fullmatch("AE[0-9]{21}", account)):
            raise ValueError(f"Invalid supported bank-account format at WPS row {index}")
        if account.startswith("AE"):
            rearranged = account[4:] + "1014" + account[2:4]
            if int(rearranged) % 97 != 1:
                raise ValueError(f"Invalid UAE IBAN checksum at WPS row {index}")
        first, last = iso_date(start), iso_date(end)
        if (
            not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start)
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end)
            or len(days) > 4
            or len(unpaid) > 4
            or len(fixed) > 15
            or len(variable) > 15
            or first > last
            or first.strftime("%Y-%m") != salary_month
            or last.strftime("%Y-%m") != salary_month
            or not days.isdigit()
            or int(days) != (last - first).days + 1
            or not unpaid.isdigit()
            or not 0 <= int(unpaid) <= int(days)
        ):
            raise ValueError(f"Invalid WPS wage dates, period days or unpaid leave at row {index}")
        f, v = number(fixed, places=2), number(variable, places=2)
        fixed_total += f
        variable_total += v
        subjects.add(employee)
        rows.append(
            {
                "id": f"wps:{index}",
                "registration": employer,
                "subject": employee,
                "period": salary_month,
                "component": "SALARY",
                "currency": "AED",
                "amount": str(f + v),
                "due_date": data.obligation_due_date.isoformat()
                if data.obligation_due_date
                else None,
                "payment_date": None,
                "fixed_income": str(f),
                "variable_income": str(v),
                "unpaid_days": int(unpaid),
                "employee_account_sha256": hashlib.sha256(account.encode()).hexdigest(),
                "source_row": index,
            }
        )
    if number(total, places=2) != fixed_total + variable_total:
        raise ValueError("WPS SCR total salary does not agree to fixed plus variable income")
    return rows, {
        "employer_registration": employer,
        "salary_month": salary_month,
        "employee_count": len(rows),
        "fixed_total": str(fixed_total),
        "variable_total": str(variable_total),
        "total_salary": str(fixed_total + variable_total),
        "file_created_at": creation.isoformat(),
        "payment_execution": "NOT_EVIDENCED_BY_INSTRUCTION_FILE",
        "due_date_basis": "DECLARED_NOT_LEGALLY_INFERRED",
        "employer_reference": reference,
    }


def parse_native(content, data, country, filename):
    if len(content) > MAX_BYTES or b"\x00" in content:
        raise ValueError("Native source is too large or contains invalid null bytes")
    profile = next(f for f in FORMATS if f["id"] == data.file_format)
    if profile["countries"] and country not in profile["countries"]:
        raise ValueError("Native source format is unavailable for this engagement country")
    if data.table_type != profile["table_type"]:
        raise ValueError("Native format does not produce the selected source table type")
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        try:
            if data.file_format == "camt053":
                rows, metadata = camt(content, data)
            elif data.file_format == "swift-mt940":
                rows, metadata = mt940(content, data)
            elif data.file_format == "india-inv01-json":
                from app.modules.country_workflows.india_invoice_source import parse_invoice_json

                rows, metadata = parse_invoice_json(content, data)
            elif data.file_format == "india-epfo-ecr":
                from app.modules.country_workflows.india_ecr_source import parse_ecr

                rows, metadata = parse_ecr(content, data)
            elif data.file_format == "india-epfo-arrear-ecr-v2":
                from app.modules.country_workflows.india_ecr_arrear_source import parse_arrears

                rows, metadata = parse_arrears(content, data)
            elif data.file_format == "india-gstr1-documents-json":
                from app.modules.country_workflows.india_gstr1_source import parse_gstr1

                rows, metadata = parse_gstr1(content, data)
            elif data.file_format == "india-gstr1-document-series-json":
                from app.modules.country_workflows.document_series import parse_series

                rows, metadata = parse_series(content, data)
            elif data.file_format == "india-gstr1-summary-json":
                from app.modules.country_workflows.gst_summary import parse_summary

                rows, metadata = parse_summary(content, data)
            elif data.file_format == "india-gstr2b-json":
                from app.modules.country_workflows.india_gstr2b_source import parse_gstr2b

                rows, metadata = parse_gstr2b(content, data)
            elif data.file_format == "uae-wps-sif-evp":
                from app.modules.country_workflows.wps_variable_pay import parse_wps_variable_pay

                rows, metadata = parse_wps_variable_pay(content, data, filename)
            else:
                rows, metadata = wps(content, data, filename)
        except ValidationError:
            raise ValueError(
                "Native source field validation failed; inspect the retained document"
            ) from None
        if len(rows) != data.expected_rows:
            raise ValueError("Native source row-count control does not agree")
        if len(rows) > 5000:
            raise ValueError("Native source exceeds 5,000 derived rows")
        totals: dict[str, Decimal] = {}
        for row in ([] if data.table_type in {"gst-summary-metrics", "gst-document-series"} else rows):
            totals[row["currency"]] = totals.get(row["currency"], Decimal(0)) + Decimal(
                row["tax"] if data.table_type == "tax-documents" else row["amount"]
            )
        if not rows:
            if not data.nil_reason or any(v != 0 for v in data.control_totals.values()):
                raise ValueError("A native nil source requires a rationale and zero controls")
            totals = {metadata.get("currency", "AED"): Decimal(0)}
        if totals != data.control_totals:
            raise ValueError("Native source currency control totals do not agree")
    return {
        "table_type": data.table_type,
        "rows": rows,
        "row_count": len(rows),
        "control_totals": {k: str(v) for k, v in sorted(totals.items())},
        "population_completeness": "RETAINED_DOCUMENT_SERIES_COUNTS_NOT_INVOICE_COMPLETENESS"
        if data.file_format == "india-gstr1-document-series-json"
        else "DECLARED_GSTR1_INVOICE_NOTE_SECTION_CONTROLS_NOT_COMPLETE_RETURN"
        if data.file_format == "india-gstr1-documents-json"
        else "RETAINED_GSTR1_SUMMARY_HIERARCHY_METRIC_CONTROLS"
        if data.file_format == "india-gstr1-summary-json"
        else "SELECTED_NATIVE_STATEMENT_CONTROLS"
        if data.table_type == "transactions"
        else "INV01_SELECTED_DOCUMENT_ITEM_CONTROLS"
        if data.file_format == "india-inv01-json"
        else "ECR_DECLARED_MEMBER_AND_COMPONENT_CONTROLS"
        if data.file_format == "india-epfo-ecr"
        else "ECR_ARREAR_DECLARED_MEMBER_WAGE_AND_CONTRIBUTION_CONTROLS"
        if data.file_format == "india-epfo-arrear-ecr-v2"
        else "GSTR2B_DECLARED_DOCUMENT_AND_COMPONENT_CONTROLS"
        if data.file_format == "india-gstr2b-json"
        else "WPS_INSTRUCTION_FILE_CONTROLS",
        "review_status": "UNVERIFIED",
        "nil_reason": data.nil_reason,
        "title": data.label,
        "parser_version": data.file_format
        + ("-3" if data.file_format in {"swift-mt940", "camt053"} else "-1"),
        "native_format": data.file_format,
        **({"allowed_source_roles": ["reported"], "document_series_controls": metadata["count_controls"]} if data.file_format == "india-gstr1-document-series-json" else {}),
        **({"allowed_source_roles": ["return"]} if data.file_format == "india-gstr1-documents-json" else {}),
        **({"allowed_source_roles": ["return"], "metric_controls": metadata["metric_controls"]} if data.file_format == "india-gstr1-summary-json" else {}),
        **({"allowed_source_roles": ["books", "invoices"]} if data.file_format == "india-inv01-json" else {}),
        **({"allowed_source_roles": ["return"]} if data.file_format == "india-gstr2b-json" else {}),
        **({"allowed_source_roles": ["return", "reported"]} if data.file_format == "india-epfo-arrear-ecr-v2" else {}),
        **({"allowed_source_roles": ["channel", "return", "reported"]} if data.file_format == "uae-wps-sif-evp" else {}),
        "native_metadata": metadata,
        "native_controls_verified": True,
        "statutory_calculation_qualified": False,
        "limitations": [
            "File structure and arithmetic validation do not verify account ownership, legal entitlement or payment execution"
        ],
    }
