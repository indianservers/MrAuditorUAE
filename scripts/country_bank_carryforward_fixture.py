"""Fictional retained partial-clearance populations for the owned browser test."""


async def prepare(client, headers, engagements, reviewer):
    from tests.qa_crud.test_country_workflows import decision, execute, source
    from tests.unit.test_bank_clearance import population

    fixtures = {}
    for country, engagement, currency in engagements:
        p = population(currency)
        selected = {}
        for role, kind in (("outstanding", "bank-outstanding"), ("statement", "transactions"), ("allocations", "bank-clearances")):
            imported = await source(client, headers, engagement, p[role], f"SYNTHETIC {country} partial {role}",
                table_type=kind, totals={currency: "40" if role == "allocations" else "-100"})
            reviewed = await decision(client, reviewer[0], engagement, imported)
            assert reviewed.status_code == 201, reviewed.text
            selected[role] = reviewed.json()["id"]
        parent = await execute(client, headers, engagement, "country-workflow", {
            "workflow": "bank-subsequent-clearance", "source_ids": selected, "account": "BANK-1",
            "currency": currency, "as_of": "2026-06-30", "review_through": "2026-07-31",
            "title": f"SYNTHETIC {country} reviewed partial clearance",
            "rationale": "Retained statement window and unresolved reversals independently assessed",
        })
        for row in parent["body"]["rows"]:
            disposition = await decision(client, headers, engagement, parent, "accept", item_id=row["id"])
            assert disposition.status_code == 201, disposition.text
            parent = disposition.json()
        reviewed = await decision(client, reviewer[0], engagement, parent)
        assert reviewed.status_code == 201, reviewed.text
        fixtures[country] = {"parent": reviewed.json()["id"], "engagement": engagement}
        p["statement"][0].update(date="2026-08-05", amount="-60")
        p["allocations"][0]["amount"] = "60"
        for role, kind in (("statement", "transactions"), ("allocations", "bank-clearances")):
            imported = await source(client, headers, engagement, p[role], f"SYNTHETIC {country} August {role}",
                table_type=kind, totals={currency: "60" if role == "allocations" else "-60"})
            reviewed = await decision(client, reviewer[0], engagement, imported)
            assert reviewed.status_code == 201, reviewed.text
            fixtures[country][role] = reviewed.json()["id"]
    return fixtures
