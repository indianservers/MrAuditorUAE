import csv
import io
import json
import tempfile
import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Context
from app.db.models.platform import FinancialPeriod
from app.modules.accounting.models import Connection, SyncRun
from app.modules.accounting.schemas import ImportOptions
from app.modules.accounting.service import scope_values, scoped, upload
from app.modules.connectors.secrets import decrypt, encrypt
from app.modules.connectors.zoho import RESOURCES, ZohoConnector
from app.modules.lineage.storage import ObjectStore


async def zoho_sync(db: AsyncSession, ctx: Context, connection_id: uuid.UUID):
    connection = await scoped(db, ctx, Connection, connection_id, True)
    if connection.provider != "zoho" or not connection.organization_id:
        raise HTTPException(422, "Zoho organization selection required")
    period = await scoped(db, ctx, FinancialPeriod, connection.period_id)
    credentials = decrypt(connection.encrypted_credentials or "")
    adapter = ZohoConnector(
        connection.region,
        credentials["client_id"],
        credentials["client_secret"],
        credentials.get("refresh_token", ""),
    )
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
    excluded_journals = 0
    excluded_out_of_period = 0
    status = "completed"
    error = None
    # Partial failures persist already received raw pages, never claim complete GL coverage.
    try:
        for resource in RESOURCES:
            async for page in adapter.pages(resource, connection.organization_id):
                data = adapter.last_raw or json.dumps(page, sort_keys=True, default=str).encode()
                stored = ObjectStore().put(str(ctx.tenant_id), io.BytesIO(data))
                manifest.append({"resource": resource, "page": page["page"], **stored})
                if resource == "chartofaccounts":
                    for account in page["raw"][resource]:
                        chart_writer.writerow(
                            {
                                "account_code": str(account["account_id"]),
                                "account_name": account["account_name"],
                                "source_group": account.get("account_type", ""),
                                "source_account_code": account.get("account_code", ""),
                            }
                        )
                        chart_count += 1
                if resource == "journals":
                    for header in page["raw"]["journals"]:
                        detail = await adapter.journal_detail(
                            str(header["journal_id"]), connection.organization_id
                        )
                        detail_raw = adapter.last_raw or json.dumps(detail, default=str).encode()
                        original = ObjectStore().put(str(ctx.tenant_id), io.BytesIO(detail_raw))
                        manifest.append(
                            {
                                "resource": "journal_detail",
                                "journal_id": str(header["journal_id"]),
                                **original,
                            }
                        )
                        journal = detail["journal"]
                        if journal.get("status") != "published":
                            excluded_journals += 1
                            continue
                        if (
                            not period.start_date
                            <= date.fromisoformat(journal["journal_date"])
                            <= period.end_date
                        ):
                            excluded_out_of_period += 1
                            continue
                        for item in journal.get("line_items", []):
                            side = item.get("debit_or_credit")
                            if side not in {"debit", "credit"}:
                                raise ValueError("Unsupported journal side")
                            amount = str(item["amount"])
                            base = str(item["bcy_amount"]) if "bcy_amount" in item else ""
                            writer.writerow(
                                {
                                    "account_code": str(item["account_id"]),
                                    "account_name": item.get(
                                        "account_name", str(item["account_id"])
                                    ),
                                    "journal_ref": str(header["journal_id"]),
                                    "posting_date": journal["journal_date"],
                                    "debit": amount if side == "debit" else "0",
                                    "credit": amount if side == "credit" else "0",
                                    "base_debit": base if side == "debit" else "0",
                                    "base_credit": base if side == "credit" else "0",
                                    "currency": journal.get("currency_code", ""),
                                    "exchange_rate": str(journal.get("exchange_rate", "")),
                                    "source_id": str(header["journal_id"])
                                    + ":"
                                    + str(item["line_id"]),
                                    "counterparty": item.get("customer_id", ""),
                                    "description": item.get("description", ""),
                                    "tax_code": item.get("tax_id", ""),
                                    "project": item.get("project_id", ""),
                                    "manual": "true",
                                }
                            )
                            extracted_lines += 1

    except Exception:
        status = "failed"
        error = "partial_extraction"
    credentials.update(access_token=adapter.access_token, refresh_token=adapter.refresh_token)
    connection.encrypted_credentials = encrypt(credentials)
    run.status = status
    run.error_category = error
    run.manifest = {
        "objects": manifest,
        "connector_version": adapter.version,
        "fallback": "Upload an independently controlled GL and trial-balance report",
        "complete_general_ledger": False,
        "excluded_out_of_period_journals": excluded_out_of_period,
        "period_start": str(period.start_date),
        "period_end": str(period.end_date),
        "incremental_support": "Only use resource-documented filters; this release performs complete resource pagination",
    }
    if status == "completed" and extracted_lines:
        from app.db.models.platform import LegalEntity

        entity = await scoped(db, ctx, LegalEntity, connection.entity_id)
        normalized.seek(0)
        # The derived CSV has lineage to every original API page/detail via the sync run.
        options = ImportOptions(
            client_id=connection.client_id,
            entity_id=connection.entity_id,
            period_id=connection.period_id,
            kind="journals",
            source_system="zoho",
            currency=entity.functional_currency,
            source_sync_run_id=run.id,
            source_complete=False,
        )
        batch = await upload(
            db,
            ctx,
            options,
            "zoho-manual-journals.csv",
            io.BytesIO(normalized.read().encode()),
            str(run.id),
        )
        run.manifest = {
            **run.manifest,
            "derived_import_batch_id": str(batch.id),
            "extracted_lines": extracted_lines,
            "excluded_nonpublished_journals": excluded_journals,
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
    run.completeness = "insufficient_evidence"
    await db.flush()
    return {
        "id": str(run.id),
        "status": status,
        "result": run.manifest,
        "completeness": run.completeness,
    }
