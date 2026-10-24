"""Strict normalization of Zoho's documented per-account transaction feed.

Account feeds include system-generated postings, unlike the manual-journals API.
They are still subject to independent GL/TB reconciliation and live qualification.
"""

from datetime import date

from app.modules.connectors.zoho import ConnectorError
from app.modules.ingestion.parser import money


def zoho_ledger_row(item: dict, account: dict, start: date, end: date) -> dict:
    account_id = str(account["account_id"])
    if str(item.get("account_id", "")) != account_id:
        raise ConnectorError("Zoho transaction account mismatch")
    transaction_id = str(item.get("transaction_id", ""))
    transaction_type = item.get("transaction_type", "")
    posting = date.fromisoformat(item["transaction_date"])
    if not transaction_id.isdigit() or not transaction_type or not start <= posting <= end:
        raise ConnectorError("Invalid Zoho transaction identity or period")
    # Both sides are supplied by the source. Do not create a balancing offset.
    if "debit_amount" not in item or "credit_amount" not in item:
        raise ConnectorError("Zoho transaction is missing debit/credit amounts")
    debit, credit = money(str(item["debit_amount"])), money(str(item["credit_amount"]))
    if debit < 0 or credit < 0 or (debit and credit):
        raise ConnectorError("Invalid Zoho debit/credit amounts")
    side = item.get("debit_or_credit")
    if (
        side not in {"debit", "credit"}
        or (debit and side != "debit")
        or (credit and side != "credit")
    ):
        raise ConnectorError("Zoho transaction side conflicts with amounts")
    native_id = item.get("categorized_transaction_id") or item.get("line_id")
    if not native_id:
        raise ConnectorError("Zoho transaction has no stable posting identifier")
    currency = item.get("currency_code") or account.get("currency_code", "")
    if not currency:
        raise ConnectorError("Zoho transaction currency is missing")
    return {
        "account_code": account_id,
        "account_name": account["account_name"],
        "journal_ref": f"{transaction_type}:{transaction_id}",
        "posting_date": posting.isoformat(),
        "debit": str(debit),
        "credit": str(credit),
        "base_debit": str(item.get("bcy_debit_amount", "")),
        "base_credit": str(item.get("bcy_credit_amount", "")),
        "currency": currency,
        "exchange_rate": str(item.get("exchange_rate", "")),
        "source_id": f"{account_id}:{transaction_type}:{transaction_id}:{native_id}",
        "counterparty": item.get("customer_id") or item.get("payee", ""),
        "description": item.get("description", ""),
        "tax_code": item.get("tax_id", ""),
        "project": item.get("project_id", ""),
        "manual": "true" if transaction_type == "journal" else "false",
        "opening": "true" if transaction_type == "opening_balance" else "false",
    }
