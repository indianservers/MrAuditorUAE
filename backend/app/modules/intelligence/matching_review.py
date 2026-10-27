"""Read all retained ambiguity candidates without loading every source row into the UI."""

from fastapi import HTTPException


def saved_candidates_complete(body):
    ambiguous = body.get("ambiguous", [])
    return not ambiguous or (
        body.get("matching_contract") == "indexed-transaction-candidates/1"
        and all(
            type(row.get("candidate_count")) is int
            and row["candidate_count"] >= 2
            and row["candidate_count"] == len(row.get("candidate_ids", []))
            and len(set(row["candidate_ids"])) == row["candidate_count"]
            and not row.get("candidate_preview_truncated")
            for row in ambiguous
        )
        and body.get("ambiguity_link_count") == sum(row["candidate_count"] for row in ambiguous)
    )


async def candidate_page(db, ctx, eid, obj, left_id, offset, limit):
    from uuid import UUID

    from app.modules.intelligence import service

    body = obj.body
    if not (obj.kind == "reconciliation" or body.get("workflow") == "bank-brs"):
        raise HTTPException(422, "Select a retained bank/transaction matching result")
    if not saved_candidates_complete(body):
        raise HTTPException(
            409, "Regenerate matching with complete retained candidates before review"
        )
    group = next((row for row in body.get("ambiguous", []) if row["left_id"] == left_id), None)
    if group is None:
        raise HTTPException(404, "Ambiguous source item not found")
    if obj.kind == "reconciliation":
        left, right = body["source_rows"], body["destination_rows"]
    else:
        sources = body["parameters"]["source_ids"]
        books = await service.event(db, ctx, eid, UUID(sources["books"]))
        statement = await service.event(db, ctx, eid, UUID(sources["statement"]))
        left, right = books.body["rows"], statement.body["rows"]
    book = next((row for row in left if row["id"] == left_id), None)
    bank = {row["id"]: row for row in right}
    if book is None or any(identifier not in bank for identifier in group["candidate_ids"]):
        raise HTTPException(409, "Retained candidate source population is incomplete")
    ids = group["candidate_ids"][offset : offset + limit]
    proposed = {
        identifier: match for match in body.get("matches", []) for identifier in match["right_ids"]
    }
    return {
        "left": book,
        "items": [
            {**bank[identifier], "machine_match": proposed.get(identifier)} for identifier in ids
        ],
        "total": group["candidate_count"],
        "offset": offset,
        "limit": limit,
        "candidate_retention": "COMPLETE_RETAINED_CANDIDATES_PAGED",
        "interpretation": "Possible competing matches only; no candidate is selected or approved",
    }
