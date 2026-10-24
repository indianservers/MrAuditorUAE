"""Bind imported judgments to approved native engagement parameters."""

import uuid
from decimal import Decimal

from fastapi import HTTPException


async def validate_parameters(db, ctx, eid, data):
    if data.use_case_id != 149:
        return
    from app.db.models.platform import Engagement, LegalEntity
    from app.modules.enterprise_ai.security import source

    eng = await db.get(Engagement, eid)
    entity = await db.get(LegalEntity, eng.entity_id)
    if data.currency != entity.functional_currency:
        raise HTTPException(
            422,
            "Misstatement aggregation must use the engagement functional currency; approved conversion is required first",
        )
    for row in data.rows:
        parameter = await source(db, ctx, eid, uuid.UUID(row["parameter_source_id"]))
        if parameter.kind != "materiality" or not parameter.body.get("calculation"):
            raise HTTPException(
                422, "Select the engagement's independently approved materiality record"
            )
        approved = parameter.body["calculation"]
        if Decimal(row["materiality"]) != Decimal(approved["overall"]) or Decimal(
            row["trivial_threshold"]
        ) != Decimal(approved["clearly_trivial"]):
            raise HTTPException(
                422,
                "Misstatement thresholds differ from the approved engagement materiality parameters",
            )
