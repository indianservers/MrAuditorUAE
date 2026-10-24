"""Read QuickBooks Desktop via its local COM SDK; no listening network service."""

import argparse
import getpass
import json
import sys
from datetime import date
from pathlib import Path

import keyring

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.modules.accounting.schemas import ImportOptions
from app.modules.connectors.quickbooks_desktop import package_rows, request, response
from app.modules.connectors.tally import date_windows


def extract(config):
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    processor = None
    ticket = None
    try:
        processor = win32com.client.Dispatch("QBXMLRP2.RequestProcessor")
        processor.OpenConnection2("", "AuditOS accounting reader", 1)
        # Pin the explicitly selected file. Never attach to whichever file happens
        # to be open on the machine.
        company_file = str(Path(config["company_file"]).resolve(strict=True))
        ticket = processor.BeginSession(company_file, 2)
        version = config.get("qbxml_version", "13.0")
        if version not in list(processor.QBXMLVersionsForSession(ticket)):
            raise ValueError("Configured qbXML version is not supported by this installation")
        first, last = date.fromisoformat(config["start_date"]), date.fromisoformat(config["end_date"])
        def query(kind, start=first, end=last):
            raw = processor.ProcessRequest(ticket, request(kind, start, end, version))
            response(raw.encode())
            return raw
        package = {"format": "quickbooks-desktop-sdk/1", "expected_company": config["company"],
            "start_date": str(first), "end_date": str(last), "company_xml": query("company"),
            "accounts_xml": query("accounts"), "ledger_xml": [], "complete_general_ledger": False,
            "currency_verification": "independent_source_control_required"}
        for start, end in date_windows(first, last, config.get("window_days", 31)):
            package["ledger_xml"].append(query("gl", start, end))
        return package
    finally:
        try:
            if processor is not None and ticket is not None:
                processor.EndSession(ticket)
        finally:
            if processor is not None:
                processor.CloseConnection()
            pythoncom.CoUninitialize()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--set-refresh-token", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.set_refresh_token:
        identity = config["server_url"].rstrip("/") + ":" + config["tenant_id"]
        keyring.set_password("AuditOS-QuickBooks-Desktop", identity, getpass.getpass("AuditOS refresh token: "))
        return
    if not args.output:
        raise SystemExit("Choose a new --output evidence file")
    package = extract(config)
    options = ImportOptions(**{key: config[key] for key in ("client_id", "entity_id", "period_id")},
        source_system="quickbooks", currency=config["currency"])
    # Fail before writing an importable package if the deployed report differs.
    count = sum(1 for _ in package_rows(package, options))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(package, stream)
    if args.upload:
        from upload_package import upload_package

        print(json.dumps({"imports": upload_package(config, args.output, ["coa", "gl"], "quickbooks", "AuditOS-QuickBooks-Desktop")}))
    print(json.dumps({"status": "extracted_pending_review", "rows": count, "package": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
