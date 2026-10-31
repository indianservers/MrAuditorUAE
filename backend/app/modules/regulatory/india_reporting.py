"""Source-reconciled Indian statement drafts; no implicit IFRS/Ind AS equivalence."""

from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.accounting.models import MappingProfile
from app.modules.intelligence import service as intelligence
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.workspace import resolved
from app.modules.lineage.freshness import mapping_receipt
from app.modules.reconciliation.service import balance

CONTRACT = "india-source-statements/2"


def implementation_hash():
    return sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_reporting_selection(items, division, framework):
    divisions = {
        item.get("facts", {}).get("schedule_iii_division")
        for item in items
        if item.get("facts", {}).get("schedule_iii_division") is not None
    }
    if divisions != {division}:
        raise HTTPException(
            409,
            "Retain one consistent reviewed Schedule III division across the applicability checklist",
        )
    if (framework == "AS") != (division == "I"):
        raise HTTPException(
            422,
            "Division/framework selection is inconsistent; independently assess entity applicability",
        )
    if framework == "Ind AS":
        flags = [item.get("facts", {})["nbfc"] for item in items if "nbfc" in item.get("facts", {})]
        expected = division == "III"
        if not flags or any(value is not expected for value in flags):
            raise HTTPException(
                409,
                "Retain consistent explicit NBFC facts: Division III for an assessed Ind AS NBFC, Division II for an assessed non-NBFC",
            )


def presentation_rows(current, prior, assignments, groups, snapshot_id, comparative_id):
    current_codes = {r["code"] for r in current}
    population = [
        *current,
        *[
            {**row, "closing": Decimal(0)}
            for code, row in prior.items()
            if code not in current_codes
        ],
    ]
    rows = []
    for line in population:
        assigned = assignments.get(line["code"]) or groups.get(line.get("source_group"))
        classification = line["classification"]
        if (
            classification not in {"Assets", "Liabilities", "Equity", "Income", "Expenses"}
            or not assigned
            or not str(assigned.get("statement_group", "")).strip()
            or assigned.get("classification") != classification
        ):
            raise HTTPException(
                409,
                "Every source account requires consistent approved presentation mapping; unmapped balances are not discarded",
            )
        comparative = prior.get(line["code"])
        if comparative and comparative["classification"] != classification:
            raise HTTPException(
                409,
                "Comparative classification differs; retain an independently assessed restatement instead of silently reclassifying",
            )
        negate = classification in {"Liabilities", "Equity", "Income"}
        prior_amount = comparative["closing"] if comparative else None
        rows.append(
            {
                "account_id": str(line["id"]),
                "account_code": line["code"],
                "name": line["name"],
                "classification": classification,
                "statement_group": assigned["statement_group"],
                "source_closing_debit_positive": str(line["closing"]),
                "presented_amount": str(
                    line["closing"].copy_negate() if negate else line["closing"]
                ),
                "comparative_amount": None
                if prior_amount is None
                else str(prior_amount.copy_negate() if negate else prior_amount),
                "source_snapshot_id": str(snapshot_id) if line["code"] in current_codes else None,
                "comparative_source_snapshot_id": str(comparative_id) if comparative else None,
                "current_account_in_source": line["code"] in current_codes,
                "comparative_account_in_source": comparative is not None,
            }
        )
    return rows


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
    require_reporting_selection(applicability.body["items"], data.division, context["framework"])
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
    prior_checks = None
    if data.comparative_snapshot_id:
        comparative, comparative_receipt = await intelligence.snapshot(
            db, ctx, eng, data.comparative_snapshot_id, True
        )
        dependencies.append(comparative_receipt)
        previous = await balance(db, ctx, comparative.id)
        if (
            not previous["balanced"]
            or previous["functional_currency"] != values["functional_currency"]
        ):
            raise HTTPException(
                409, "Comparative trial balance must balance in the same reporting currency"
            )
        prior = {r["code"]: r for r in previous["lines"]}
        prior_checks = {"source_tb_balanced": True, "source_snapshot_id": str(comparative.id)}
    rows = presentation_rows(
        values["lines"], prior, assignments, groups, snapshot.id, data.comparative_snapshot_id
    )
    for row in rows:
        row["mapping_profile_id"] = str(profile.id)
    totals, profit, difference = aggregate(rows)
    if difference != 0:
        raise HTTPException(409, "Presented current statement equation does not balance")
    comparative_totals = comparative_profit = None
    if data.comparative_snapshot_id:
        comparative_totals, comparative_profit, comparative_difference = aggregate(
            [
                {**row, "presented_amount": row["comparative_amount"]}
                for row in rows
                if row["comparative_account_in_source"]
            ]
        )
        if comparative_difference != 0:
            raise HTTPException(409, "Presented comparative statement equation does not balance")
        assert prior_checks is not None
        prior_checks["statement_equation_balanced"] = True
    return await intelligence.append(
        db,
        ctx,
        eng,
        "india-financial-statements",
        {
            "title": f"Schedule III Division {data.division} — source-reconciled statement draft",
            "division": data.division,
            "contract": CONTRACT,
            "implementation_sha256": implementation_hash(),
            "framework": context["framework"],
            "rows": rows,
            "currency": values["functional_currency"],
            "totals": {k: str(v) for k, v in totals.items()},
            "period_profit": str(profit),
            "comparative_totals": {k: str(v) for k, v in comparative_totals.items()}
            if comparative_totals is not None
            else None,
            "comparative_period_profit": str(comparative_profit)
            if comparative_profit is not None
            else None,
            "comparative_checks": prior_checks,
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
