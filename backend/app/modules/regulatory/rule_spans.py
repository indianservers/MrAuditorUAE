"""Selection over a complete interval, including short-lived interior amendments."""

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.modules.regulatory.models import RuleAction, RuleVersion
from app.modules.regulatory.schemas import Rule


def boundaries(start, end, rules):
    points = {start}
    for rule in rules:
        if start < rule.effective_from <= end:
            points.add(rule.effective_from)
        if rule.effective_to and start <= rule.effective_to < end:
            points.add(rule.effective_to + timedelta(days=1))
    return sorted(points)


async def selection_over_span(db, ctx, key, period_start, period_end, start, end):
    from app.modules.regulatory.service import selection

    if end < start:
        raise HTTPException(422, "Rule selection span dates must be ordered")
    versions = (
        await db.scalars(
            select(RuleVersion)
            .join(RuleAction, RuleAction.version_id == RuleVersion.id)
            .where(
                RuleVersion.tenant_id == ctx.tenant_id,
                RuleVersion.rule_key == key,
                RuleAction.state == "PUBLISHED",
                RuleVersion.body["effective_from"].astext <= end.isoformat(),
                or_(
                    RuleVersion.body["effective_to"].astext.is_(None),
                    RuleVersion.body["effective_to"].astext >= start.isoformat(),
                ),
            )
            .order_by(RuleVersion.version.desc())
            .limit(1001)
        )
    ).all()
    if len(versions) > 1000:
        raise HTTPException(
            409, "Rule interval history exceeds one thousand overlapping published versions"
        )
    profiles = [Rule.model_validate(version.body) for version in versions]
    first = None
    for point in boundaries(start, end, profiles):
        current = await selection(db, ctx, key, period_start, period_end, point)
        if current is not None and current.body.get("period_basis") != "transaction_date":
            raise HTTPException(
                409, "Whole-month profile selection requires transaction-date rules"
            )
        if current is None or (first is not None and current.id != first.id):
            return None
        first = current
    return first
