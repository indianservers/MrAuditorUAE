import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx

from app.core.dependencies import Context
from app.core.security import access_token
from app.db.session import Session, engine, tenant_context
from app.main import app
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.ml import service

ROOT = Path(__file__).resolve().parents[1]


async def main():
    m = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text())
    runs = json.loads((ROOT / "docs/phase-9/training-results.json").read_text())
    dataset = json.loads((ROOT / "docs/phase-9/demo-dataset.json").read_text())
    async with Session() as db, db.begin():
        await guard(db)

    def h(i):
        return {
            "Authorization": "Bearer " + access_token(m["users"][i]["id"]),
            "X-Tenant-ID": str(DEMO_TENANT),
        }

    decision = {
        "rationale": "Synthetic independent review of measured held-out results, baselines, artifact reproducibility and limitations",
        "experimental_use_acknowledged": True,
    }
    report = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        for run in runs:
            mid = run["id"]
            for suffix, who in [
                ("approval-requests", 1),
                ("approvals", 3),
                ("deployments", 3),
            ]:
                r = await c.post(
                    f"/api/v1/ml/models/{mid}/{suffix}", headers=h(who), json=decision
                )
                assert r.status_code == 201, r.text
            deployment = r.json()["id"]
            async with Session() as db, db.begin():
                await tenant_context(db, str(DEMO_TENANT))
                ctx = Context(uuid.UUID(m["users"][1]["id"]), DEMO_TENANT, frozenset())
                result = await service.execute_job(
                    db,
                    ctx,
                    {
                        "operation": "infer",
                        "source_id": deployment,
                        "dataset_id": dataset["dataset_id"],
                        "offset": 260824,
                        "limit": 1000,
                    },
                )
            r = await c.get("/api/v1/ml/events/" + result["id"], headers=h(1))
            assert r.status_code == 200, r.text
            body = r.json()["body"]
            assert len(body["predictions"]) == 1000
            assert not body["calibrated_probability"]
            report.append(
                {
                    "family": run["family"],
                    "model_id": mid,
                    "deployment_id": deployment,
                    "inference_id": result["id"],
                    "predictions": len(body["predictions"]),
                    "reload_max_delta": run["metrics"]["reload_max_delta"],
                    "drift_features": len(body["drift"]),
                }
            )
        # Explicit rollback to first approved version and immutable deployment history.
        r = await c.post(
            f"/api/v1/ml/models/{runs[0]['id']}/deployments",
            headers=h(3),
            json={
                **decision,
                "rationale": "Synthetic rollback to earlier independently approved autoencoder version",
            },
        )
        assert r.status_code == 201, r.text
        for i in [6, 18]:
            r = await c.get(
                f"/api/v1/ml/events?eid={dataset['engagement_id']}", headers=h(i)
            )
            assert r.status_code == 403, r.text
    (ROOT / "docs/phase-9/inference-verification.json").write_text(
        json.dumps(
            {
                "families": report,
                "rollback_model_id": runs[0]["id"],
                "auditor_internal_denied": True,
                "client_internal_denied": True,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(report))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
