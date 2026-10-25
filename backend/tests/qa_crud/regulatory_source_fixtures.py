"""Explicit fictional retained copies for rule mechanics, never legal qualification."""

import json


async def retain(c, h, payload, *, uploader=None):
    citation = payload["citations"][0]
    date = citation.get("retrieved_on") or "2026-10-24"
    content = b"SYNTHETIC rule source; not official legislation or a legally adopted rate.\n"
    response = await c.post(
        "/api/v1/regulatory/sources",
        headers=uploader or h,
        data={
            "metadata": json.dumps(
                {
                    "title": "SYNTHETIC rule reference copy",
                    "country": payload["country"],
                    "source_url": citation["url"],
                    "retrieved_on": date,
                }
            )
        },
        files={"file": ("SYNTHETIC-rule-source.txt", content, "text/plain")},
    )
    assert response.status_code == 201, response.text
    document = response.json()
    citation.update(
        source_document_id=document["id"],
        document_sha256=document["sha256"],
        retrieval_status="RETRIEVED",
        retrieved_on=date,
    )
    return document
