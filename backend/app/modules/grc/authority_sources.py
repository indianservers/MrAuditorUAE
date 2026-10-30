"""Exact original authority bytes, reused by country procedure profiles."""


async def verify_original_sources(db, ctx, checked, authority, sources, extension_id=None):
    from fastapi import HTTPException
    from sqlalchemy import select

    from app.modules.audit_execution.models import EvidenceVersion
    from app.modules.lineage.storage import ObjectStore, hash_file

    if extension_id and checked[str(extension_id)].kind != "evidence":
        raise HTTPException(
            422, f"{authority} deadline extensions require original retained authority evidence"
        )
    for identifier, digest in sources:
        if checked[str(identifier)].kind != "evidence":
            raise HTTPException(
                422, f"{authority} profile requires original regulation and guideline evidence"
            )
        version = await db.scalar(
            select(EvidenceVersion)
            .where(
                EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.record_id == identifier
            )
            .order_by(EvidenceVersion.number.desc())
            .limit(1)
        )
        if (
            not version
            or version.scan_status != "CLEAN"
            or version.sha256 != digest
            or version.media_type != "application/pdf"
        ):
            raise HTTPException(
                409,
                f"Select the exact retained original PDFs for the adopted {authority} profile version",
            )
        try:
            with ObjectStore().local(version.object_key, version.object_version) as path:
                if path.stat().st_size != version.size or hash_file(path) != digest:
                    raise HTTPException(
                        409, f"Retained {authority} source bytes do not match the adopted profile"
                    )
        except (OSError, ValueError) as error:
            raise HTTPException(
                409, f"Retained {authority} source bytes are unavailable"
            ) from error
