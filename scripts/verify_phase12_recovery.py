"""Isolated encrypted local recovery drill; never drops or overwrites a database."""

import asyncio
import hashlib
import json
import subprocess
import tarfile
import time
from pathlib import Path

import asyncpg
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "auditos_phase7_demo"
TARGET = "auditos_phase12_restore_test"
TENANT = "8733db06-81bc-59b3-afcc-bf0f4c0cd8a2"
LOCAL = ROOT / ".local-runtime" / "phase12-recovery"
TOOLS = ROOT / ".local-runtime" / "postgres" / "bin"


async def connection(name):
    return await asyncpg.connect(user="postgres", host="127.0.0.1", port=55432, database=name)


async def fingerprint(conn):
    result = {}
    names = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    for row in names:
        name = row["tablename"]
        quoted = '"' + name.replace('"', '""') + '"'
        # Hash complete rows and sort hashes; includes all tenants and immutable history.
        item = await conn.fetchrow(
            f"SELECT count(*) AS rows, md5(coalesce(string_agg(h,'' ORDER BY h),'')) AS digest FROM (SELECT md5(row_to_json(t)::text) h FROM {quoted} t) q"
        )
        result[name] = dict(item)
    return result


async def main():
    started = time.perf_counter()
    LOCAL.mkdir(parents=True, exist_ok=True)
    source = await connection(SOURCE)
    target = await connection(TARGET)
    assert (
        await source.fetchval("SELECT name FROM tenants WHERE id=$1::uuid", TENANT)
        == "AuditOS Demo Chartered Accountants [SYNTHETIC]"
    )
    if await target.fetchval("SELECT count(*) FROM pg_tables WHERE schemaname='public'"):
        raise RuntimeError("Restore target must be empty; this drill never drops existing data")
    key = Fernet.generate_key()
    (LOCAL / "recovery-key.local").write_bytes(key)
    cipher = Fernet(key)
    dump = LOCAL / "database.dump"
    # Hold the exported snapshot through dump and fingerprint so concurrent changes
    # cannot create a false match or mismatch between the two observations.
    async with source.transaction(isolation="repeatable_read", readonly=True):
        snapshot = await source.fetchval("SELECT pg_export_snapshot()")
        expected = await fingerprint(source)
        await asyncio.to_thread(
            subprocess.run,
            [
                str(TOOLS / "pg_dump.exe"),
                "-h",
                "127.0.0.1",
                "-p",
                "55432",
                "-U",
                "postgres",
                "-Fc",
                "--no-owner",
                "--snapshot=" + snapshot,
                "-f",
                str(dump),
                SOURCE,
            ],
            check=True,
            capture_output=True,
        )
    encrypted = cipher.encrypt(dump.read_bytes())
    (LOCAL / "database.dump.fernet").write_bytes(encrypted)
    dump.unlink()
    # Demonstrate decryption separately from the dump command.
    restored_dump = LOCAL / "restore.dump"
    restored_dump.write_bytes(cipher.decrypt((LOCAL / "database.dump.fernet").read_bytes()))
    restore_start = time.perf_counter()
    await asyncio.to_thread(
        subprocess.run,
        [
            str(TOOLS / "pg_restore.exe"),
            "-h",
            "127.0.0.1",
            "-p",
            "55432",
            "-U",
            "postgres",
            "--role=auditos_phase4_app",
            "--no-owner",
            "--exit-on-error",
            "-d",
            TARGET,
            str(restored_dump),
        ],
        check=True,
        capture_output=True,
    )
    actual = await fingerprint(target)
    database_seconds = time.perf_counter() - restore_start
    restored_dump.unlink()
    if actual != expected:
        raise RuntimeError("Restored database fingerprint differs")
    objects = ROOT / ".private-source-objects" / TENANT
    archive = LOCAL / "objects.tar.gz"
    source_hashes = {
        str(p.relative_to(objects)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in objects.rglob("*")
        if p.is_file()
    }
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(objects, arcname=TENANT)
    (LOCAL / "objects.tar.gz.fernet").write_bytes(cipher.encrypt(archive.read_bytes()))
    archive.unlink()
    archive.write_bytes(cipher.decrypt((LOCAL / "objects.tar.gz.fernet").read_bytes()))
    destination = LOCAL / "restored-objects"
    if destination.exists():
        raise RuntimeError("Restore object destination already exists")
    destination.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(destination, filter="data")
    archive.unlink()
    actual_hashes = {
        str(p.relative_to(destination / TENANT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (destination / TENANT).rglob("*")
        if p.is_file()
    }
    if source_hashes != actual_hashes:
        raise RuntimeError("Restored private object hashes differ")
    result = {
        "status": "PASS",
        "source_database": SOURCE,
        "isolated_target": TARGET,
        "migration": await target.fetchval("SELECT version_num FROM alembic_version"),
        "database_tables": expected,
        "database_restore_and_verify_seconds": database_seconds,
        "private_objects": len(source_hashes),
        "private_object_hashes_equal": True,
        "elapsed_seconds": time.perf_counter() - started,
        "encrypted_database_bytes": len(encrypted),
        "scope": "Synthetic local recovery only; not production PITR, remote retention, or deployment rollback qualification",
    }
    (ROOT / "docs/phase-12/recovery.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    await source.close()
    await target.close()
    print(json.dumps({k: v for k, v in result.items() if k != "database_tables"}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
