"""CGI single-file CAMT statement pages; never infer missing pages or bank identity.

Reference: SWIFT CGI-MP camt.05x v1.6 (August 2025), pages 49–55.
The first page's transaction summary controls the complete statement, not that page.
Separate physical XML files and message-level pagination require a retained assembly
workflow and remain unsupported here.
"""

import re
from copy import deepcopy
from datetime import date
from decimal import Decimal
from typing import Any
from xml.etree import ElementTree as xml

from defusedxml import ElementTree as safe_xml


def assemble(content, data, read_page):
    from app.modules.country_workflows.native_sources import CAMT_VERSIONS, iso_date, number

    try:
        root = safe_xml.fromstring(
            content, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except Exception:
        raise ValueError("Invalid or unsafe CAMT XML") from None
    match = re.fullmatch(
        r"\{(urn:iso:std:iso:20022:tech:xsd:camt\.053\.001\.(\d{2}))\}Document", root.tag
    )
    if not match or match[2] not in CAMT_VERSIONS:
        raise ValueError("Unsupported CAMT.053 namespace version")
    namespace = match[1]

    def nodes(element, path):
        return element.findall("/".join("{" + namespace + "}" + p for p in path.split("/")))

    def node(element, path):
        found = nodes(element, path)
        if len(found) > 1:
            raise ValueError("Duplicate CAMT control field: " + path)
        return found[0] if found else None

    def value(element, path):
        found = node(element, path)
        return found.text.strip() if found is not None and found.text else None

    def account(statement):
        iban = value(statement, "Acct/Id/IBAN")
        other = value(statement, "Acct/Id/Othr/Id")
        if iban and other:
            raise ValueError("Competing CAMT account identifiers")
        return iban or other

    container = node(root, "BkToCstmrStmt")
    if container is None:
        raise ValueError("Missing CAMT statement container")

    def document(statement):
        page_root = xml.Element(root.tag)
        page_container = xml.SubElement(page_root, container.tag)
        page_container.append(statement)
        return xml.tostring(page_root)

    # A message-level split cannot be certified from a single retained file.
    for pagination in nodes(root, "BkToCstmrStmt/GrpHdr/MsgPgntn"):
        if value(pagination, "PgNb") != "1" or value(pagination, "LastPgInd") not in {"true", "1"}:
            raise ValueError("Paged CAMT files require complete-page assembly before import")
    statements = nodes(root, "BkToCstmrStmt/Stmt")
    if not statements or len(statements) > 100:
        raise ValueError("CAMT statement selection is missing or exceeds the file bound")
    if any(not value(statement, "Id") for statement in statements):
        raise ValueError("Missing CAMT statement identifier")
    selected = [
        (index, statement)
        for index, statement in enumerate(statements, 1)
        if (not data.statement_identifier or value(statement, "Id") == data.statement_identifier)
        and (not data.account_identifier or account(statement) == data.account_identifier)
    ]
    identities = {(value(statement, "Id"), account(statement)) for _, statement in selected}
    if not selected or len(identities) != 1:
        raise ValueError("Exactly one unambiguous CAMT statement selection is required")
    if len(selected) == 1:
        pagination = node(selected[0][1], "StmtPgntn")
        if pagination is None or (
            value(pagination, "PgNb") == "1" and value(pagination, "LastPgInd") in {"true", "1"}
        ):
            single_rows, metadata = read_page(document(deepcopy(selected[0][1])), data)
            metadata["file_statement_count"] = len(statements)
            return single_rows, metadata

    pages = [statement for _, statement in selected]
    statement_id, selected_account = next(iter(identities))
    currency = value(pages[0], "Acct/Ccy")
    sequence = value(pages[0], "ElctrncSeqNb")
    legal_sequence = value(pages[0], "LglSeqNb")
    if not sequence or not re.fullmatch(r"[0-9]{1,18}", sequence):
        raise ValueError("Paginated CAMT requires an explicit electronic statement sequence")
    if (
        any(len(nodes(page, "Ntry")) > 5000 for page in pages)
        or sum(len(nodes(page, "Ntry")) for page in pages) > 5000
    ):
        raise ValueError("Native bank source exceeds 5,000 entries")
    if any(
        value(page, "Acct/Ccy") != currency
        or value(page, "ElctrncSeqNb") != sequence
        or value(page, "LglSeqNb") != legal_sequence
        for page in pages
    ):
        raise ValueError("CAMT pages mix statement sequences, accounts or currencies")

    def balance(page, code, interim):
        balances = [b for b in nodes(page, "Bal") if value(b, "Tp/CdOrPrtry/Cd") == code]
        if len(balances) != 1:
            raise ValueError("Exactly one " + code + " balance is required per CAMT page")
        balance_node = balances[0]
        subtype = node(balance_node, "Tp/SubTp")
        if (subtype is not None) != interim or (
            interim and (value(subtype, "Cd") != "INTM" or node(subtype, "Prtry") is not None)
        ):
            raise ValueError("CAMT page balance must use the expected INTM subtype")
        amount = node(balance_node, "Amt")
        direction = value(balance_node, "CdtDbtInd")
        when = value(balance_node, "Dt/Dt") or value(balance_node, "Dt/DtTm")
        if (
            amount is None
            or amount.attrib.get("Ccy") != currency
            or direction not in {"CRDT", "DBIT"}
            or not when
        ):
            raise ValueError("Invalid CAMT page balance amount, currency, direction or date")
        return number(amount.text) * (1 if direction == "CRDT" else -1), iso_date(when)

    bounds: list[tuple[tuple[Decimal, date], tuple[Decimal, date]]] = []
    for index, page in enumerate(pages, 1):
        pagination = node(page, "StmtPgntn")
        if pagination is None or value(pagination, "PgNb") != str(index):
            raise ValueError("CAMT pages must be contiguous and ordered from page 1")
        last = value(pagination, "LastPgInd")
        if last not in ({"true", "1"} if index == len(pages) else {"false", "0"}):
            raise ValueError("CAMT page chain is incomplete or has an early last-page marker")
        opening = balance(page, "OPBD", index > 1)
        closing = balance(page, "CLBD", index < len(pages))
        if closing[1] < opening[1]:
            raise ValueError("CAMT page balance dates are reversed")
        if bounds and opening != bounds[-1][1]:
            raise ValueError(
                "CAMT page opening does not carry forward the prior closing amount/date"
            )
        if index > 1 and node(page, "TxsSummry") is not None:
            raise ValueError(
                "CAMT whole-statement transaction summary belongs only on the first page"
            )
        bounds.append((opening, closing))

    rows: list[dict[str, Any]] = []
    controls = []
    for index, ((position, original), (opening, closing)) in enumerate(
        zip(selected, bounds, strict=True), 1
    ):
        page = deepcopy(original)
        for path in ("StmtPgntn", "TxsSummry"):
            removable = node(page, path)
            if removable is not None:
                page.remove(removable)
        page_rows, _ = read_page(
            document(page),
            data,
            booking_window=(bounds[0][0][1], bounds[-1][1][1]),
            allow_interim=True,
        )
        for row in page_rows:
            row.update(
                id=f"{statement_id}:page:{index}:entry:{row['source_row']}",
                source_statement_position=position,
                source_statement_page=index,
                source_page_row=row["source_row"],
                source_row=len(rows) + 1,
            )
            rows.append(row)
        controls.append(
            {
                "page_number": index,
                "last_page": index == len(pages),
                "source_statement_position": position,
                "statement_id": statement_id,
                "electronic_sequence": sequence,
                "legal_sequence": legal_sequence,
                "account": selected_account,
                "currency": currency,
                "opening": str(opening[0]),
                "opening_date": opening[1].isoformat(),
                "opening_subtype": "INTM" if index > 1 else None,
                "closing": str(closing[0]),
                "closing_date": closing[1].isoformat(),
                "closing_subtype": "INTM" if index < len(pages) else None,
                "entry_count": len(page_rows),
                "entry_total": str(sum((Decimal(row["amount"]) for row in page_rows), Decimal(0))),
            }
        )
    summary = node(pages[0], "TxsSummry")
    if summary is None:
        raise ValueError("Paginated CAMT requires first-page whole-statement transaction controls")
    validate_summary(summary, rows, node, value, number)
    opening, start = bounds[0][0]
    closing, end = bounds[-1][1]
    if opening + sum((Decimal(row["amount"]) for row in rows), Decimal(0)) != closing:
        raise ValueError(
            "CAMT whole-statement opening plus entries does not agree to closing balance"
        )
    return rows, {
        "statement_id": statement_id,
        "electronic_sequence": sequence,
        "legal_sequence": legal_sequence,
        "account": selected_account,
        "currency": currency,
        "opening": str(opening),
        "closing": str(closing),
        "from": start.isoformat(),
        "through": end.isoformat(),
        "file_statement_count": len(statements),
        "page_count": len(pages),
        "page_controls": controls,
        "pagination_profile": "CGI_SINGLE_FILE_STATEMENT_PAGES",
        "entry_grain": "BOOKED_ENTRY_ONCE_NOT_ENTRY_PLUS_DETAILS",
        "format_namespace": namespace,
        "bank_identity_verified": False,
        "summary_scope": "WHOLE_STATEMENT_FIRST_PAGE",
        "summary_controls": {
            group.tag.rsplit("}", 1)[-1]: {
                child.tag.rsplit("}", 1)[-1]: child.text.strip() if child.text else None
                for child in group
            }
            for group in summary
        },
    }


def validate_summary(summary, rows, node, value, number):
    """Verify every reported count/amount; unknown summary groups fail closed."""
    allowed = {"TtlNtries", "TtlCdtNtries", "TtlDbtNtries"}
    if any(child.tag.rsplit("}", 1)[-1] not in allowed for child in summary):
        raise ValueError("Unsupported CAMT transaction-summary group")
    all_amounts = [Decimal(row["amount"]) for row in rows]
    count = value(summary, "TtlNtries/NbOfNtries")
    if count is None:
        raise ValueError("CAMT whole-statement entry-count control is required")
    for group, amounts in (
        ("TtlNtries", all_amounts),
        (
            "TtlCdtNtries",
            [
                Decimal(row["amount"])
                for row in rows
                if row["source_credit_debit_indicator"] == "CRDT"
            ],
        ),
        (
            "TtlDbtNtries",
            [
                Decimal(row["amount"])
                for row in rows
                if row["source_credit_debit_indicator"] == "DBIT"
            ],
        ),
    ):
        current = node(summary, group)
        if current is None:
            continue
        if any(
            child.tag.rsplit("}", 1)[-1] not in {"NbOfNtries", "Sum", "TtlNetNtryAmt", "CdtDbtInd"}
            for child in current
        ):
            raise ValueError("Unsupported CAMT transaction-summary control")
        declared_count = value(current, "NbOfNtries")
        if declared_count is not None and (
            not re.fullmatch(r"[0-9]{1,8}", declared_count) or int(declared_count) != len(amounts)
        ):
            raise ValueError("CAMT whole-statement entry-count control does not agree")
        gross = value(current, "Sum")
        if gross is not None and number(gross) != sum(
            (abs(amount) for amount in amounts), Decimal(0)
        ):
            raise ValueError("CAMT whole-statement gross amount control does not agree")
        net = value(current, "TtlNetNtryAmt")
        direction = value(current, "CdtDbtInd")
        if (net is None) != (direction is None):
            raise ValueError("CAMT net summary amount requires its credit/debit direction")
        if net is not None and (
            direction not in {"CRDT", "DBIT"}
            or number(net) * (1 if direction == "CRDT" else -1) != sum(amounts, Decimal(0))
        ):
            raise ValueError("CAMT whole-statement net amount control does not agree")
