"""Native Tally XML collection requests and fail-closed parsing; no remote port exposure."""

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from xml.etree.ElementTree import Element, SubElement, tostring

from defusedxml.ElementTree import fromstring

from app.modules.connectors.zoho import ConnectorError

VERSION = "tally-xml/3.0.0"


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
    if kind == "companies":
        SubElement(collection, "FILTER").text = "AuditOSCompanyFilter"
        SubElement(tdl, "SYSTEM", TYPE="Formulae", NAME="AuditOSCompanyFilter").text = "$Name = ##SVCurrentCompany"
    if kind == "vouchers":
        SubElement(collection, "FILTER").text = "AuditOSDateFilter"
        SubElement(
            tdl, "SYSTEM", TYPE="Formulae", NAME="AuditOSDateFilter"
        ).text = "$Date >= ##SVFromDate AND $Date <= ##SVToDate"
    return tostring(root, encoding="utf-8", xml_declaration=True)


def parse_export(content: bytes, company: str, start: date, end: date, *, master_catalog=None, expected_fingerprint=None) -> dict:
    if len(content) > 64 * 1024 * 1024:
        raise ConnectorError("Tally XML too large")
    try:
        root = fromstring(content)
    except Exception as exc:
        raise ConnectorError("Invalid or unsafe Tally XML") from exc
    if root.findtext(".//STATUS") == "0" or root.find(".//LINEERROR") is not None:
        raise ConnectorError("Tally export reported failure")
    observed_names = {
        node.text.strip()
        for tag in ("SVCURRENTCOMPANY", "COMPANYNAME")
        for node in root.findall(".//" + tag)
        if node.text and node.text.strip()
    }
    if observed_names and observed_names != {company}:
        raise ConnectorError("Tally company mismatch")
    identities = []
    for node in root.findall(".//COMPANY"):
        name = node.get("NAME") or node.findtext("NAME")
        if name != company:
            continue
        identities.append({"name": name, **{tag.lower(): node.findtext(tag) or "" for tag in
            ("GUID", "GSTREGISTRATIONNUMBER", "INCOMETAXNUMBER", "BOOKSFROM", "STARTINGFROM")}})
    if len(identities) > 1:
        raise ConnectorError("Ambiguous Tally company fingerprint")
    identity = identities[0] if identities else None
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest() if identity and identity["guid"] else None
    if expected_fingerprint and fingerprint != expected_fingerprint:
        raise ConnectorError("Tally company fingerprint changed or cannot be verified; review restore/company selection")
    masters = dict(master_catalog or {})
    for node in root.findall(".//LEDGER"):
        name = node.get("NAME") or node.findtext("NAME")
        if name:
            if name in masters:
                raise ConnectorError("Duplicate Tally ledger master")
            masters[name] = {
                "name": name,
                "group": node.findtext("PARENT"),
                "opening_balance": node.findtext("OPENINGBALANCE"),
                "closing_balance": node.findtext("CLOSINGBALANCE"),
            }
    groups = {
        n.get("NAME") or n.findtext("NAME"): n.findtext("PARENT") for n in root.findall(".//GROUP")
    }
    vouchers = []
    seen = set()
    warnings = []
    excluded_vouchers = 0
    voucher_revisions = []
    for voucher in root.findall(".//VOUCHER"):
        source_identifier = voucher.findtext("GUID") or voucher.get("REMOTEID") or voucher.findtext("MASTERID")
        source_status = next((tag for tag in ("ISCANCELLED", "ISOPTIONAL", "ISDELETED")
            if (voucher.findtext(tag) or "").strip().lower() == "yes"), "POSTED")
        voucher_revisions.append({"guid": source_identifier, "alter_id": voucher.findtext("ALTERID"),
            "status": source_status, "sha256": hashlib.sha256(tostring(voucher)).hexdigest()})
        # These vouchers do not form part of the posted accounting population.
        if any(
            (voucher.findtext(tag) or "").strip().lower() == "yes"
            for tag in ("ISCANCELLED", "ISOPTIONAL", "ISDELETED")
        ):
            excluded_vouchers += 1
            continue
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
                    "voucher_guid": identifier, "alter_id": voucher.findtext("ALTERID") or "",
                    "bill_allocations": json.dumps([{child.tag: child.text or "" for child in allocation}
                        for allocation in node.findall("BILLALLOCATIONS.LIST")], sort_keys=True),
                    "cost_center_allocations": json.dumps(centers, sort_keys=True),
                    "inventory_allocations": json.dumps([{child.tag: child.text or "" for child in allocation
                        if not list(child)} for allocation in node.findall("INVENTORYALLOCATIONS.LIST")], sort_keys=True),
                    "account_code": name,
                    "account_name": name,
                    "journal_ref": identifier,
                    "voucher_number": voucher.findtext("VOUCHERNUMBER") or "",
                    "voucher_type": voucher.get("VCHTYPE")
                    or voucher.findtext("VOUCHERTYPENAME")
                    or "",
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
        "company_identity": identity,
        "company_fingerprint": fingerprint,
        "voucher_revisions": voucher_revisions,
        "allocation_policy": "supplementary_evidence; accounting_lines_only_in_gl",
        "company_verified_in_export": bool(observed_names),
        "masters": masters,
        "groups": groups,
        "lines": vouchers,
        "warnings": warnings,
        "excluded_nonposting_vouchers": excluded_vouchers,
        "completeness": "requires_source_controls",
        "connector_version": VERSION,
    }


def trial_balance_rows(result: dict) -> list[dict]:
    """Source-reported balances with movements from posted voucher allocations.

    Reject absent balances and date-context inconsistencies. Never substitute
    a calculated closing balance for a missing native closing balance.
    """
    movements: dict[str, list[Decimal]] = {}
    for line in result["lines"]:
        debit, credit = movements.setdefault(line["account_code"], [Decimal(0), Decimal(0)])
        movements[line["account_code"]] = [
            debit + Decimal(line["debit"]),
            credit + Decimal(line["credit"]),
        ]
    if set(movements) - result["masters"].keys():
        raise ConnectorError("Tally trial balance requires every ledger master")
    rows = []
    for name, master in result["masters"].items():
        values = []
        for key in ("opening_balance", "closing_balance"):
            try:
                native = Decimal(master[key])
            except Exception as exc:
                raise ConnectorError(
                    "Tally TB requires native opening and closing balances"
                ) from exc
            if not native.is_finite():
                raise ConnectorError("Invalid Tally trial-balance amount")
            values.append(-native)  # Native debit-negative -> canonical debit-positive.
        opening, closing = values
        debit, credit = movements.get(name, [Decimal(0), Decimal(0)])
        if opening + debit - credit != closing:
            raise ConnectorError(
                "Tally balance period does not roll forward; import a period-specific TB report"
            )
        rows.append(
            {
                "account_code": name,
                "account_name": name,
                "source_id": "ledger:" + name,
                "opening_balance": str(opening),
                "closing_balance": str(closing),
                "debit": str(debit),
                "credit": str(credit),
                "source_group": master.get("group") or "",
            }
        )
    return rows


def date_windows(start, end, days=31):
    if start > end or not 1 <= days <= 366:
        raise ConnectorError("Invalid Tally extraction window")
    while start <= end:
        stop = min(end, start + timedelta(days=days - 1))
        yield start, stop
        if stop == end:
            return
        start = stop + timedelta(days=1)
