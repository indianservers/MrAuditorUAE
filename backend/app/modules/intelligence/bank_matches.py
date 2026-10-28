"""Read exact retained proposal groups without sending whole source populations."""

from uuid import UUID

from fastapi import HTTPException

FIELDS = (
    "id",
    "account",
    "account_code",
    "original_account_code",
    "reference_basis",
    "reference",
    "counterparty",
    "date",
    "amount",
    "currency",
    "bank_booking_date",
    "bank_value_date",
    "bank_date_basis",
    "is_reversal",
    "source_record_id",
    "source_row",
)


def select_group(matches, index, left, right):
    if not isinstance(matches, list):
        raise HTTPException(409, "Retained matched proposal collection is incomplete")
    if type(index) is not int or index < 0:
        raise HTTPException(422, "Select a nonnegative retained proposal index")
    if index >= len(matches):
        raise HTTPException(404, "Retained matched proposal not found")
    match = matches[index]
    if not isinstance(match, dict):
        raise HTTPException(409, "Retained matched proposal is incomplete")
    selected = {}
    for side, rows, key in [("books", left, "left_ids"), ("statement", right, "right_ids")]:
        ids = match.get(key)
        if (
            not isinstance(ids, list)
            or not ids
            or len(ids) > 100
            or any(not isinstance(value, str) or not value for value in ids)
            or len(set(ids)) != len(ids)
        ):
            raise HTTPException(
                409, "Retained match identity is incomplete or exceeds the inspection bound"
            )
        if (
            not isinstance(rows, list)
            or len(rows) > 20000
            or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in rows)
        ):
            raise HTTPException(409, "Retained match source population cannot be verified")
        population = {row["id"]: row for row in rows}
        if len(population) != len(rows) or any(value not in population for value in ids):
            raise HTTPException(409, "Retained match source population is incomplete or ambiguous")
        selected[side] = [
            {field: population[value][field] for field in FIELDS if field in population[value]}
            for value in ids
        ]
    return {
        "index": index,
        "total": len(matches),
        "proposal": match,
        **selected,
        "source_detail": "EXACT_SAVED_MATCH_IDENTITIES_IN_SAVED_ORDER",
        "interpretation": "Machine proposal and original source facts; bank authentication, payment confirmation and accounting postings are not established",
    }


async def detail(db, ctx, eid, obj, index):
    from app.modules.intelligence import service

    body = obj.body
    if obj.kind == "reconciliation":
        left, right = body.get("source_rows", []), body.get("destination_rows", [])
    elif obj.kind == "country-workflow" and body.get("workflow") == "bank-brs":
        try:
            ids = body["parameters"]["source_ids"]
            books = await service.event(db, ctx, eid, UUID(ids["books"]))
            statement = await service.event(db, ctx, eid, UUID(ids["statement"]))
        except (KeyError, TypeError, ValueError):
            raise HTTPException(
                409, "Retained bank matching source references are incomplete"
            ) from None
        if any(
            source.kind != "workflow-source" or source.body.get("table_type") != "transactions"
            for source in (books, statement)
        ):
            raise HTTPException(409, "Retained bank matching requires original transaction sources")
        left, right = books.body.get("rows", []), statement.body.get("rows", [])
    else:
        raise HTTPException(422, "Select a retained bank or transaction matching result")
    return select_group(body.get("matches", []), index, left, right)
