import io
import os
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, create
from tests.phase5 import test_reporting

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)


async def test_prior_group_amounts_export_and_recursive_freshness(environment, monkeypatch):
    c = environment
    parent = await test_reporting.prepared(c, suffix="-comparative-current-parent")
    h = parent[0]

    async def post(path, body):
        response = await c.post("/api/v1/" + path, headers=h, json=body)
        assert response.status_code == 201, response.text
        return response.json()

    engagement = (await c.get(f"/api/v1/engagements/{parent[1]}", headers=h)).json()
    entity = (await c.get(f"/api/v1/entities/{engagement['entity_id']}", headers=h)).json()
    subsidiary = await post(
        "entities",
        {
            "client_id": entity["client_id"],
            "name": "SYNTHETIC comparative subsidiary",
            "country": "AE",
            "jurisdiction": "Synthetic",
            "functional_currency": "USD",
            "presentation_currency": "USD",
        },
    )
    packages = {2026: [parent], 2025: []}
    original_csv = test_reporting.CSV
    for year in [2025, 2026]:
        for index, member_entity in enumerate([entity, subsidiary]):
            if year == 2026 and index == 0:
                continue
            period = await post(
                "financial-periods",
                {
                    "entity_id": member_entity["id"],
                    "start_date": f"{year}-01-01",
                    "end_date": f"{year}-12-31",
                },
            )
            eng = await post(
                "engagements",
                {
                    "entity_id": member_entity["id"],
                    "period_id": period["id"],
                    "name": f"SYNTHETIC comparative {year} member {index}",
                    "engagement_type": "External Audit",
                },
            )
            options = {
                "client_id": entity["client_id"],
                "entity_id": member_entity["id"],
                "period_id": period["id"],
                "currency": "USD" if index else "AED",
                "source_complete": True,
            }
            monkeypatch.setattr(
                test_reporting, "CSV", original_csv.replace(b"2026", str(year).encode())
            )
            packages[year].append(
                await test_reporting.prepared(
                    c,
                    (h, options, eng["id"], f"/api/v1/engagements/{eng['id']}/audit"),
                    f"-comparative-{year}-{index}",
                    scale=2 if year == 2026 else 1,
                )
            )
    monkeypatch.setattr(test_reporting, "CSV", original_csv)
    groups = {}
    group_bodies = {}
    for year, sources in packages.items():
        members = []
        for index, package in enumerate(sources):
            _, eid, base, reviewer, partner, profile, _, _, _ = package
            financial = await post(
                f"ifrs/engagements/{eid}/financial-statements/{profile['id']}", None
            )
            approval = await create(
                c,
                h,
                base,
                "ifrs-financials",
                {
                    "run_id": financial["id"],
                    "release_rationale": "SYNTHETIC independently reviewed member reporting package",
                },
            )
            approval = await action(c, h, base, approval, "submit")
            approval = await action(c, reviewer[0], base, approval, "approve")
            await action(c, partner[0], base, approval, "approve")
            members.append(
                {
                    "engagement_id": eid,
                    "financial_run_id": financial["id"],
                    "ownership": "0.8" if index else "1",
                    "power": True,
                    "variable_returns": True,
                    "ability_to_affect_returns": True,
                    "control_rationale": "SYNTHETIC unchanged full-period group control",
                    "closing_rate": ("2" if year == 2025 else "3") if index else "1",
                    "average_rate": ("1.5" if year == 2025 else "2.5") if index else "1",
                    "historical_rate": "1",
                    "opening_rate": "1",
                    "rate_source": "SYNTHETIC independently retained representative dated rates",
                    "rate_date": f"{year}-12-31",
                    "control_effective_from": "2025-01-01",
                    "acquisition_type": "business_combination" if index else "parent",
                    "accounting_policy": "SYNTHETIC unchanged group policy",
                }
            )
        body = {
            "presentation_currency": "AED",
            "members": members,
            "intercompany_nil_assessment": {
                "member_engagement_ids": [m["engagement_id"] for m in members],
                "period_start": f"{year}-01-01",
                "period_end": f"{year}-12-31",
                "rationale": "SYNTHETIC complete group reciprocal population assessed as nil",
                "source_record_ids": [p[7]["id"] for p in sources],
            },
        }
        group_bodies[year] = body
        source = await sources[0][8]("consolidation", body)
        groups[year] = await post(
            f"ifrs/engagements/{sources[0][1]}/consolidation/{source['id']}", None
        )
    current_eid = packages[2026][0][1]
    prior_eid = packages[2025][0][1]
    comparative = {
        "engagement_id": prior_eid,
        "run_id": groups[2025]["id"],
        "basis": "SYNTHETIC unchanged legal-entity membership, ownership and chart classification; retain prior reported amounts without restatement",
    }
    source = await parent[8](
        "consolidation", {**group_bodies[2026], "comparative_source": comparative}
    )
    result = await post(f"ifrs/engagements/{current_eid}/consolidation/{source['id']}", None)
    rows = {r["line_code"]: r for r in result["results"]["lines"]}
    assert Decimal(rows["100"]["current"]) == 910
    assert Decimal(rows["100"]["comparative"]) == 390
    assert result["results"]["comparative"]["sha256"] == groups[2025]["sha256"]
    assert not result["results"]["validation"]["ready"]
    supporting = result["results"]["execution"]["supporting_runs"]
    assert {"engagement_id": prior_eid, "id": groups[2025]["id"]} in supporting
    download = await c.get(
        f"/api/v1/ifrs/engagements/{current_eid}/runs/{result['id']}/export/xlsx", headers=h
    )
    assert download.status_code == 200, download.text
    workbook = load_workbook(io.BytesIO(download.content), read_only=True)
    exported = list(workbook["Financial package"].values)
    assert any(row[0] == "Cash" and row[2] == "390.00" for row in exported)
    assert any(row[0] == "PRIOR GROUP COMPARATIVE SOURCE" for row in exported)
    workbook.close()
    wrong = await parent[8](
        "consolidation",
        {
            **group_bodies[2026],
            "comparative_source": {
                **comparative,
                "engagement_id": current_eid,
                "run_id": groups[2026]["id"],
            },
        },
    )
    assert (
        await c.post(
            f"/api/v1/ifrs/engagements/{current_eid}/consolidation/{wrong['id']}", headers=h
        )
    ).status_code == 422
    validation_path = f"/api/v1/ifrs/engagements/{current_eid}/runs/{result['id']}/validate"
    assert (await c.get(validation_path, headers=h)).json()["dependencies_current"]
    # A newly approved prior-period note was not in the copied dependency list.
    # Recursively checking the retained prior run must still detect it.
    previous_parent = packages[2025][0]
    await previous_parent[8](
        "note",
        {
            "profile_id": previous_parent[5]["id"],
            "note_reference": "SYNTHETIC-new-prior-note",
            "text": "SYNTHETIC newly approved prior-period disclosure requires a new financial package",
            "linked_line_codes": ["100"],
        },
    )
    assert not (await c.get(validation_path, headers=h)).json()["dependencies_current"]
    assert (
        await c.post(
            f"/api/v1/ifrs/engagements/{current_eid}/consolidation/{source['id']}", headers=h
        )
    ).status_code == 409
