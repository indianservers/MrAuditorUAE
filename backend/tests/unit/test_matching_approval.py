from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.intelligence.matching_review import (
    exception_reference,
    review_requirements,
    review_summary,
    verify_review,
)


def finding(item="L", **changes):
    return dict(
        item_id=item,
        record_id=str(uuid4()),
        kind="findings",
        reason="Reviewed unresolved difference",
        actor="preparer",
        **changes,
    )


@pytest.mark.parametrize("missing", ["auditor_status", "auditor", "auditor_comments"])
def test_machine_match_needs_the_recorded_auditor_decision(missing):
    match = dict(
        auditor_status="ACCEPTED", auditor="preparer", auditor_comments="Compared retained sources"
    )
    match.pop(missing)
    with pytest.raises(HTTPException, match="Every proposed match"):
        review_requirements(dict(matches=[match]))


@pytest.mark.parametrize("kind", ["requests", "review-notes", "", None])
def test_requests_and_notes_are_not_unmatched_dispositions(kind):
    link = finding()
    link["kind"] = kind
    with pytest.raises(HTTPException, match="Every unmatched transaction"):
        review_requirements(dict(unmatched_left=[dict(id="L")], exceptions=[link]))


@pytest.mark.parametrize("missing", ["record_id", "actor", "reason"])
def test_finding_link_requires_identity_and_documented_rationale(missing):
    link = finding()
    link.pop(missing)
    with pytest.raises(HTTPException, match="Every unmatched transaction"):
        review_requirements(dict(unmatched_right=[dict(id="L")], exceptions=[link]))


def test_complete_review_counts_are_independent_of_read_pages_and_duplicate_links():
    links = [finding(str(i)) for i in range(242)]
    body = dict(
        unmatched_left=[dict(id=str(i)) for i in range(121)],
        unmatched_right=[dict(id=str(i)) for i in range(121, 242)],
        exceptions=links + [links[0]],
    )
    assert review_summary(body)["unmatched_transactions"] == 242
    assert review_summary(body)["unmatched_with_findings"] == 242
    assert len(review_requirements(body)) == 243
    body["exceptions"] = links[:-1]
    with pytest.raises(HTTPException, match="Every unmatched transaction"):
        review_requirements(body)


@pytest.mark.parametrize(
    "change", ["archived", "kind", "another-item", "another-population", "invalid-id"]
)
async def test_approval_revalidates_actual_scoped_finding(change, monkeypatch):
    from app.modules.audit_execution import service as audit

    link = finding()
    dependencies = [dict(type="snapshot", id="SYNTHETIC-POPULATION")]
    record = SimpleNamespace(
        kind="findings",
        status="IN_PROGRESS",
        reference=exception_reference(dependencies, "L", "findings"),
    )
    if change == "archived":
        record.status = "ARCHIVED"
    elif change == "kind":
        record.kind = "requests"
    elif change == "another-item":
        record.reference = exception_reference(dependencies, "OTHER", "findings")
    elif change == "another-population":
        record.reference = exception_reference([], "L", "findings")
    else:
        link["record_id"] = "invalid"

    async def get(*args, **kwargs):
        return record

    monkeypatch.setattr(audit, "get_record", get)
    obj = SimpleNamespace(
        dependencies=dependencies, body=dict(unmatched_left=[dict(id="L")], exceptions=[link])
    )
    with pytest.raises(HTTPException) as error:
        await verify_review(None, None, None, obj)
    assert error.value.status_code == 409


async def test_one_actual_finding_read_per_distinct_record_and_access_errors_propagate(monkeypatch):
    from app.modules.audit_execution import service as audit

    link = finding()
    calls = []
    obj = SimpleNamespace(
        dependencies=[], body=dict(unmatched_left=[dict(id="L")], exceptions=[link, link])
    )

    async def get(db, ctx, eid, rid, **kwargs):
        calls.append((ctx, eid, rid))
        return SimpleNamespace(
            kind="findings",
            status="IN_PROGRESS",
            reference=exception_reference([], "L", "findings"),
        )

    monkeypatch.setattr(audit, "get_record", get)
    await verify_review(None, "ACTOR", "ENGAGEMENT", obj)
    assert len(calls) == 1 and calls[0][:2] == ("ACTOR", "ENGAGEMENT")

    async def denied(*args, **kwargs):
        raise HTTPException(403, "Scoped access denied")

    monkeypatch.setattr(audit, "get_record", denied)
    with pytest.raises(HTTPException) as error:
        await verify_review(None, "ACTOR", "ENGAGEMENT", obj)
    assert error.value.status_code == 403
