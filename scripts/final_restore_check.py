"""Restore only the explicitly named synthetic database into a new isolated database."""

import asyncio
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "auditos_final_verification_test"
TARGET = "auditos_final_restore_test_" + datetime.now(UTC).strftime("%Y%m%d%H%M%S")
BIN = ROOT / ".local-runtime/postgres/bin"
FOLDER = ROOT / ".local-runtime/final-verification" / TARGET
FOLDER.mkdir(parents=True, exist_ok=False)


async def counts(name):
    db = await asyncpg.connect(user="postgres", host="127.0.0.1", port=55432, database=name)
    try:
        names = await db.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        return {row["tablename"]: await db.fetchval('SELECT count(*) FROM public."' + row["tablename"].replace('"', '""') + '"') for row in names}
    finally:
        await db.close()


async def main():
    before = await counts(SOURCE)
    dump = FOLDER / "synthetic.dump"
    subprocess.run([str(BIN / "pg_dump.exe"), "-h", "127.0.0.1", "-p", "55432", "-U", "postgres", "-d", SOURCE,
        "--format=custom", "--no-owner", "--no-acl", "-f", str(dump)], check=True, capture_output=True)
    admin = await asyncpg.connect(user="postgres", host="127.0.0.1", port=55432, database="postgres")
    try:
        # TARGET is a fixed prefix plus numeric timestamp, never supplied or reused.
        await admin.execute('CREATE DATABASE "' + TARGET + '" OWNER auditos_phase4_app')
    finally:
        await admin.close()
    subprocess.run([str(BIN / "pg_restore.exe"), "-h", "127.0.0.1", "-p", "55432", "-U", "postgres", "-d", TARGET,
        "--no-owner", "--no-acl", "--exit-on-error", str(dump)], check=True, capture_output=True)
    after = await counts(TARGET)
    assert before == after, "Restored table counts differ"
    original = ROOT / ".local-runtime/final-verification/objects"
    restored = FOLDER / "restored-objects"
    shutil.copytree(original, restored)
    objects = {}
    for path in original.rglob("*"):
        if path.is_file():
            relative = path.relative_to(original)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert hashlib.sha256((restored / relative).read_bytes()).hexdigest() == digest
            objects[str(relative)] = digest
    result = {"synthetic": True, "source_database": SOURCE, "restored_database": TARGET,
        "table_counts_equal": before == after, "tables": before, "object_count": len(objects),
        "all_copied_object_hashes_equal": True, "dump_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
        "limitations": ["Single-host synthetic restore; not production RPO/RTO qualification", "No live credentials or provider reauthorization tested", "Production encryption keys require separately protected backup"]}
    (ROOT / "docs/engine-strengthening/phase5/restore-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"tables_verified": len(before), "objects_verified": len(objects), "destination": TARGET}))


asyncio.run(main())
