import asyncio
import datetime
import hashlib
import json
import subprocess
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/qa-campaign"
LOCAL = ROOT / ".local-runtime/qa-campaign"


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    LOCAL.mkdir(parents=True, exist_ok=True)
    c = await asyncpg.connect(
        user="postgres", host="127.0.0.1", port=55432, database="postgres"
    )
    names = [
        r["datname"]
        for r in await c.fetch(
            "SELECT datname FROM pg_database WHERE datistemplate=false"
        )
    ]
    result = {
        "time": datetime.datetime.now(datetime.UTC).isoformat(),
        "host": "127.0.0.1",
        "port": 55432,
        "databases": names,
        "existing_assessment": [],
        "isolation": "fresh dedicated auditos_qa_campaign_demo; regression uses separate auditos_qa_campaign_test",
    }
    for name in names:
        if name.startswith("auditos_"):
            d = await asyncpg.connect(
                user="postgres", host="127.0.0.1", port=55432, database=name
            )
            tables = await d.fetchval(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
            )
            item = {"database": name, "tables": tables}
            if await d.fetchval("SELECT to_regclass('public.tenants') IS NOT NULL"):
                item["tenants"] = [
                    dict(r)
                    for r in await d.fetch("SELECT id::text,name,status FROM tenants")
                ]
                item["clients"] = await d.fetchval("SELECT count(*) FROM clients")
                item["journal_lines"] = await d.fetchval(
                    "SELECT count(*) FROM journal_lines"
                )
            result["existing_assessment"].append(item)
            await d.close()
    for name in ["auditos_qa_campaign_demo", "auditos_qa_campaign_test"]:
        if name in names:
            raise RuntimeError(
                "Campaign database already exists: inspect before reusing"
            )
    # Back up existing demo before any campaign database creation; never modify it.
    dump = LOCAL / "pre-campaign-demo.dump"
    await asyncio.to_thread(
        subprocess.run,
        [
            str(ROOT / ".local-runtime/postgres/bin/pg_dump.exe"),
            "-h",
            "127.0.0.1",
            "-p",
            "55432",
            "-U",
            "postgres",
            "-Fc",
            "--no-owner",
            "-f",
            str(dump),
            "auditos_phase7_demo",
        ],
        check=True,
        capture_output=True,
    )
    result["backup"] = {
        "path": str(dump.relative_to(ROOT)),
        "bytes": dump.stat().st_size,
        "sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
    }
    for name in ["auditos_qa_campaign_demo", "auditos_qa_campaign_test"]:
        await c.execute("CREATE DATABASE " + name + " OWNER auditos_phase4_app")
    result["created_databases"] = [
        "auditos_qa_campaign_demo",
        "auditos_qa_campaign_test",
    ]
    (OUT / "database-assessment.json").write_text(
        json.dumps(result, indent=2), encoding="utf8"
    )
    await c.close()
    print(
        json.dumps(
            {
                "assessment_databases": len(result["existing_assessment"]),
                "created": result["created_databases"],
                "backup_bytes": result["backup"]["bytes"],
            }
        )
    )


asyncio.run(main())
