import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.integration.test_platform import environment as environment
from tests.qa_crud.test_country_workflows import double_boundaries, execute
from tests.qa_crud.test_generic_candidates import context, prepare

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Owned database")


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_original_statement_account_requires_explicit_reviewed_gl_mapping(
    environment, monkeypatch, country
):
    c = environment
    double_boundaries(monkeypatch)
    h, options, eid, audit = await context(c, country)
    payload, _ = await prepare(
        c,
        h,
        options,
        eid,
        audit,
        country,
        count=1,
        source_account_codes=("00000123",),
        bank_account_label="100",
    )
    saved = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-bank-account-labels"
        / country
    )
    expected = json.loads((saved / "expected.json").read_text(encoding="utf-8"))
    original_hash = hashlib.sha256((saved / "statement.csv").read_bytes()).hexdigest()
    assert original_hash == expected["source_sha256"]
    original = (
        await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{payload['statement_source_id']}",
            headers=h,
        )
    ).json()
    assert (
        next(dep["sha256"] for dep in original["dependencies"] if dep["type"] == "evidence")
        == original_hash
    )
    obj = await execute(c, h, eid, "reconciliation", payload)
    scope = obj["body"]["bank_account_scope"]
    assert scope["matching_account_code"] == "100"
    assert scope["statement_original_account_code"] == "00000123"
    assert scope["source_basis"] == "EXPLICIT_ORIGINAL_TO_GL_LABEL"
    assert scope["bank_authentication"] == "NOT_ESTABLISHED"
    assert len(obj["body"]["matches"]) == 1
    assert obj["body"]["destination_rows"][0]["original_account_code"] == "00000123"


@pytest.mark.parametrize("codes", [("",), ("300",), ("100", "300")])
async def test_missing_wrong_and_mixed_bank_accounts_publish_no_matching_result(
    environment, monkeypatch, codes
):
    c = environment
    double_boundaries(monkeypatch)
    h, options, eid, audit = await context(c, "AE")
    payload, _ = await prepare(c, h, options, eid, audit, "AE", count=2, source_account_codes=codes)
    await execute(c, h, eid, "reconciliation", payload, failed="Every bank row must identify")


async def test_several_gl_accounts_cannot_be_queued_as_one_bank_scope(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, options, eid, audit = await context(c, "AE")
    payload, _ = await prepare(c, h, options, eid, audit, "AE", count=1)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    accounts = (
        await c.get(
            prefix + "/accounts", headers=h, params=dict(snapshot_id=payload["snapshot_id"])
        )
    ).json()["items"]
    response = await c.post(
        prefix + "/jobs",
        headers={**h, "Idempotency-Key": "invalid-multiple-bank-accounts"},
        json=dict(
            operation="reconciliation",
            payload={**payload, "account_ids": [a["id"] for a in accounts]},
        ),
    )
    assert response.status_code == 422, response.text


async def test_declared_mapping_cannot_merge_mixed_original_statement_accounts(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, options, eid, audit = await context(c, "AE")
    payload, _ = await prepare(
        c, h, options, eid, audit, "AE", count=2, source_account_codes=("100", "300")
    )
    original = (
        await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{payload['statement_source_id']}",
            headers=h,
        )
    ).json()
    await execute(
        c,
        h,
        eid,
        "source-table",
        dict(
            evidence_version_id=original["body"]["evidence_version_id"],
            table_kind="bank",
            bank_account_label="100",
            bank_account_mapping_rationale="Attempted merge of two source bank accounts",
        ),
        failed="cannot merge mixed or partially identified source accounts",
    )
