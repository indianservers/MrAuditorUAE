import gzip
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.audit_execution import service as audit
from app.modules.lineage.storage import ObjectStore, hash_file
from app.modules.ml.models import MLEvent
from app.modules.saas.storage import put_private


class TrainingCancelled(Exception):
    pass


ROOT = Path(__file__).resolve().parents[4]
_NODE_SLOTS = threading.BoundedSemaphore(2)


async def event(db, ctx, eid, kind, body, parent=None):
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    obj = MLEvent(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eid,
        parent_id=parent,
        kind=kind,
        body=body,
        sha256=hashlib.sha256(payload.encode()).hexdigest(),
    )
    db.add(obj)
    await db.flush()
    return obj


async def get(db, ctx, identifier, kind=None, permission="ml.read"):
    obj = await db.scalar(
        select(MLEvent).where(MLEvent.tenant_id == ctx.tenant_id, MLEvent.id == identifier)
    )
    if not obj:
        raise HTTPException(404, "ML resource not found")
    if obj.kind.startswith("dmtt_"):
        raise HTTPException(404, "ML resource not found")
    await audit.engagement(db, ctx, obj.engagement_id, permission, lock=False)
    if kind and obj.kind != kind:
        raise HTTPException(422, "Unexpected ML resource type")
    return obj


def put_json(tenant, data):
    content = gzip.compress(json.dumps(data, separators=(",", ":")).encode(), mtime=0)
    meta = ObjectStore().put(str(tenant), io.BytesIO(content))
    return {**meta, "encoding": "gzip-json", "uncompressed_limit": 750000000}


async def put_dataset(db, ctx, data):
    content = gzip.compress(json.dumps(data, separators=(",", ":")).encode(), mtime=0)
    meta = await put_private(db, ctx, io.BytesIO(content))
    return {**meta, "encoding": "gzip-json", "uncompressed_limit": 750000000}


def read_object(meta):
    with ObjectStore().local(meta["object_key"], meta["object_version"]) as path:
        if hash_file(path) != meta["sha256"]:
            raise ValueError("Private artifact integrity failed")
        if meta.get("encoding") == "gzip-json":
            with gzip.open(path, "rb") as stream:
                content = stream.read(750000001)
                if len(content) > 750000000:
                    raise ValueError("Dataset expanded size limit")
                return content
        return path.read_bytes()


def node(operation, dataset=None, config=None, model=None, rows=None, job_id=None):
    if not _NODE_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "Local ML worker capacity reached; retry the queued operation")
    try:
        return _node(operation, dataset, config, model, rows, job_id)
    finally:
        _NODE_SLOTS.release()


def _node(operation, dataset=None, config=None, model=None, rows=None, job_id=None):
    """Only server-created files/topology; no uploaded JS, paths or arbitrary models."""
    with tempfile.TemporaryDirectory(prefix="auditos-ml-") as directory:
        root = Path(directory)
        artifacts = root / "artifacts"
        artifacts.mkdir()
        if model:
            for name in ("model.json", "weights.bin", "metadata.json"):
                if name not in model:
                    raise ValueError("ML_MODEL_UNAVAILABLE: required model artifact is missing")
                try:
                    (artifacts / name).write_bytes(read_object(model[name]))
                except (OSError, ValueError):
                    raise ValueError("ML_ARTIFACT_INVALID: private model artifact is absent or corrupt") from None
        if operation == "infer" and not model:
            raise ValueError("ML_MODEL_UNAVAILABLE: inference requires explicit trained artifacts")
        runtime = shutil.which("node")
        worker = ROOT / "ml-engine/dist/src/worker.js"
        if not runtime or not worker.is_file():
            raise ValueError("ML_RUNTIME_UNAVAILABLE: build the local Node CPU worker")
        request = {
            "operation": operation,
            "artifact_dir": str(artifacts),
            "config": config,
            "rows": rows,
        }
        if dataset:
            (root / "dataset.json").write_bytes(read_object(dataset))
            request["dataset"] = str(root / "dataset.json")
        (root / "request.json").write_text(json.dumps(request))
        # Wall timeout and V8 heap cap are independent of request parameters.
        from redis import Redis

        from app.core.config import settings

        redis = Redis.from_url(settings().redis_url)
        started = time.monotonic()
        process = subprocess.Popen(
            [
                runtime,
                "--max-old-space-size=1536",
                str(worker),
                str(root / "request.json"),
                str(root / "result.json"),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            while process.poll() is None:
                if job_id:
                    progress = root / "result.json.progress"
                    if progress.exists():
                        redis.setex(
                            "ml-progress:" + str(job_id), 3600, progress.read_bytes()[-100000:]
                        )
                    if redis.get("ml-cancel:" + str(job_id)):
                        raise TrainingCancelled("Training cancelled by requesting user")
                if time.monotonic() - started > 900:
                    raise TimeoutError("ML worker exceeded wall-clock limit")
                time.sleep(0.2)
            if process.returncode:
                category = "ML_INFERENCE_FAILED"
                error_path = root / "result.json"
                if error_path.is_file() and error_path.stat().st_size < 4096:
                    reported = json.loads(error_path.read_text()).get("error_category")
                    if reported in {"ML_ARTIFACT_INVALID", "ML_INPUT_INVALID", "ML_INFERENCE_FAILED"}:
                        category = reported
                raise ValueError(category + ": local worker failed; no baseline or mock was substituted")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            redis.close()
        result = json.loads((root / "result.json").read_text())
        files = (
            {
                name: (artifacts / name).read_bytes()
                for name in ("model.json", "weights.bin", "metadata.json")
            }
            if operation == "train"
            else {}
        )
        return result, files


async def execute_job(db, ctx, payload, job_id=None):
    from starlette.concurrency import run_in_threadpool

    if payload["operation"] == "dataset":
        from app.modules.accounting.models import Account, ImportBatch, ImportSnapshot, JournalLine
        from app.modules.lineage.freshness import mapping_receipt

        eng = await audit.engagement(db, ctx, uuid.UUID(payload["engagement_id"]), "ml.train", True)
        rows = (
            await db.execute(
                select(JournalLine, Account.name)
                .join(Account, Account.id == JournalLine.account_id)
                .join(ImportBatch, ImportBatch.id == JournalLine.batch_id)
                .where(
                    JournalLine.tenant_id == ctx.tenant_id,
                    JournalLine.entity_id == eng.entity_id,
                    JournalLine.period_id == eng.period_id,
                    ImportBatch.status == "active",
                )
                .order_by(JournalLine.posting_date, JournalLine.journal_id, JournalLine.id)
                .limit(250001)
            )
        ).all()
        if not rows or len(rows) > 250000:
            raise HTTPException(
                422, "Dataset requires 1–250000 journal lines; partition larger periods"
            )
        data = []
        for row, name in rows:
            data.append(
                {
                    "id": str(row.id),
                    "journal": str(row.journal_id),
                    "client": str(row.client_id),
                    "date": str(row.posting_date),
                    "debit": float(row.base_debit),
                    "credit": float(row.base_credit),
                    "currency": row.currency,
                    "functional_currency": row.functional_currency,
                    "description": row.description,
                    "account": str(row.account_id),
                    "account_name": name,
                    "counterparty": row.counterparty,
                    **({"manual": row.attributes["manual"]} if isinstance(row.attributes.get("manual"), bool) else {}),
                    "label_kind": "unknown",
                    "snapshot_id": str(row.snapshot_id),
                }
            )
        journals = sorted(
            {x["journal"] for x in data}, key=lambda j: hashlib.sha256(j.encode()).hexdigest()
        )
        splits = {
            j: "train"
            if i < len(journals) * 0.6
            else "validation"
            if i < len(journals) * 0.8
            else "test"
            for i, j in enumerate(journals)
        }
        meta = await put_dataset(
            db,
            ctx,
            {"rows": data, "split": [splits[x["journal"]] for x in data], "synthetic": False},
        )
        obj = await event(
            db,
            ctx,
            eng.id,
            "dataset",
            {
                "object": meta,
                "synthetic": False,
                "total_rows": len(data),
                "source_snapshots": [
                    {"id": str(s.id), "sha256": s.sha256}
                    for s in (
                        await db.scalars(
                            select(ImportSnapshot).where(
                                ImportSnapshot.tenant_id == ctx.tenant_id,
                                ImportSnapshot.id.in_({row.snapshot_id for row, _ in rows}),
                            )
                        )
                    ).all()
                ],
                "account_mapping_receipt": await mapping_receipt(db, ctx.tenant_id, eng.entity_id),
                "labels": {"unknown": len(data)},
                "training_eligible": False,
                "scope": "Single authorized entity/period; journal-grouped hash split. Curated reviewed labels required before fitting.",
            },
        )
        return {"id": str(obj.id), "status": "completed"}

    source = await get(
        db,
        ctx,
        uuid.UUID(payload["source_id"]),
        permission="ml.train" if payload["operation"] == "train" else "ml.score",
    )
    if payload["operation"] == "baseline":
        from app.modules.lineage.freshness import require_ml_current
        from app.modules.ml.baselines import predict

        if source.kind != "dataset":
            raise HTTPException(422, "A current versioned dataset is required for baseline execution")
        await require_ml_current(db, ctx, source)
        data = json.loads(await run_in_threadpool(read_object, source.body["object"]))
        start, size = payload.get("offset", 0), payload.get("limit", 1000)
        result = await run_in_threadpool(predict, data["rows"][start:start + size], payload["mode"])
        eng = await audit.engagement(db, ctx, source.engagement_id, "ml.score", True)
        await require_ml_current(db, ctx, source)
        obj = await event(db, ctx, eng.id, "inference", {
            **result, "model_id": None, "dataset_id": str(source.id),
            "entity_id": str(eng.entity_id), "period_id": str(eng.period_id),
            "source_snapshots": source.body.get("source_snapshots", []),
            "snapshot": source.sha256, "offset": start,
            "language_model_dependency": False,
        }, source.id)
        return {"id": str(obj.id), "status": "completed", "execution_mode": result["execution_mode"]}
    if payload["operation"] == "train":
        if source.kind != "dataset":
            raise HTTPException(422, "Versioned dataset required")
        if source.body.get("training_eligible") is False:
            raise HTTPException(409, "Reviewed training labels are required before fitting a local model")
        from app.modules.lineage.freshness import require_ml_current

        await require_ml_current(db, ctx, source)
        result, files = await run_in_threadpool(
            node, "train", source.body["object"], payload["config"], None, None, job_id
        )
        await audit.engagement(db, ctx, source.engagement_id, "ml.train", True)
        await require_ml_current(db, ctx, source)
        artifacts = {
            name: await put_private(db, ctx, io.BytesIO(content)) for name, content in files.items()
        }
        result.pop("baseline_sample", None)
        obj = await event(
            db,
            ctx,
            source.engagement_id,
            "model",
            {
                "metrics": result,
                "artifacts": artifacts,
                "lifecycle": "EVALUATED",
                "scope": "TENANT_SYNTHETIC" if source.body["synthetic"] else "TENANT",
                "production_validated": False,
            },
            source.id,
        )
    else:
        if source.kind != "deployment":
            raise HTTPException(422, "Approved deployment required")
        latest = await db.scalar(
            select(MLEvent)
            .where(
                MLEvent.tenant_id == ctx.tenant_id,
                MLEvent.engagement_id == source.engagement_id,
                MLEvent.kind == "deployment",
                MLEvent.body["family"].astext == source.body.get("family"),
            )
            .order_by(MLEvent.created_at.desc(), MLEvent.id.desc())
            .limit(1)
        )
        if not latest or latest.id != source.id:
            raise HTTPException(409, "Deployment superseded; choose current version")
        model = await get(db, ctx, uuid.UUID(source.body["model_id"]), "model")
        dataset = await get(db, ctx, uuid.UUID(payload["dataset_id"]), "dataset")
        from app.modules.lineage.freshness import require_ml_current

        await require_ml_current(db, ctx, model)
        await require_ml_current(db, ctx, dataset)
        if dataset.engagement_id != source.engagement_id:
            raise HTTPException(422, "Same engagement scoring dataset required")
        data = json.loads(await run_in_threadpool(read_object, dataset.body["object"]))
        start, size = payload.get("offset", 0), payload.get("limit", 1000)
        rows = data["rows"][start : start + size]
        if not rows:
            raise HTTPException(422, "Empty inference batch")
        result, _ = await run_in_threadpool(
            node, "infer", None, None, model.body["artifacts"], rows
        )
        # Immutable source reads do not hold an engagement lock through Node inference.
        # Reauthorize and serialize publication, checking deployment supersession again.
        eng = await audit.engagement(db, ctx, source.engagement_id, "ml.score", True)
        await require_ml_current(db, ctx, model)
        await require_ml_current(db, ctx, dataset)
        current = await db.scalar(
            select(MLEvent.id)
            .where(
                MLEvent.tenant_id == ctx.tenant_id,
                MLEvent.engagement_id == source.engagement_id,
                MLEvent.kind == "deployment",
                MLEvent.body["family"].astext == source.body.get("family"),
            )
            .order_by(MLEvent.created_at.desc(), MLEvent.id.desc())
            .limit(1)
        )
        if current != source.id:
            raise HTTPException(409, "Deployment changed during inference; rerun current model")
        obj = await event(
            db,
            ctx,
            source.engagement_id,
            "inference",
            {
                "model_id": str(model.id),
                "dataset_id": str(dataset.id),
                "snapshot": dataset.sha256,
                "offset": start,
                **result,
                "entity_id": str(eng.entity_id), "period_id": str(eng.period_id),
                "source_snapshots": dataset.body.get("source_snapshots", []),
                "language_model_dependency": False,
            },
            source.id,
        )
    return {"id": str(obj.id), "status": "completed", "execution_mode": "trained_model"}
