"""Source-reconciled Indian statement drafts; no implicit IFRS/Ind AS equivalence."""

from decimal import Decimal, localcontext

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.accounting.models import MappingProfile
from app.modules.intelligence import service as intelligence
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.workspace import resolved
from app.modules.lineage.freshness import mapping_receipt
from app.modules.reconciliation.service import balance


def aggregate(rows):
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        totals = {
            category: sum(
                (Decimal(r["presented_amount"]) for r in rows if r["classification"] == category),
                Decimal(0),
            )
            for category in ["Assets", "Liabilities", "Equity", "Income", "Expenses"]
        }
        profit = totals["Income"] - totals["Expenses"]
        difference = totals["Assets"] - totals["Liabilities"] - totals["Equity"] - profit
    return totals, profit, difference


async def statements(db, ctx, eng, data, request_id):
    binding, context = await resolved(db, ctx, eng)
    if binding.country != "IN" or context["framework"] not in {"AS", "Ind AS"}:
        raise HTTPException(422, "An approved India AS or Ind AS reporting context is required")
    if (context["framework"] == "AS") != (data.division == "I"):
        raise HTTPException(
            422,
            "Division/framework selection is inconsistent; independently assess entity applicability",
        )
    applicability = await intelligence.event(db, ctx, eng.id, data.applicability_id, True)
    if (
        applicability.kind != "statutory-checklist"
        or applicability.body.get("area") != "india-disclosures"
        or applicability.body.get("review_status") != "REVIEWED"
    ):
        raise HTTPException(
            409,
            "A current independently reviewed Indian reporting applicability/disclosure checklist is required",
        )
    if not any(
        item["facts"].get("schedule_iii_division") == data.division
        for item in applicability.body["items"]
    ):
        raise HTTPException(
            409,
            "The reviewed applicability case must explicitly document the selected Schedule III division",
        )
    profile = await db.scalar(
        select(MappingProfile).where(
            MappingProfile.tenant_id == ctx.tenant_id,
            MappingProfile.id == data.mapping_profile_id,
            MappingProfile.entity_id == eng.entity_id,
            MappingProfile.period_id == eng.period_id,
            MappingProfile.approved.is_(True),
        )
    )
    if not profile:
        raise HTTPException(
            409, "An approved accounting mapping profile for this entity/period is required"
        )
    snapshot, receipt = await intelligence.snapshot(db, ctx, eng, data.snapshot_id)
    values = await balance(db, ctx, snapshot.id)
    if not values["balanced"]:
        raise HTTPException(409, "Trial balance does not balance")
    assignments = profile.mapping.get("accounts", {})
    groups = profile.mapping.get("groups", {})
    rows = []
    dependencies = [
        receipt,
        intelligence.event_receipt(applicability),
        {
            "type": "mapping",
            "entity_id": str(eng.entity_id),
            "receipt": await mapping_receipt(db, ctx.tenant_id, eng.entity_id),
        },
        {
            "type": "mapping-profile",
            "id": str(profile.id),
            "sha256": fingerprint(profile.mapping),
            "version": profile.version,
        },
    ]
    prior = {}
    if data.comparative_snapshot_id:
        comparative, comparative_receipt = await intelligence.snapshot(
            db, ctx, eng, data.comparative_snapshot_id, True
        )
        dependencies.append(comparative_receipt)
        prior = {r["code"]: r for r in (await balance(db, ctx, comparative.id))["lines"]}
    current_codes = {r["code"] for r in values["lines"]}
    population = [
        *values["lines"],
        *[
            {**row, "closing": Decimal(0)}
            for code, row in prior.items()
            if code not in current_codes
        ],
    ]
    for line in population:
        assigned = assignments.get(line["code"]) or groups.get(line.get("source_group"))
        if (
            not assigned
            or not assigned.get("statement_group")
            or assigned.get("classification") != line["classification"]
        ):
            raise HTTPException(
                409,
                "Every source account requires consistent approved presentation mapping; unmapped balances are not discarded",
            )
        classification = line["classification"]
        sign = Decimal(-1) if classification in {"Liabilities", "Equity", "Income"} else Decimal(1)
        comparative_amount = prior.get(line["code"], {}).get("closing")
        rows.append(
            {
                "account_id": str(line["id"]),
                "account_code": line["code"],
                "name": line["name"],
                "classification": classification,
                "statement_group": assigned["statement_group"],
                "source_closing_debit_positive": str(line["closing"]),
                "presented_amount": str(
                    line["closing"] if sign == 1 else line["closing"].copy_negate()
                ),
                "comparative_amount": None
                if comparative_amount is None
                else str(comparative_amount if sign == 1 else comparative_amount.copy_negate()),
                "source_snapshot_id": str(snapshot.id),
                "mapping_profile_id": str(profile.id),
            }
        )
    totals, profit, difference = aggregate(rows)
    return await intelligence.append(
        db,
        ctx,
        eng,
        "india-financial-statements",
        {
            "title": f"Schedule III Division {data.division} — source-reconciled statement draft",
            "division": data.division,
            "framework": context["framework"],
            "rows": rows,
            "currency": values["functional_currency"],
            "totals": {k: str(v) for k, v in totals.items()},
            "period_profit": str(profit),
            "balance_sheet_difference_including_unappropriated_profit": str(difference),
            "checks": {
                "source_tb_balanced": values["balanced"],
                "all_accounts_mapped": True,
                "statement_equation_balanced": difference == 0,
            },
            "rationale": data.rationale,
            "review_status": "UNVERIFIED",
            "contributors": [str(ctx.user_id)],
            "limitations": [
                "A source-reconciled draft is not complete statutory financial statements",
                "Cash flow, equity movements, note contents and legally prescribed disclosure completeness require actual reviewed schedules",
                "IFRS measurement is not automatically treated as Ind AS or AS measurement",
            ],
        },
        dependencies,
        request_id,
    )
