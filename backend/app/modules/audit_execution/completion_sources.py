"""A retained review status cannot substitute for current dependent sources."""

import uuid

from fastapi import HTTPException

from app.modules.lineage.working_papers import freshness


async def reviewed_source_control(db, ctx, rows):
    reviewed = sorted(
        (row for row in rows if row.status in {"APPROVED", "LOCKED"}),
        key=lambda row: str(row.id),
    )
    issues = []
    cache: dict[uuid.UUID, str] = {}
    for row in reviewed:
        try:
            # Do not share reporting-context expectations across engagements:
            # explicitly linked comparative/group sources have their own context.
            state = await freshness(db, ctx, row, cache=cache)
        except HTTPException as exc:
            if exc.status_code not in {401, 403, 404, 409, 422}:
                raise
            state = "BLOCKED"
        except (ValueError, KeyError, TypeError):
            state = "UNVERIFIED"
        if state != "CURRENT":
            # Aggregate readiness reveals no source bodies or sensitive titles.
            issues.append({"record_id": str(row.id), "kind": row.kind, "freshness": state})
    return {
        "code": "reviewed_source_freshness",
        "passed": not issues,
        "description": "Current sources for every approved or locked audit record",
        "record_ids": [issue["record_id"] for issue in issues],
        "source_issues": issues,
        "checked_records": len(reviewed),
        "source_check_contract": "reviewed-source-freshness/1",
    }
