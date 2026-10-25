"""Selected reviewed BRS book exceptions, preserving original transaction lineage."""

from decimal import Decimal, localcontext

from pydantic import Field, field_validator

from app.modules.country_workflows.operations_schemas import BankOutstanding
from app.modules.country_workflows.schemas import Money
from app.modules.jurisdictions.profiles import Strict


class BankOutstandingSourceInput(Strict):
    exception_ids: list[str] = Field(min_length=1, max_length=5000)
    expected_rows: int = Field(ge=1, le=5000)
    signed_total: Money
    label: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("assessment")
    @classmethod
    def explicit_assessment(cls, value):
        if len(value.strip()) < 10:
            raise ValueError("Assess selected outstanding book items explicitly")
        return value.strip()


def source_rows(body, books, data):
    if body.get("workflow") != "bank-brs":
        raise ValueError("Select a bank reconciliation")
    if len(set(data.exception_ids)) != len(data.exception_ids):
        raise ValueError("Duplicate BRS exception selection")
    exceptions = {row["id"]: row for row in body["rows"]}
    original = {row["id"]: row for row in books["rows"]}
    if len(original) != len(books["rows"]):
        raise ValueError("Duplicate original book row identity")
    params = body["parameters"]
    rows = []
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for identifier in data.exception_ids:
            exception = exceptions.get(identifier)
            if not exception or exception.get("side") != "books":
                raise ValueError(
                    "Only selected book-side BRS exceptions can establish outstanding items"
                )
            book = original.get(exception.get("source_id"))
            if not book or any(
                book[key] != exception[key] for key in ("reference", "currency", "amount")
            ):
                raise ValueError("BRS exception differs from its retained book transaction")
            if book["account"] != params["account"] or book["currency"] != params["currency"]:
                raise ValueError("Original book transaction differs from BRS account/currency")
            row = BankOutstanding(
                id=identifier,
                account=book["account"],
                currency=book["currency"],
                date=book["date"],
                balance_date=body["as_of"],
                reference=book["reference"],
                amount=book["amount"],
                evidence_reference="BRS:" + identifier,
            ).model_dump(mode="json")
            rows.append(
                {
                    **row,
                    "source_brs_exception_id": identifier,
                    "source_book_row_id": book["id"],
                    "source_book_evidence_row": book.get("source_row"),
                    "source_candidate_cause": exception.get("cause"),
                    "source_exception_disposition": exception.get("auditor_status"),
                }
            )
        total = sum((Decimal(row["amount"]) for row in rows), Decimal(0))
    if len(rows) != data.expected_rows or total != data.signed_total:
        raise ValueError(
            "Independent outstanding row-count or signed amount control does not agree"
        )
    return rows, {params["currency"]: str(total)}
