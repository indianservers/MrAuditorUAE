"""Read all retained ambiguity candidates without loading every source row into the UI."""

from fastapi import HTTPException


def exception_reference(dependencies, item_id, kind):
    import hashlib
    import json

    identity = json.dumps(
        {"dependencies": dependencies, "item": item_id, "kind": kind}, sort_keys=True
    )
    return "INT-" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def _accepted(match):
    return (
        match.get("auditor_status") == "ACCEPTED"
        and bool(match.get("auditor"))
        and bool(str(match.get("auditor_comments", "")).strip())
    )


def _finding_links(body):
    needed = {
        row["id"] for key in ("unmatched_left", "unmatched_right") for row in body.get(key, [])
    }
    links = [
        row
        for row in body.get("exceptions", [])
        if row.get("item_id") in needed
        and row.get("kind") == "findings"
        and row.get("record_id")
        and row.get("actor")
        and str(row.get("reason", "")).strip()
    ]
    return needed, links


def review_summary(body):
    needed, links = _finding_links(body)
    return {
        "proposed_matches": len(body.get("matches", [])),
        "accepted_matches": sum(_accepted(match) for match in body.get("matches", [])),
        "unmatched_transactions": len(needed),
        "unmatched_with_findings": len({row["item_id"] for row in links}),
        "complete_retained_candidates": saved_candidates_complete(body),
        "scope": "RECORDED_DECISIONS_ONLY_LIVE_FINDING_VALIDATION_AT_APPROVAL",
    }


def review_requirements(body):
    """Accepting a proposed match and documenting an unmatched item are distinct."""
    if not saved_candidates_complete(body):
        raise HTTPException(
            409, "Regenerate matching with complete retained candidates before approval"
        )
    if any(not _accepted(match) for match in body.get("matches", [])):
        raise HTTPException(
            409, "Every proposed match needs recorded auditor acceptance before approval"
        )
    needed, links = _finding_links(body)
    if needed != {row["item_id"] for row in links}:
        raise HTTPException(
            409,
            "Every unmatched transaction needs a linked documented finding before approval; requests and notes do not dispose of it",
        )
    return links


async def verify_review(db, ctx, eid, obj):
    from uuid import UUID

    from app.modules.audit_execution import service as audit

    links = review_requirements(obj.body)
    checked = {}
    for link in links:
        identifier = link["record_id"]
        if identifier not in checked:
            try:
                rid = UUID(identifier)
            except (ValueError, TypeError, AttributeError):
                raise HTTPException(409, "A reconciliation finding reference is invalid") from None
            checked[identifier] = await audit.get_record(db, ctx, eid, rid, lock=False)
        record = checked[identifier]
        if (
            record.kind != "findings"
            or record.status == "ARCHIVED"
            or record.reference
            != exception_reference(obj.dependencies, link["item_id"], "findings")
        ):
            raise HTTPException(
                409,
                "Reconciliation disposition needs its current scoped finding for the original transaction",
            )


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
