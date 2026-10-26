"""Bind SoD calculations to independently reviewed records and exact retained CSV bytes."""

import hashlib
import json
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.modules.audit_execution.models import EvidenceVersion
from app.modules.grc import service
from app.modules.grc.sod_import import parse
from app.modules.lineage.storage import ObjectStore, hash_file
from app.modules.lineage.working_papers import require_current


def implementation_hash():
    digest = hashlib.sha256()
    for name in (
        "schemas.py",
        "sod_import.py",
        "sod_intervals.py",
        "sod_sources.py",
        "operations.py",
    ):
        digest.update(name.encode())
        digest.update(
            (Path(__file__).parent / name)
            .read_text(encoding="utf-8")
            .replace("\r\n", "\n")
            .encode()
        )
    return digest.hexdigest()


async def evidence_receipt(db, ctx, eid, identifier, *, role, limit):
    record = await service.evidence(db, ctx, eid, identifier)
    body_hash = hashlib.sha256(
        json.dumps(
            {"id": str(record.id), "version": record.version, "body": record.body},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    receipt = dict(
        role=role,
        record_id=str(record.id),
        record_version=record.version,
        record_body_sha256=body_hash,
        record_kind=record.kind,
    )
    if record.kind != "evidence":
        return record, receipt, None
    version = await db.scalar(
        select(EvidenceVersion)
        .where(EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.record_id == record.id)
        .order_by(EvidenceVersion.number.desc())
        .limit(1)
    )
    if not version or version.scan_status != "CLEAN":
        raise HTTPException(409, "Current clean independently reviewed SoD source required")

    def read():
        try:
            with ObjectStore().local(version.object_key, version.object_version) as path:
                if path.stat().st_size > limit or hash_file(path) != version.sha256:
                    raise HTTPException(
                        409, "SoD source exceeds its bound or fails original-file integrity"
                    )
                return path.read_bytes()
        except OSError as error:
            raise HTTPException(409, "Original retained SoD file is unavailable") from error

    content = await run_in_threadpool(read)
    receipt.update(
        evidence_version_id=str(version.id), sha256=version.sha256, filename=version.filename
    )
    return record, receipt, content


async def bind(db, ctx, eid, access_record, rule_record, data, rule):
    await require_current(db, ctx, access_record)
    await require_current(db, ctx, rule_record)
    strict = (
        data.period_start is not None
        or data.population_basis == "validity-history"
        or rule.scope_mode == "reviewed-overlap"
    )
    if strict and (
        not data.source_hash
        or data.expected_assignment_count is None
        or data.expected_principal_count is None
        or data.population_control_evidence_id is None
    ):
        raise HTTPException(
            409,
            "Period/reviewed-overlap SoD needs an imported hashed CSV and separate independent population controls",
        )
    source, source_receipt, content = await evidence_receipt(
        db, ctx, eid, data.source_evidence_id, role="access-population", limit=4 * 1024 * 1024
    )
    verified = False
    if data.source_hash:
        if content is None or source_receipt.get("sha256") != data.source_hash:
            raise HTTPException(
                409,
                "SoD population changed or is not the matching retained CSV; re-import and independently review",
            )
        try:
            actual = await run_in_threadpool(parse, content)
        except (ValueError, UnicodeError) as error:
            raise HTTPException(
                422, "SoD source is not a supported exact assignment CSV"
            ) from error
        if actual != [item.model_dump(mode="json") for item in data.assignments]:
            raise HTTPException(
                409,
                "SoD assignments differ from the exact retained CSV; re-import and independently review",
            )
        verified = True
    elif strict:
        raise HTTPException(409, "Historical/overlap SoD must bind its exact retained CSV")
    definition, definition_receipt, _ = await evidence_receipt(
        db,
        ctx,
        eid,
        rule.definition_evidence_id,
        role="definition-and-scope-policy",
        limit=10 * 1024 * 1024,
    )
    records = [access_record, rule_record, source, definition]
    receipts = [source_receipt, definition_receipt]
    if data.population_control_evidence_id is not None:
        if data.population_control_evidence_id == data.source_evidence_id:
            raise HTTPException(
                422, "Independent population controls cannot be the assignment CSV itself"
            )
        control, receipt, _ = await evidence_receipt(
            db,
            ctx,
            eid,
            data.population_control_evidence_id,
            role="independent-population-controls",
            limit=10 * 1024 * 1024,
        )
        records.append(control)
        receipts.append(receipt)
    unique = {record.id: record for record in records}
    return dict(
        source_binding_status="CSV_BYTES_AND_ASSIGNMENTS_VERIFIED"
        if verified
        else "DECLARED_APPROVED_REFERENCE_NOT_CSV_BOUND",
        retained_source_receipts=receipts,
        population_control_status="INDEPENDENT_DECLARED_COUNTS_AGREE"
        if data.expected_assignment_count is not None
        else "NOT_DECLARED",
        expected_assignment_count=data.expected_assignment_count,
        expected_principal_count=data.expected_principal_count,
        population_control_reference=data.population_control_reference,
        coverage_start=data.coverage_start.isoformat() if data.coverage_start else None,
        coverage_end=data.coverage_end.isoformat() if data.coverage_end else None,
        history_scope_assessment=data.history_scope_assessment,
        sod_implementation_sha256=implementation_hash(),
    ), [service.dependency(record) for record in unique.values()]
