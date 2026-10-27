"""Bind assessed ESI bases to reviewed member evidence without deriving eligibility."""

from datetime import date
from decimal import Decimal

from fastapi import HTTPException

COMPONENTS = {"ESI:EMPLOYEE", "ESI:EMPLOYER"}


def bind(data, tables, body, receipt):
    if (
        data.workflow != "india-payroll-rules"
        or str(data.esic_population_review_id) != receipt["id"]
    ):
        raise ValueError("The ESIC population link does not belong to this contribution request")
    if (
        body.get("workflow") != "india-esic-population"
        or body.get("esic_population_contract") != "india-esic-population/1"
        or body.get("review_status") != "REVIEWED"
        or body.get("blocked")
    ):
        raise ValueError("Select a current independently reviewed complete ESIC member population")
    if date.fromisoformat(body["parameters"]["as_of"]) > data.as_of:
        raise ValueError("The ESIC review date is after the contribution reconciliation date")
    scope = body["esic_population_scope"]
    members = {}
    for row in body["rows"]:
        if (row["registration"], row["period"]) != (scope["registration"], scope["period"]):
            raise ValueError("ESIC review members must retain one employer and wage month")
        if (
            row["subject"] in members
            or row.get("payroll_id") is None
            or row.get("reported_id") is None
        ):
            raise ValueError("Retain unique ESIC members with both payroll and reported evidence")
        if row["state"] != "MATCHED" and row.get("auditor_status") != "EXCEPTION_DOCUMENTED":
            raise ValueError(
                "Document every ESIC population exception before linking contribution bases"
            )
        members[row["subject"]] = row
    if not members:
        raise ValueError("An empty ESIC population cannot establish contribution member coverage")
    selected = set(data.esic_components)
    expected = {(subject, component) for subject in members for component in selected}
    links = {}
    for basis in tables["bases"]:
        if basis["component"] not in COMPONENTS:
            continue
        identity = basis["subject"], basis["component"]
        if (basis["registration"], basis["period"]) != (
            scope["registration"],
            scope["period"],
        ) or identity not in expected:
            raise ValueError(
                "ESI bases fall outside the selected ESIC employer, month, members or components"
            )
        if identity in links:
            raise ValueError(
                "Retain exactly one ESI basis per reviewed member and selected component"
            )
        member = members[basis["subject"]]
        links[identity] = {
            "population_row_id": member["id"],
            "basis_source_id": basis["id"],
            "population_state": member["state"],
            "population_exceptions": member.get("exceptions", []),
            "population_exception_disposition": member.get("auditor_status"),
            "population_exception_comments": member.get("auditor_comments"),
            "payroll_wages": member["payroll_amount"],
            "reported_wages": member["reported_amount"],
            "payroll_paid_days": member["payroll_paid_days"],
            "reported_paid_days": member["reported_paid_days"],
            "payroll_zero_wage_reason": member["payroll_zero_wage_reason"],
            "reported_zero_wage_reason": member["reported_zero_wage_reason"],
            "payroll_zero_day_reason": member.get("payroll_zero_day_reason"),
            "reported_zero_day_reason": member.get("reported_zero_day_reason"),
            "payroll_last_working_day": member["payroll_last_working_day"],
            "reported_last_working_day": member["reported_last_working_day"],
            "assessed_base": basis["amount"],
            "base_minus_payroll_wages": str(
                Decimal(basis["amount"]) - Decimal(member["payroll_amount"])
            ),
            "base_minus_reported_wages": str(
                Decimal(basis["amount"]) - Decimal(member["reported_amount"])
            ),
            "eligible_as_assessed": basis["eligible"],
            "eligibility_reference": basis["eligibility_reference"],
            "basis_assessment": basis["assessment"],
        }
    if set(links) != expected:
        raise ValueError(
            "Every reviewed ESIC member needs one explicit basis for each selected ESI component, including zero-wage and ineligible members"
        )
    return links, {
        "status": "BOUND",
        "review_receipt": receipt,
        "scope": scope,
        "components": sorted(selected),
        "members": len(members),
        "basis_rows": len(links),
        "documented_population_exceptions": sum(
            row["state"] != "MATCHED" for row in members.values()
        ),
        "assessment": data.esic_basis_scope_assessment,
        "eligibility_status": "ASSESSED_SEPARATELY_NOT_INFERRED_FROM_ESIC_WAGES",
        "payment_verification": "NOT_PERFORMED_BY_POPULATION_BINDING",
    }


def annotate(result, links, metadata):
    rows = []
    for row in result["rows"]:
        identity = row["subject"], row["component"]
        if row["component"] in COMPONENTS:
            link = links.get(identity)
            if link is None or row.get("basis_source_id") != link["basis_source_id"]:
                raise ValueError(
                    "Reported ESI contributions extend beyond the reviewed ESIC member/component coverage"
                )
            row = {
                **row,
                "esic_population_basis": link,
                "esic_payroll_wages": link["payroll_wages"],
                "esic_reported_wages": link["reported_wages"],
                "esic_base_minus_payroll_wages": link["base_minus_payroll_wages"],
                "esic_base_minus_reported_wages": link["base_minus_reported_wages"],
            }
        rows.append(row)
    return {
        **result,
        "rows": rows,
        "esic_population_binding": metadata,
        "limitations": [
            *result.get("limitations", []),
            "Linked ESIC wages and days do not establish statutory contribution bases, membership eligibility, rates, filing or payment; explicit basis assessments and reviewed rules remain required",
        ],
    }


async def resolve(db, ctx, eng, data):
    from app.modules.intelligence import service

    selected = await service.event(db, ctx, eng.id, data.esic_population_review_id, True)
    if selected.kind != "country-workflow":
        raise HTTPException(422, "Select an independently reviewed ESIC population result")
    return (
        selected.body,
        service.event_receipt(selected),
        set(selected.body.get("contributors", [str(selected.created_by)])),
    )
