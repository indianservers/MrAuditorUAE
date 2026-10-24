"""Query-only qbXML contracts for the local QuickBooks Desktop SDK agent."""

import hashlib
import json
import re
from collections import Counter
from datetime import date
from xml.etree.ElementTree import Element, SubElement, tostring

from defusedxml.ElementTree import fromstring

from app.modules.connectors.zoho import ConnectorError


def request(kind, start: date, end: date, version="13.0"):
    if not re.fullmatch(r"[0-9]{1,2}\.[0-9]", version) or start > end:
        raise ConnectorError("Invalid Desktop SDK version or period")
    root = Element("QBXML")
    messages = SubElement(root, "QBXMLMsgsRq", onError="stopOnError")
    if kind == "company":
        SubElement(messages, "CompanyQueryRq")
    elif kind == "accounts":
        node = SubElement(messages, "AccountQueryRq")
        SubElement(node, "ActiveStatus").text = "All"
    elif kind == "gl":
        node = SubElement(messages, "GeneralDetailReportQueryRq")
        SubElement(node, "GeneralDetailReportType").text = "GeneralLedger"
        period = SubElement(node, "ReportPeriod")
        SubElement(period, "FromReportDate").text = str(start)
        SubElement(period, "ToReportDate").text = str(end)
        SubElement(node, "ReportBasis").text = "Accrual"
        for column in ("TxnID", "TxnType", "Date", "Account", "Debit", "Credit", "Memo"):
            SubElement(node, "IncludeColumn").text = column
    else:
        raise ConnectorError("Desktop SDK permits only approved read queries")
    return '<?xml version="1.0"?><?qbxml version="' + version + '"?>' + tostring(root, encoding="unicode")


def response(raw):
    if len(raw) > 64 * 1024 * 1024:
        raise ConnectorError("Desktop SDK response exceeds window limit")
    root = fromstring(raw)
    replies = root.find("QBXMLMsgsRs")
    if replies is None or not list(replies):
        raise ConnectorError("Desktop SDK response envelope is missing")
    if any(n.get("statusSeverity") == "Error" or n.get("statusCode", "0") != "0" for n in replies):
        raise ConnectorError("Desktop SDK query failed or returned incomplete evidence")
    return root


def package_rows(package, options):
    if package.get("format") != "quickbooks-desktop-sdk/1":
        raise ConnectorError("Invalid Desktop SDK evidence package")
    company = response(package["company_xml"].encode()).find(".//CompanyRet")
    if company is None or company.findtext("CompanyName") != package.get("expected_company"):
        raise ConnectorError("Desktop SDK company identity mismatch")
    accounts = {}
    for node in response(package["accounts_xml"].encode()).findall(".//AccountRet"):
        code, name = node.findtext("ListID"), node.findtext("FullName")
        if not code or not name or name in accounts:
            raise ConnectorError("Desktop SDK chart identity is missing or ambiguous")
        accounts[name] = code
        if options.kind == "coa":
            yield {"account_code": code, "account_name": name, "source_id": code,
                   "source_group": node.findtext("AccountType") or ""}
    if options.kind == "coa":
        return
    if options.kind not in {"gl", "journals"}:
        raise ConnectorError("Desktop SDK trial-balance controls require an independently qualified source report")
    occurrences: Counter = Counter()
    for raw in package["ledger_xml"]:
        root = response(raw.encode())
        columns = {n.get("colID"): n.findtext("ColType") for n in root.findall(".//ColDesc")}
        if not {"TxnID", "Date", "Account", "Debit", "Credit"} <= set(columns.values()):
            raise ConnectorError("Unsupported Desktop SDK report column contract")
        for node in root.findall(".//DataRow"):
            values = {columns.get(n.get("colID")): n.get("value", "") for n in node.findall("ColData")}
            code = accounts.get(values.get("Account"))
            if not code or not values.get("TxnID") or not values.get("Date"):
                raise ConnectorError("Desktop SDK posting lacks an account, transaction identity or date")
            fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
            occurrences[fingerprint] += 1
            yield {"account_code": code, "account_name": values["Account"],
                "journal_ref": values["TxnID"], "posting_date": values["Date"],
                "debit": values.get("Debit") or "0", "credit": values.get("Credit") or "0",
                "description": values.get("Memo", ""), "source_transaction_id": values["TxnID"],
                "source_id": f"desktop-report:{fingerprint}:{occurrences[fingerprint]}",
                "source_identity_quality": "report_snapshot; native_posting_line_id_not_available"}
