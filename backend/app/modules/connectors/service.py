import csv
import io
import json
import tempfile
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import Context
from app.db.models.platform import FinancialPeriod
from app.modules.accounting.models import Connection, SyncRun
from app.modules.accounting.schemas import ImportOptions
from app.modules.accounting.service import scope_values, scoped, upload
from app.modules.connectors.enrichment import tax_evidence
from app.modules.connectors.ledger import zoho_ledger_row
from app.modules.connectors.runtime import ConnectorRuntime, digest
from app.modules.connectors.secrets import decrypt, encrypt
from app.modules.connectors.zoho import DETAIL_RESOURCES, RESOURCES, ZohoConnector
from app.modules.ingestion.parser import normalize
from app.modules.saas.storage import put_private


async def zoho_sync(
    db: AsyncSession, ctx: Context, connection_id: uuid.UUID, resume_session: str | None = None
):
    runtime = ConnectorRuntime.for_session(db, ctx, connection_id)
    if runtime:
        from app.modules.connectors.locking import begin_sync

        await begin_sync(db, ctx, connection_id)
    connection = await scoped(db, ctx, Connection, connection_id)
    if runtime:
        await db.refresh(connection)
    if connection.provider != "zoho" or not connection.organization_id:
        raise HTTPException(422, "Zoho organization selection required")
    period = await scoped(db, ctx, FinancialPeriod, connection.period_id)
    from app.db.models.platform import LegalEntity

    entity = await scoped(db, ctx, LegalEntity, connection.entity_id)
    config = getattr(connection, "config", {})
    credentials = decrypt(connection.encrypted_credentials or "")
    adapter = ZohoConnector(
        connection.region,
        credentials["client_id"],
        credentials["client_secret"],
        credentials.get("refresh_token", ""),
    )
    initial_config, initial_credentials = digest(config), connection.encrypted_credentials
    session_id = resume_session or str(uuid.uuid4())
    cache_scope = digest(
        [
            str(connection.id),
            str(connection.period_id),
            connection.region,
            connection.organization_id,
            config,
            session_id,
        ]
    )
    quota_client = None
    if runtime:
        from redis.asyncio import Redis

        from app.modules.connectors.quota import OrganizationQuota

        adapter.read_cache = lambda key, fetch: runtime.cached_read(cache_scope, key, fetch)

        async def rotate(current, force):
            async def exchange(source):
                adapter.refresh_token = source.get("refresh_token", "")
                return {**source, **await adapter.exchange_token()}

            return await runtime.rotate_grant(
                digest(
                    [
                        "zoho",
                        connection.region,
                        credentials["client_id"],
                        config.get("oauth_grant_id") or connection.organization_id,
                    ]
                ),
                current,
                exchange,
                force,
            )

        adapter.token_handler = rotate
        quota_client = Redis.from_url(settings().redis_url)
        adapter.governor = OrganizationQuota(
            quota_client, "zoho", connection.organization_id, credentials["client_id"], 60, 10000, 2
        )
        await runtime.put(
            "session",
            cache_scope,
            {"resume_session": session_id, "status": "extracting"},
            ttl_hours=168,
        )

    async def preserve(raw):
        if runtime:
            import hashlib

            candidate = runtime.last_object
            return (
                candidate
                if candidate and candidate["sha256"] == hashlib.sha256(raw).hexdigest()
                else await runtime.persist_object(raw)
            )
        return await put_private(db, ctx, io.BytesIO(raw))

    document_controls = []
    started = datetime.now(UTC)
    delta_resources = set()
    run = SyncRun(**scope_values(connection), connection_id=connection.id)
    db.add(run)
    await db.flush()
    manifest = []
    normalized = tempfile.TemporaryFile(mode="w+", encoding="utf-8", newline="")
    columns = [
        "account_code",
        "account_name",
        "journal_ref",
        "posting_date",
        "debit",
        "credit",
        "base_debit",
        "base_credit",
        "currency",
        "exchange_rate",
        "source_id",
        "counterparty",
        "description",
        "tax_code",
        "project",
        "manual",
        "opening",
    ]
    writer = csv.DictWriter(normalized, fieldnames=columns)
    writer.writeheader()
    chart = tempfile.TemporaryFile(mode="w+", encoding="utf-8", newline="")
    chart_writer = csv.DictWriter(
        chart, fieldnames=["account_code", "account_name", "source_group", "source_account_code"]
    )
    chart_writer.writeheader()
    chart_count = 0
    extracted_lines = 0
    extracted_accounts = 0
    ledger_totals: dict[str, dict[str, Decimal]] = {}
    seen_accounts = set()
    seen_postings = set()
    fingerprints: dict[str, str] = {}
    comparable = True
    journal_balances: dict[str, Decimal] = defaultdict(Decimal)
    base_debit = base_credit = Decimal(0)
    validation_options = ImportOptions(
        client_id=connection.client_id,
        entity_id=connection.entity_id,
        period_id=connection.period_id,
        source_system="zoho",
        currency=entity.functional_currency,
    )
    status = "completed"
    error = None
    # Partial failures persist already received raw pages, never claim complete GL coverage.
    try:
        if runtime:
            organization_reply = await adapter.get("organizations", {})
            organizations = organization_reply.get("organizations", [])
            organization = next(
                (
                    o
                    for o in organizations
                    if str(o.get("organization_id")) == connection.organization_id
                ),
                None,
            )
            if not organization or organization.get("currency_code") != entity.functional_currency:
                raise ValueError("Zoho organization/base currency mismatch")
            manifest.append(
                {
                    "resource": "organization_identity",
                    **await preserve(
                        adapter.last_raw or json.dumps(organization_reply, default=str).encode()
                    ),
                }
            )
        resources = dict(RESOURCES)
        if config.get("include_documents"):
            resources.update(customerpayments="customerpayments", vendorpayments="vendorpayments")
        for resource in resources:
            extra = {"filter_by": "AccountType.All"} if resource == "chartofaccounts" else None
            if runtime and config.get("incremental_documents"):
                from app.modules.connectors.incremental import ZOHO_MODIFIED, modified_filter

                if resource in ZOHO_MODIFIED:
                    watermark = await runtime.get(
                        "watermark", digest([str(connection.id), resource])
                    )
                    extra = modified_filter(
                        resource, watermark.get("last_completed_start") if watermark else None
                    )
                    delta_resources.add(resource)
            async for page in adapter.pages(resource, connection.organization_id, extra):
                data = adapter.last_raw or json.dumps(page, sort_keys=True, default=str).encode()
                stored = await preserve(data)
                manifest.append({"resource": resource, "page": page["page"], **stored})
                if resource == "chartofaccounts":
                    for account in page["raw"][resource]:
                        if account["account_id"] in seen_accounts:
                            raise ValueError("Duplicate Zoho account")
                        seen_accounts.add(account["account_id"])
                        chart_writer.writerow(
                            {
                                "account_code": str(account["account_id"]),
                                "account_name": account["account_name"],
                                "source_group": account.get("account_type", ""),
                                "source_account_code": account.get("account_code", ""),
                            }
                        )
                        chart_count += 1
                        # Fetch ALL posting types for every account, including inactive
                        # accounts returned by the unfiltered chart endpoint.
                        async for transactions in adapter.pages(
                            "chartofaccounts/accounttransactions",
                            connection.organization_id,
                            {
                                "account_id": str(account["account_id"]),
                                "date_start": str(period.start_date),
                                "date_end": str(period.end_date),
                                "filter_by": "TransactionType.All",
                            },
                        ):
                            original = await preserve(
                                adapter.last_raw
                                or json.dumps(transactions["raw"], default=str).encode()
                            )
                            manifest.append(
                                {
                                    "resource": "accounttransactions",
                                    "account_id": str(account["account_id"]),
                                    "page": transactions["page"],
                                    **original,
                                }
                            )
                            for item in transactions["raw"]["transactions"]:
                                row = zoho_ledger_row(
                                    item, account, period.start_date, period.end_date
                                )
                                if row["source_id"] in seen_postings:
                                    raise ValueError("Duplicate Zoho ledger posting")
                                seen_postings.add(row["source_id"])
                                if row["currency"] == entity.functional_currency:
                                    row["exchange_rate"] = "1"
                                canonical, _ = normalize(
                                    row,
                                    validation_options,
                                    period.start_date,
                                    period.end_date,
                                    entity.functional_currency,
                                    extracted_lines + 2,
                                )
                                source_debit, source_credit = (
                                    Decimal(canonical["base_debit"]),
                                    Decimal(canonical["base_credit"]),
                                )
                                base_debit += source_debit
                                base_credit += source_credit
                                journal_balances[canonical["journal_ref"]] += (
                                    source_debit - source_credit
                                )
                                if len(fingerprints) < 100000:
                                    fingerprints[row["source_id"]] = digest(row)
                                else:
                                    comparable = False
                                writer.writerow(row)
                                extracted_lines += 1
                                totals = ledger_totals.setdefault(
                                    row["currency"] or "unspecified",
                                    {"debit": Decimal(0), "credit": Decimal(0)},
                                )
                                totals["debit"] += Decimal(row["debit"])
                                totals["credit"] += Decimal(row["credit"])
                        extracted_accounts += 1
                if config.get("include_documents") and resource in DETAIL_RESOURCES:
                    singular, id_key = DETAIL_RESOURCES[resource]
                    for summary in page["raw"][resource]:
                        identity = str(summary[id_key])
                        detail = await adapter.document_detail(
                            resource, identity, connection.organization_id
                        )
                        document = detail.get(singular)
                        if not isinstance(document, dict) or str(document.get(id_key)) != identity:
                            raise ValueError("Zoho detail identity mismatch")
                        manifest.append(
                            {
                                "resource": resource + "/detail",
                                "id": identity,
                                **await preserve(adapter.last_raw),
                            }
                        )
                        if (
                            document.get("exchange_rate") is not None
                            and Decimal(str(document["exchange_rate"])) <= 0
                        ):
                            raise ValueError("Invalid Zoho source exchange rate")
                        document_controls.append(
                            {
                                "resource": resource,
                                "id": identity,
                                "currency": document.get("currency_code"),
                                "exchange_rate": str(document.get("exchange_rate", "")),
                                "tax": tax_evidence(document, "zoho"),
                            }
                        )
                        if (
                            resource == "invoices"
                            and document.get("has_attachment")
                            and config.get("include_attachments")
                        ):
                            content, mime = await adapter.invoice_attachment(
                                identity, connection.organization_id
                            )
                            manifest.append(
                                {
                                    "resource": "invoice_attachment",
                                    "id": identity,
                                    "content_type": mime,
                                    **await preserve(content),
                                }
                            )
                if resource == "journals":
                    # Manual details remain evidence; never append them again to GL.
                    for header in page["raw"]["journals"]:
                        detail = await adapter.journal_detail(
                            str(header["journal_id"]), connection.organization_id
                        )
                        original = await preserve(
                            adapter.last_raw or json.dumps(detail, default=str).encode()
                        )
                        manifest.append(
                            {
                                "resource": "journal_detail",
                                "journal_id": str(header["journal_id"]),
                                **original,
                            }
                        )

        if not extracted_lines or any(journal_balances.values()):
            raise ValueError("Zoho full ledger is empty or contains unbalanced journal groups")
    except Exception:
        status = "failed"
        error = "partial_extraction"
    if quota_client:
        await quota_client.aclose()
    changed = False
    if runtime:
        from app.modules.connectors.locking import finish_sync

        connection = await finish_sync(db, ctx, connection_id)
        changed = (
            not connection
            or digest(connection.config) != initial_config
            or connection.encrypted_credentials != initial_credentials
        )
        if changed:
            status, error = "failed", "configuration_changed_during_extraction"
    credentials.update(access_token=adapter.access_token, refresh_token=adapter.refresh_token)
    if not changed:
        connection.encrypted_credentials = encrypt(credentials)
    run.status = status
    run.error_category = error
    run.manifest = {
        "objects": manifest,
        "resume_session": session_id,
        "counts": {"gl": extracted_lines, "coa": chart_count},
        "functional_totals": {"debit": str(base_debit), "credit": str(base_credit)},
        "checkpoint": {"replayed": runtime.replayed, "downloaded": runtime.downloaded}
        if runtime
        else {},
        "execution_mode": "live" if adapter.transport is None else "simulated",
        "document_controls": document_controls,
        "connector_version": adapter.version,
        "fallback": "Upload an independently controlled GL and trial-balance report",
        "complete_general_ledger": False,
        "ledger_coverage": "all_account_transaction_types",
        "accounts_with_completed_pagination": extracted_accounts,
        "extracted_lines": extracted_lines,
        "transaction_totals_by_currency": {
            currency: {k: str(v) for k, v in totals.items()}
            for currency, totals in ledger_totals.items()
        },
        "requires_validation": True,
        "period_start": str(period.start_date),
        "period_end": str(period.end_date),
        "incremental_support": {
            "document_resources": sorted(delta_resources),
            "gl": "full_account_transaction_pagination",
            "deletions": "full_population_comparison_required",
        },
    }
    if status == "completed" and runtime:
        from app.modules.connectors.revisions import append_revision

        revision = await append_revision(db, ctx, connection, run.id, fingerprints, comparable)
        run.manifest = {**run.manifest, "source_revision": revision}
    if status == "completed" and runtime and delta_resources:
        from app.modules.connectors.incremental import commit_watermarks

        await commit_watermarks(db, ctx, connection.id, delta_resources, started, run.id)
    if status == "completed" and extracted_lines:
        normalized.seek(0)
        # The derived CSV has lineage to every original API page/detail via the sync run.
        options = ImportOptions(
            client_id=connection.client_id,
            entity_id=connection.entity_id,
            period_id=connection.period_id,
            kind="gl",
            source_system="zoho",
            currency=entity.functional_currency,
            source_sync_run_id=run.id,
            source_complete=False,
        )
        batch = await upload(
            db,
            ctx,
            options,
            "zoho-general-ledger.csv",
            io.BytesIO(normalized.read().encode()),
            str(run.id),
        )
        run.manifest = {
            **run.manifest,
            "derived_import_batch_id": str(batch.id),
            "extracted_lines": extracted_lines,
        }
    if status == "completed" and chart_count:
        chart.seek(0)
        options = ImportOptions(
            client_id=connection.client_id,
            entity_id=connection.entity_id,
            period_id=connection.period_id,
            kind="coa",
            source_system="zoho",
            source_sync_run_id=run.id,
            source_complete=False,
        )
        chart_batch = await upload(
            db,
            ctx,
            options,
            "zoho-chart-of-accounts.csv",
            io.BytesIO(chart.read().encode()),
            str(run.id),
        )
        run.manifest = {
            **run.manifest,
            "derived_chart_batch_id": str(chart_batch.id),
            "extracted_accounts": chart_count,
        }
    chart.close()
    normalized.close()
    if runtime:
        await runtime.put(
            "session",
            cache_scope,
            {
                "resume_session": session_id,
                "status": status,
                "sync_run_id": str(run.id),
                "counts": {"gl": extracted_lines, "coa": chart_count},
            },
            ttl_hours=168,
        )
    connection.status = "sync_failed" if status == "failed" else "extracted_pending_review"
    run.completeness = "insufficient_evidence"
    await db.flush()
    return {
        "id": str(run.id),
        "status": status,
        "result": run.manifest,
        "completeness": run.completeness,
    }
