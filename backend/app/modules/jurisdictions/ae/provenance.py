"""Private original-file provenance indicators, not an authenticity verdict."""

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.audit_execution.models import AuditRecord, EvidenceVersion
from app.modules.enterprise_ai.security import digest


async def corpus(db, ctx, eid):
    from app.modules.audit_execution.service import get_record

    records = (
        await db.scalars(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind == "evidence",
                AuditRecord.status != "ARCHIVED",
            )
            .order_by(AuditRecord.id)
            .limit(1001)
        )
    ).all()
    if len(records) > 1000:
        raise HTTPException(422, "Evidence corpus exceeds bounded 1000-record provenance scan")
    out = []
    for record in records:
        try:
            await get_record(db, ctx, eid, record.id, lock=False)
        except HTTPException as exc:
            if exc.status_code in {403, 404}:
                continue
            raise
        latest = await db.scalar(
            select(EvidenceVersion)
            .where(
                EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.record_id == record.id
            )
            .order_by(EvidenceVersion.number.desc())
            .limit(1)
        )
        if latest:
            out.append(
                dict(
                    record_id=str(record.id),
                    record_version=record.version,
                    version_id=str(latest.id),
                    number=latest.number,
                    sha256=latest.sha256,
                    reference=record.reference,
                    scan_status=latest.scan_status,
                )
            )
    return out


async def assess(db, ctx, eid, rid):
    from app.modules.enterprise_ai.documents import latest_evidence
    from app.modules.lineage.storage import ObjectStore, hash_file

    proof, version = await latest_evidence(db, ctx, eid, rid)
    if proof.kind != "evidence":
        raise HTTPException(422, "Select approved original evidence")
    with ObjectStore().local(version.object_key, version.object_version) as path:
        observed = hash_file(path)
    candidates = await corpus(db, ctx, eid)
    duplicates = [
        row for row in candidates if row["record_id"] != str(rid) and row["sha256"] == observed
    ]
    output = dict(
        engine="original-evidence-provenance/1",
        record_id=str(rid),
        evidence_version_id=str(version.id),
        registered_sha256=version.sha256,
        observed_sha256=observed,
        matches_registered_hash=observed == version.sha256,
        duplicate_candidates=duplicates,
        source_filename=version.filename,
        media_type=version.media_type,
        registered_size=version.size,
        population_sha256=digest(candidates),
        analysis_mode="rules_baseline",
        local_ml_mode="unavailable",
        language_mode="unavailable",
        forgery_conclusion=None,
        digital_signature_verified=False,
        scan_did_not_modify_object=True,
        limitations=[
            "Duplicate bytes can be legitimate copies",
            "Metadata and hash indicators do not authenticate a document or signature",
            "No forensic image manipulation or semantic forgery detector",
        ],
    )
    deps = [
        {"type": "record", "id": str(proof.id), "version": proof.version},
        {
            "type": "evidence",
            "id": str(version.id),
            "record_id": str(proof.id),
            "number": version.number,
            "sha256": version.sha256,
        },
    ]
    return output, deps
