from fastapi import HTTPException
from sqlalchemy import select

from app.db.models.platform import LegalEntity
from app.modules.jurisdictions.models import EngagementJurisdiction
from app.modules.jurisdictions.packages import fingerprint, package


async def pin(db, ctx, engagement):
    entity = await db.get(LegalEntity, engagement.entity_id)
    manifest = package(entity.country)
    binding = EngagementJurisdiction(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=engagement.id,
        country=entity.country,
        package_version=manifest["version"],
        package_sha256=fingerprint(manifest),
        manifest=manifest,
    )
    db.add(binding)
    await db.flush()
    return binding


async def original_binding(db, ctx, engagement):
    row = await db.scalar(
        select(EngagementJurisdiction).where(
            EngagementJurisdiction.tenant_id == ctx.tenant_id,
            EngagementJurisdiction.engagement_id == engagement.id,
        )
    )
    if not row:
        raise HTTPException(
            409, "Engagement country package missing; apply migration or reviewed repair"
        )
    return row


async def binding(db, ctx, engagement):
    from app.modules.jurisdictions.workspace import resolved

    return (await resolved(db, ctx, engagement))[0]


async def require_capability(db, ctx, engagement, permission):
    # Core audit and IFRS profile selection remain global. UAE engines never become another country's tax engine.
    prefix = permission.split(".")[0]
    if prefix not in {"tax", "vat", "tp", "dmtt", "einvoice"}:
        return
    row = await binding(db, ctx, engagement)
    capability = {
        "tax": "uae-corporate-tax",
        "vat": "uae-vat",
        "einvoice": "uae-vat",
        "tp": "uae-tp",
        "dmtt": "uae-dmtt",
    }[prefix]
    if capability not in row.manifest.get("capabilities", []):
        raise HTTPException(
            409,
            "This country's regulatory engine is not implemented; shared audit workflows remain available",
        )
