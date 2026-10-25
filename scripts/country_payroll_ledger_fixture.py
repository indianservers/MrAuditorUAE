"""Retained, independently reviewed fictional accounting inputs for the browser."""


async def prepare(client, headers, engagements, reviewer):
    from tests.qa_crud.test_payroll_ledger import prepare_sources

    result = {}
    for country, engagement, currency in engagements:
        sources, _ = await prepare_sources(client, headers, engagement, currency, reviewer)
        result[country] = {"engagement": engagement, "sources": sources}
    return result
