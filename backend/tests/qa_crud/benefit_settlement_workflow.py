"""Real retained gratuity bridge and bank allocation; shared scanner/dispatch doubles."""

import io
import json
from copy import deepcopy

from openpyxl import load_workbook

from app.modules.country_workflows.schemas import Obligation
from tests.phase4.test_workflows import actor, create, grant
from tests.qa_crud.test_country_workflows import decision, execute, source


async def verify_settlement(c, h, eid, base, benefit, reviewer):
    endpoint = f"/api/v1/intelligence/engagements/{eid}"
    uploader = await actor(h, "Firm Administrator", "gratuity-evidence-uploader")
    await grant(c, h, base, uploader)
    support_record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    uploaded = await c.post(
        base + "/evidence-files/" + support_record["id"],
        headers=uploader[0],
        files={
            "file": (
                "SYNTHETIC-settlement-scope.txt",
                b"SYNTHETIC EMPLOYER AND DUE-DATE SUPPORT ONLY",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    request = {
        "result_id": benefit["id"],
        "employer_registration": "SYN-EMPLOYER",
        "settlement_evidence_version_id": uploaded.json()["id"],
        "selections": [
            {
                "result_row_id": key,
                "due_date": "2026-07-14",
                "due_date_reference": "SYN-EMPLOYMENT-" + key,
            }
            for key in ("E1", "E2")
        ],
        "expected_rows": 2,
        "control_total": "3150",
        "label": "Synthetic expected gratuity settlement",
        "assessment": "Synthetic independent employee identity, employer registration and settlement due dates",
    }
    wrong = await c.post(
        endpoint + "/benefit-settlement-source",
        headers=h,
        json={**request, "control_total": "3149"},
    )
    assert wrong.status_code == 422 and "amount control" in wrong.text
    created = await c.post(endpoint + "/benefit-settlement-source", headers=h, json=request)
    assert created.status_code == 201, created.text
    bridge = created.json()
    assert bridge["body"]["review_status"] == "UNVERIFIED"
    assert bridge["body"]["control_totals"] == {"AED": "3150.00"}
    assert (await decision(c, h, eid, bridge)).status_code == 403
    assert (await decision(c, uploader[0], eid, bridge)).status_code == 403
    bridge_reviewer = await actor(h, "Firm Administrator", "gratuity-bridge-reviewer")
    await grant(c, h, base, bridge_reviewer)
    approved = await decision(c, bridge_reviewer[0], eid, bridge)
    assert approved.status_code == 201, approved.text
    bridge_reviewed = approved.json()
    rows = bridge["body"]["rows"]
    assert [row["amount"] for row in rows] == ["2100.00", "1050.00"]
    assert {row["benefit_scope"]["work_model"] for row in rows} == {"full-time", "part-time"}
    reported = [
        {
            **{key: value for key, value in row.items() if key in Obligation.model_fields},
            "id": "REPORTED-" + row["source_result_row_id"],
            "benefit_scope": json.dumps(row["benefit_scope"]),
        }
        for row in rows
    ]
    report_source = await source(
        c,
        h,
        eid,
        reported,
        "Synthetic independent HR settlement register",
        "obligations",
        {"AED": "3150"},
    )
    bank_source = await source(
        c,
        h,
        eid,
        [
            {
                "id": "BANK-1",
                "account": "BANK-1",
                "reference": "SYN-POOLED-EXIT-PAY",
                "date": "2026-07-10",
                "currency": "AED",
                "amount": "-3150",
            }
        ],
        "Synthetic independent bank outflow",
        "transactions",
        {"AED": "-3150"},
    )
    allocation_source = await source(
        c,
        h,
        eid,
        [
            {
                "id": "A-" + row["source_result_row_id"],
                "expected_id": row["id"],
                "reported_id": "REPORTED-" + row["source_result_row_id"],
                "transaction_id": "BANK-1",
                "currency": "AED",
                "amount": row["amount"],
                "evidence_reference": "SYN-EMPLOYEE-ADVICE",
                "rationale": "Synthetic independently assessed employee split of pooled bank outflow",
            }
            for row in rows
        ],
        "Synthetic explicit gratuity bank allocations",
        "obligation-allocations",
        {"AED": "3150"},
    )
    sources = {
        "expected": bridge,
        "reported": report_source,
        "bank": bank_source,
        "allocations": allocation_source,
    }
    payload = {
        "workflow": "obligation-bank-allocations",
        "source_ids": {role: value["id"] for role, value in sources.items()},
        "as_of": "2026-07-31",
        "currency": "AED",
        "account": "BANK-1",
        "obligation_month_start": "2026-06",
        "obligation_month_end": "2026-06",
        "settlement_start": "2026-07-01",
        "bank_payment_sign": "debit-negative",
        "title": "Synthetic gratuity to independent bank review",
        "rationale": "Reviewed employee service scopes, HR register and pooled bank allocations",
    }
    await execute(
        c, h, eid, "country-workflow", payload, failed="Independently review all obligation"
    )
    sources["expected"] = bridge_reviewed
    for role in ("reported", "bank", "allocations"):
        reviewed = await decision(c, bridge_reviewer[0], eid, sources[role])
        assert reviewed.status_code == 201, reviewed.text
        sources[role] = reviewed.json()
    payload["source_ids"] = {role: value["id"] for role, value in sources.items()}
    result = await execute(c, h, eid, "country-workflow", payload)
    obligations = [row for row in result["body"]["rows"] if row["kind"] == "obligation"]
    assert [row["outstanding_amount"] for row in obligations] == ["0.00", "0.00"]
    assert all(row["state"] == "MATCHED" for row in result["body"]["rows"])
    assert obligations[0]["benefit_scope"]["service_start"] == "2025-07-01"
    assert (await decision(c, h, eid, result)).status_code == 403
    final_reviewer = await actor(h, "Firm Administrator", "gratuity-bank-final-reviewer")
    await grant(c, h, base, final_reviewer)
    final = await decision(c, final_reviewer[0], eid, result)
    assert final.status_code == 201, final.text
    result = final.json()
    exported = await c.get(endpoint + f"/events/{result['id']}/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    workbook = load_workbook(io.BytesIO(exported.content))
    exported_rows = list(workbook["Rows"].values)
    columns = exported_rows[0]
    exported_obligation = dict(zip(columns, exported_rows[1], strict=True))
    assert json.loads(exported_obligation["benefit_scope"])["service_end"] == "2026-06-30"
    assert exported_obligation["expected_amount"] == "2100.00"
    # A derived expectation cannot impersonate an independent reported settlement.
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            **payload,
            "source_ids": {
                **payload["source_ids"],
                "expected": sources["reported"]["id"],
                "reported": bridge_reviewed["id"],
            },
        },
        failed="only expected settlement",
    )
    return support_record, bridge_reviewed, result, deepcopy(result["body"])
