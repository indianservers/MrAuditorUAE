"""Scoped direct API sync: preserve evidence, validate finances, then stage imports."""

import csv
import io
import tempfile
import uuid
from collections import defaultdict
from decimal import Decimal, localcontext

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import Context
from app.modules.accounting.models import Connection, SyncRun
from app.modules.accounting.schemas import ImportOptions
from app.modules.accounting.service import check_scope, scope_values, scoped, upload
from app.modules.audit_log.service import record
from app.modules.connectors.native_adapters import NativeAdapter
from app.modules.connectors.native_config import NATIVE_PROVIDERS
from app.modules.connectors.runtime import ConnectorRuntime, digest
from app.modules.connectors.secrets import decrypt, encrypt
from app.modules.connectors.zoho import ConnectorError
from app.modules.ingestion.parser import normalize
from app.modules.saas.storage import put_private

COLUMNS = [
    "account_code",
    "account_name",
    "source_id",
    "source_group",
    "parent_code",
    "journal_ref",
    "posting_date",
    "debit",
    "credit",
    "currency",
    "exchange_rate",
    "base_debit",
    "base_credit",
    "opening_balance",
    "closing_balance",
    "opening",
    "description",
    "counterparty",
    "tax_code",
    "cost_center",
    "department",
    "project",
    "branch",
    "dimensions",
    "source_transaction_id",
    "source_transaction_type",
    "source_line_id",
    "source_identity_quality",
    "original_currency",
    "original_debit",
    "original_credit",
    "source_exchange_rate",
    "source_fx_status",
]


async def direct_sync(
    db: AsyncSession,
    ctx: Context,
    connection_id: uuid.UUID,
    resume_session: str | None = None,
    *,
    repair_since: str | None = None,
):
    runtime = ConnectorRuntime.for_session(db, ctx, connection_id)
    if runtime:
        from app.modules.connectors.locking import begin_sync

        await begin_sync(db, ctx, connection_id)
    connection = await scoped(db, ctx, Connection, connection_id)
    if runtime:
        await db.refresh(connection)
    if connection.provider not in NATIVE_PROVIDERS:
        raise HTTPException(422, "This connection does not use a direct vendor API")
    entity, period = await check_scope(db, ctx, connection)
    if not connection.encrypted_credentials:
        raise HTTPException(422, "Configure secure credentials before direct synchronization")
    credentials = decrypt(connection.encrypted_credentials)
    initial_config = digest(connection.config)
    initial_credentials = connection.encrypted_credentials
    session_id = resume_session or str(uuid.uuid4())
    cache_scope = digest(
        [
            str(connection.id),
            str(connection.tenant_id),
            str(connection.period_id),
            connection.config,
            session_id,
        ]
    )
    run = SyncRun(**scope_values(connection), connection_id=connection.id)
    db.add(run)
    await db.flush()
    objects: list[dict] = []
    manifest = {
        "objects": objects,
        "provider": connection.provider,
        "period_start": str(period.start_date),
        "period_end": str(period.end_date),
        "complete_general_ledger": False,
        "connector_version": NativeAdapter.version,
        "completeness": "independent_source_controls_required",
        "resume_session": session_id,
    }

    async def preserve(resource: str, raw: bytes):
        if runtime:
            candidate = runtime.last_object
            import hashlib

            stored = (
                candidate
                if candidate and candidate["sha256"] == hashlib.sha256(raw).hexdigest()
                else await runtime.persist_object(raw)
            )
        else:
            stored = await put_private(db, ctx, io.BytesIO(raw))
        objects.append({"resource": resource[:300], **stored})
        run.manifest = {**manifest, "objects": list(objects)}
        await db.flush()

    adapter = NativeAdapter(
        connection.provider,
        {**connection.config, **({"cdc_since": repair_since} if repair_since else {})},
        credentials,
        settings().connector_allowed_origins,
        preserve,
    )
    quota_client = None
    if runtime:
        await runtime.put(
            "session",
            cache_scope,
            {"resume_session": session_id, "status": "extracting"},
            ttl_hours=168,
        )
        from redis.asyncio import Redis

        from app.modules.connectors.native_auth import token
        from app.modules.connectors.quota import OrganizationQuota

        adapter.read_cache = lambda key, fetch: runtime.cached_read(cache_scope, key, fetch)
        grant_key = digest(
            [
                connection.provider,
                adapter.config.oauth_grant_id or adapter.config.company_id,
                credentials.get("client_id", ""),
                adapter.config.account_id,
                adapter.config.environment,
                adapter.config.directory_tenant,
            ]
        )

        async def refresh(current, force):
            return await runtime.rotate_grant(
                grant_key,
                current,
                lambda source: token(connection.provider, adapter.config, source),
                force=force,
            )

        adapter.refresh_handler = refresh
        quota_client = Redis.from_url(settings().redis_url)
        adapter.governor = OrganizationQuota(
            quota_client,
            connection.provider,
            adapter.config.company_id,
            credentials.get("client_id", ""),
            adapter.config.requests_per_minute,
            adapter.config.requests_per_day,
            adapter.config.concurrency,
        )
    counts: dict[str, int] = defaultdict(int)
    identities: dict[str, set[str]] = defaultdict(set)
    accounts = set()
    ledger_accounts = set()
    journals: dict[str, Decimal] = defaultdict(Decimal)
    journal_dates: dict[str, str] = {}
    movements: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    tb_balances: dict[str, tuple[Decimal, Decimal, Decimal, Decimal]] = {}
    failure = None
    debit_total = credit_total = Decimal(0)
    fingerprints: dict[str, str] = {}
    comparable = True
    # Private on-disk spools rather than a population-sized ORM/CSV string list.
    with tempfile.TemporaryDirectory(prefix="auditos-direct-") as directory:
        from contextlib import ExitStack
        from pathlib import Path

        with ExitStack() as stack:
            paths = {kind: Path(directory) / (kind + ".csv") for kind in ("coa", "gl", "tb")}
            streams = {
                kind: stack.enter_context(path.open("w", encoding="utf-8", newline=""))
                for kind, path in paths.items()
            }
            writers = {
                kind: csv.DictWriter(stream, fieldnames=COLUMNS, extrasaction="ignore")
                for kind, stream in streams.items()
            }
            for writer in writers.values():
                writer.writeheader()
            try:
                with localcontext() as numeric:
                    numeric.prec = 48
                    async for kind, row in adapter.extract(
                        period.start_date, period.end_date, entity.functional_currency
                    ):
                        if kind not in writers:
                            raise ConnectorError("Unknown native accounting population")
                        if kind == "tb" and not all(
                            str(row.get(key, "")).strip()
                            for key in ("opening_balance", "closing_balance")
                        ):
                            raise ConnectorError(
                                "Native TB requires source opening and closing balances"
                            )
                        options = ImportOptions.model_validate(
                            {
                                "client_id": connection.client_id,
                                "entity_id": connection.entity_id,
                                "period_id": connection.period_id,
                                "source_system": connection.provider,
                                "currency": entity.functional_currency,
                                "kind": kind,
                            }
                        )
                        # Normalize before staging anything; no silently invalid partial extracts.
                        canonical, _ = normalize(
                            row,
                            options,
                            period.start_date,
                            period.end_date,
                            entity.functional_currency,
                            counts[kind] + 2,
                        )
                        identity = (
                            canonical["source_id"] if kind == "gl" else canonical["account_code"]
                        )
                        if identity in identities[kind]:
                            raise ConnectorError("Duplicate API source/account identifier")
                        identities[kind].add(identity)
                        if kind == "coa":
                            accounts.add(canonical["account_code"])
                        elif kind == "tb":
                            if canonical["currency"] != entity.functional_currency:
                                raise ConnectorError(
                                    "Native trial balance must be in company base currency"
                                )
                            tb_balances[canonical["account_code"]] = (
                                Decimal(canonical["opening_balance"]),
                                Decimal(canonical["base_debit"]),
                                Decimal(canonical["base_credit"]),
                                Decimal(canonical["closing_balance"]),
                            )
                        elif kind == "gl":
                            if len(fingerprints) < 100000:
                                fingerprints[identity] = digest(row)
                            else:
                                comparable = False
                            if identity.startswith("report:") or row.get(
                                "source_identity_quality", ""
                            ).startswith("snapshot"):
                                comparable = False
                            debit_total += Decimal(canonical["base_debit"])
                            credit_total += Decimal(canonical["base_credit"])
                            ledger_accounts.add(canonical["account_code"])
                            ref = canonical["journal_ref"]
                            if (
                                journal_dates.setdefault(ref, canonical["posting_date"])
                                != canonical["posting_date"]
                            ):
                                raise ConnectorError("API journal reference spans posting dates")
                            journals[ref] += Decimal(canonical["base_debit"]) - Decimal(
                                canonical["base_credit"]
                            )
                            if not canonical["opening"]:
                                movement = movements[canonical["account_code"]]
                                movement[0] += Decimal(canonical["base_debit"])
                                movement[1] += Decimal(canonical["base_credit"])
                        writers[kind].writerow(row)
                        counts[kind] += 1
                    if not counts["gl"]:
                        raise ConnectorError(
                            "No ledger postings were returned for the selected period"
                        )
                    if not counts["coa"] and (
                        connection.provider != "sap-s4" or adapter.config.accounts_path
                    ):
                        raise ConnectorError(
                            "The source chart is empty but ledger postings were returned"
                        )
                    if any(journals.values()):
                        raise ConnectorError("Native API ledger contains unbalanced journal groups")
                    for label, expected, observed in (
                        ("rows", adapter.config.expected_gl_rows, counts["gl"]),
                        ("debit", adapter.config.expected_gl_debit, debit_total),
                        ("credit", adapter.config.expected_gl_credit, credit_total),
                    ):
                        if expected is not None and expected != observed:
                            raise ConnectorError(
                                "Independent API source control mismatch: " + label
                            )
                    if counts["coa"] and ledger_accounts - accounts:
                        raise ConnectorError(
                            "Native ledger references accounts absent from the source chart"
                        )
                    if tb_balances:
                        if ledger_accounts - tb_balances.keys():
                            raise ConnectorError("Native TB omits a posted ledger account")
                        for code, (_, debit, credit, _) in tb_balances.items():
                            if movements[code] != [debit, credit]:
                                raise ConnectorError(
                                    "Native TB movements differ from the extracted GL"
                                )
                        if sum(v[0] for v in tb_balances.values()) or sum(
                            v[3] for v in tb_balances.values()
                        ):
                            raise ConnectorError("Native TB opening/closing totals do not balance")
            except (ConnectorError, ValueError, KeyError, TypeError) as exc:
                # Known validation messages contain field names, never credential values or API bodies.
                failure = (
                    str(exc) if isinstance(exc, ValueError) else "Unexpected source response schema"
                )
            finally:
                await adapter.close()
                if quota_client:
                    await quota_client.aclose()

            for stream in streams.values():
                stream.flush()
        if runtime:
            from app.modules.connectors.locking import finish_sync

            connection = await finish_sync(db, ctx, connection_id)
            if (
                not connection
                or digest(connection.config) != initial_config
                or connection.encrypted_credentials != initial_credentials
            ):
                failure = "Connection configuration or credentials changed during extraction; start a new session"
        if connection and not (
            runtime and failure and failure.startswith("Connection configuration")
        ):
            connection.encrypted_credentials = encrypt(adapter.credentials)
        run.status = "failed" if failure else "completed"
        run.error_category = "extraction_or_validation_failed" if failure else None
        run.completeness = "insufficient_evidence"
        run.manifest = {
            **manifest,
            "objects": objects,
            "counts": dict(counts),
            "account_population": "source_chart" if counts["coa"] else "not_extracted",
            "functional_totals": {"debit": str(debit_total), "credit": str(credit_total)},
            "source_control_reference": adapter.config.control_reference,
            "checkpoint": {"replayed": runtime.replayed, "downloaded": runtime.downloaded}
            if runtime
            else {},
            "execution_mode": "live" if adapter.transport is None else "simulated",
            "scope_verification": adapter.scope_evidence,
            "validation_error": failure,
            "derived_import_batch_ids": {},
        }
        if not failure:
            if runtime:
                from app.modules.connectors.revisions import append_revision

                revision = await append_revision(
                    db, ctx, connection, run.id, fingerprints, comparable
                )
                run.manifest = {**run.manifest, "source_revision": revision}
            batches = {}
            for kind in ("coa", "tb", "gl"):
                if not counts[kind]:
                    continue
                options = ImportOptions.model_validate(
                    {
                        "client_id": connection.client_id,
                        "entity_id": connection.entity_id,
                        "period_id": connection.period_id,
                        "kind": kind,
                        "source_system": connection.provider,
                        "currency": entity.functional_currency,
                        "source_sync_run_id": run.id,
                        "source_complete": False,
                        "supersedes_id": adapter.config.supersedes_ids.get(kind),
                        "expected_rows": adapter.config.expected_gl_rows if kind == "gl" else None,
                        "expected_debit": adapter.config.expected_gl_debit
                        if kind == "gl"
                        else None,
                        "expected_credit": adapter.config.expected_gl_credit
                        if kind == "gl"
                        else None,
                    }
                )
                with paths[kind].open("rb") as source_stream:
                    batch = await upload(
                        db,
                        ctx,
                        options,
                        f"{connection.provider}-{kind}.csv",
                        source_stream,
                        str(run.id),
                    )
                batches[kind] = str(batch.id)
            run.manifest = {**run.manifest, "derived_import_batch_ids": batches}
        connection.status = "sync_failed" if failure else "extracted_pending_review"
        record(db, ctx, "connector.direct_sync", connection.id, str(run.id))
        await db.flush()
        if runtime:
            await runtime.put(
                "session",
                cache_scope,
                {
                    "resume_session": session_id,
                    "status": run.status,
                    "sync_run_id": str(run.id),
                    "counts": dict(counts),
                    "checkpoint": run.manifest["checkpoint"],
                },
                ttl_hours=168,
            )
    return {
        "id": str(run.id),
        "status": run.status,
        "completeness": run.completeness,
        "result": run.manifest,
    }
