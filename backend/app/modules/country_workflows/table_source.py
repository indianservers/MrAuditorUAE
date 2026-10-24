"""Reuse reviewed bank/open-item tables without changing their original evidence."""

import csv
import io
from decimal import Decimal

from app.modules.country_workflows.sources import parse_csv


def from_supporting_table(body, data):
    open_items = data.table_type == "audit-open-items"
    if (
        body.get("table_kind") != ("open-items" if open_items else "bank")
        or body.get("review_status") != "REVIEWED"
    ):
        raise ValueError("Select an independently reviewed supporting table of the required kind")
    if str(body.get("evidence_version_id")) != str(data.evidence_version_id):
        raise ValueError("Supporting table and original evidence version differ")
    if not body.get("rows") or len(body["rows"]) > 5000:
        raise ValueError(
            "Supporting population must contain one to 5,000 rows; no truncation is allowed"
        )
    if body.get("row_count") != len(body["rows"]):
        raise ValueError("Supporting table population receipt differs from its complete row set")
    rows = []
    for row in body["rows"]:
        if row.get("account_code") and row["account_code"] != data.account_identifier:
            raise ValueError(
                "Supporting table contains an account outside the explicitly selected scope"
            )
        if open_items:
            if row.get("document_type") not in {"invoice", "credit-note", "debit-note"}:
                raise ValueError(
                    "Open-item bridge requires explicit invoice/credit-note/debit-note classification"
                )
            balance_date = data.supporting_balance_date.isoformat()
            if row.get("balance_date") and row["balance_date"] != balance_date:
                raise ValueError("Supporting item balance date differs from the selected scope")
            amount = Decimal(str(row["open_amount"]))
            if data.supporting_amount_sign == "reverse-sign":
                amount = amount.copy_negate()
            rows.append(
                {
                    "id": row["id"],
                    "account": data.account_identifier,
                    "counterparty": row.get("counterparty"),
                    "reference": row.get("reference"),
                    "side": data.supporting_side,
                    "currency": row["currency"],
                    "document_date": row.get("document_date"),
                    "due_date": row.get("due_date"),
                    "balance_date": balance_date,
                    "amount": str(amount),
                    "document_type": row["document_type"],
                    "segment": row.get("segment", ""),
                }
            )
        else:
            rows.append(
                {
                    "id": row["id"],
                    "account": data.account_identifier,
                    "date": row.get("date"),
                    "reference": row.get("reference") or "",
                    "currency": row["currency"],
                    "amount": row["amount"],
                    "counterparty": row.get("counterparty") or "",
                }
            )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    result = parse_csv(buffer.getvalue().encode(), data)
    result.pop("csv_mapping", None)  # These are normalized event fields, not original CSV headings.
    for output, original in zip(result["rows"], body["rows"], strict=True):
        output["supporting_source_row"] = original.get("source_row")
        if original.get("source_worksheet"):
            output["supporting_source_worksheet"] = original["source_worksheet"]
        if open_items:
            output["supporting_reported_open_amount"] = original["open_amount"]
            output["supporting_original_balance_date"] = original.get("balance_date")
            output["supporting_balance_date_basis"] = (
                "SOURCE_FIELD" if original.get("balance_date") else "DECLARED_SCOPE"
            )
    return {
        **result,
        "parser_version": "reviewed-supporting-table-bridge-2",
        "supporting_table_id": str(data.supporting_table_id),
        "supporting_table_metadata": body.get("table_metadata"),
        "supporting_scope_assessment": data.supporting_scope_assessment.strip(),
        "population_completeness": "REVIEWED_SUPPORTING_TABLE_WITH_INDEPENDENT_CONTROLS",
        "supporting_table_basis": "REVIEWED_OPEN_ITEMS_WITH_DECLARED_SCOPE_AND_SIGN"
        if open_items
        else "PREVIOUSLY_NORMALIZED_BANK_ROWS_NO_NEW_VALUE_INFERENCE",
        "supporting_side": data.supporting_side,
        "supporting_balance_date": data.supporting_balance_date.isoformat()
        if data.supporting_balance_date
        else None,
        "supporting_amount_sign": data.supporting_amount_sign,
        "account_identity_verified": False,
    }
