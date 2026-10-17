"""Native Tally XML collection requests and fail-closed parsing; no remote port exposure."""

from datetime import date
from decimal import Decimal
from xml.etree.ElementTree import Element, SubElement, tostring

from defusedxml.ElementTree import fromstring

from app.modules.connectors.zoho import ConnectorError

VERSION = "tally-xml/2.0.0"


def export_request(company: str, kind: str, start: date, end: date) -> bytes:
    types = {"ledgers": "Ledger", "groups": "Group", "vouchers": "Voucher", "companies": "Company"}
    if kind not in types or start > end:
        raise ConnectorError("Invalid Tally export scope")
    root = Element("ENVELOPE")
    header = SubElement(root, "HEADER")
    for name, value in [
        ("VERSION", "1"),
        ("TALLYREQUEST", "Export"),
        ("TYPE", "Collection"),
        ("ID", "AuditOSCollection"),
    ]:
        SubElement(header, name).text = value
    desc = SubElement(SubElement(root, "BODY"), "DESC")
    variables = SubElement(desc, "STATICVARIABLES")
    for name, value in [
        ("SVCURRENTCOMPANY", company),
        ("SVFROMDATE", start.strftime("%Y%m%d")),
        ("SVTODATE", end.strftime("%Y%m%d")),
        ("SVEXPORTFORMAT", "$$SysName:XML"),
    ]:
        SubElement(variables, name).text = value
    tdl = SubElement(SubElement(desc, "TDL"), "TDLMESSAGE")
    collection = SubElement(tdl, "COLLECTION", NAME="AuditOSCollection", ISMODIFY="No")
    SubElement(collection, "TYPE").text = types[kind]
    SubElement(
        collection, "FETCH"
    ).text = "*,AllLedgerEntries.*,LedgerEntries.*,CategoryAllocations.*"
    if kind == "vouchers":
        SubElement(collection, "FILTER").text = "AuditOSDateFilter"
        SubElement(
            tdl, "SYSTEM", TYPE="Formulae", NAME="AuditOSDateFilter"
        ).text = "$Date >= ##SVFromDate AND $Date <= ##SVToDate"
    return tostring(root, encoding="utf-8", xml_declaration=True)


def parse_export(content: bytes, company: str, start: date, end: date) -> dict:
    if len(content) > 64 * 1024 * 1024:
        raise ConnectorError("Tally XML too large")
    try:
        root = fromstring(content)
    except Exception as exc:
        raise ConnectorError("Invalid or unsafe Tally XML") from exc
    if root.findtext(".//STATUS") == "0" or root.find(".//LINEERROR") is not None:
        raise ConnectorError("Tally export reported failure")
    observed = root.findtext(".//SVCURRENTCOMPANY") or root.findtext(".//COMPANYNAME")
    if observed and observed != company:
        raise ConnectorError("Tally company mismatch")
    masters = {}
    for node in root.findall(".//LEDGER"):
        name = node.get("NAME") or node.findtext("NAME")
        if name:
            masters[name] = {
                "name": name,
                "group": node.findtext("PARENT"),
                "opening_balance": node.findtext("OPENINGBALANCE"),
            }
    groups = {
        n.get("NAME") or n.findtext("NAME"): n.findtext("PARENT") for n in root.findall(".//GROUP")
    }
    vouchers = []
    seen = set()
    warnings = []
    for voucher in root.findall(".//VOUCHER"):
        identifier = (
            voucher.findtext("GUID") or voucher.get("REMOTEID") or voucher.findtext("MASTERID")
        )
        if not identifier or identifier in seen:
            raise ConnectorError("Missing or duplicate Tally voucher identifier")
        seen.add(identifier)
        raw_date = voucher.findtext("DATE") or ""
        try:
            posting = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
        except ValueError as exc:
            raise ConnectorError("Invalid Tally voucher date") from exc
        if not start <= posting <= end:
            raise ConnectorError("Tally voucher outside requested financial period")
        nodes = voucher.findall("ALLLEDGERENTRIES.LIST") or voucher.findall("LEDGERENTRIES.LIST")
        lines = []
        if not nodes:
            raise ConnectorError("Voucher has no accounting lines")
        for index, node in enumerate(nodes, 1):
            name = node.findtext("LEDGERNAME") or ""
            if not name:
                raise ConnectorError("Missing Tally ledger name")
            if name not in masters:
                warnings.append({"rule": "missing_ledger_master", "account": name})
            try:
                amount = Decimal(node.findtext("AMOUNT") or "")
            except Exception as exc:
                raise ConnectorError(
                    "Unsupported Tally currency amount; supply explicit functional report"
                ) from exc
            if not amount.is_finite():
                raise ConnectorError("Invalid Tally amount")
            # Native Tally accounting amount is negative for debit, positive for credit.
            debit, credit = max(-amount, Decimal(0)), max(amount, Decimal(0))
            deemed = node.findtext("ISDEEMEDPOSITIVE")
            if deemed in {"Yes", "No"} and amount and ((deemed == "Yes") != (amount < 0)):
                raise ConnectorError("Tally debit/credit sign conflict")
            centers = [
                {"name": n.findtext("NAME"), "amount": n.findtext("AMOUNT")}
                for n in node.findall(".//COSTCENTREALLOCATIONS.LIST")
            ]
            lines.append(
                {
                    "source_id": identifier + ":" + str(index),
                    "account_code": name,
                    "account_name": name,
                    "journal_ref": identifier,
                    "posting_date": posting.isoformat(),
                    "debit": str(debit),
                    "credit": str(credit),
                    "description": voucher.findtext("NARRATION") or "",
                    "cost_center": str(centers) if centers else "",
                    "source_group": masters.get(name, {}).get("group") or "",
                }
            )
        difference = sum(
            (Decimal(line["debit"]) - Decimal(line["credit"]) for line in lines), Decimal(0)
        )
        if difference:
            warnings.append(
                {"rule": "unbalanced_voucher", "voucher": identifier, "difference": str(difference)}
            )
        vouchers.extend(lines)
    return {
        "company": company,
        "company_verified_in_export": observed is not None,
        "masters": masters,
        "groups": groups,
        "lines": vouchers,
        "warnings": warnings,
        "completeness": "requires_source_controls",
        "connector_version": VERSION,
    }
