"""Purpose-bound credit-normal book turnover from an authorized committed GL."""

import uuid
from datetime import date
from decimal import Decimal, localcontext

from fastapi import HTTPException
from pydantic import Field, model_validator

from app.modules.country_workflows.turnover import Money, TurnoverAmount
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "committed-gl-turnover/1"


class TurnoverLedgerInput(Strict):
    snapshot_id: uuid.UUID
    account_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    registration: str = Field(min_length=1, max_length=15)
    period_start: date
    period_end: date
    currency: str = Field(pattern="^[A-Z]{3}$")
    expected_rows: int = Field(ge=0, le=5000, strict=True)
    expected_amount: Money
    nil_reason: str = Field(default="", max_length=2000)
    assessment: str = Field(min_length=10, max_length=2000)
    label: str = Field(min_length=3, max_length=200)

    @model_validator(mode="after")
    def explicit_scope(self):
        if (
            len(set(self.account_ids)) != len(self.account_ids)
            or self.period_start > self.period_end
        ):
            raise ValueError("Distinct accounts and an ordered ledger period required")
        if len(self.assessment.strip()) < 10:
            raise ValueError(
                "Explicit registration allocation and revenue account assessment required"
            )
        if (self.expected_rows == 0) != bool(self.nil_reason.strip()):
            raise ValueError("Only an explicitly assessed zero-line selection needs a nil reason")
        if self.expected_rows == 0 and (
            self.expected_amount != 0 or len(self.nil_reason.strip()) < 10
        ):
            raise ValueError(
                "Nil ledger selection requires zero amount and a meaningful assessment"
            )
        return self


def source_rows(data, entries, country):
    import re

    pattern = r"[0-9]{15}" if country == "AE" else r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]"
    currency = "AED" if country == "AE" else "INR"
    if (
        country not in {"AE", "IN"}
        or data.currency != currency
        or not re.fullmatch(pattern, data.registration)
    ):
        raise ValueError("Turnover registration syntax and return currency must match UAE or India")
    if len(entries) != data.expected_rows or len(entries) > 5000:
        raise ValueError(
            "Committed ledger line count differs from the independent control or exceeds 5,000"
        )
    rows = []
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for entry in entries:
            if (
                entry["currency"] != data.currency
                or not data.period_start.isoformat() <= entry["date"] <= data.period_end.isoformat()
            ):
                raise ValueError(
                    "Every ledger line must use the selected functional currency and period"
                )
            number = -Decimal(entry["amount"])
            row = TurnoverAmount(
                id=entry["id"],
                reference=entry["id"],
                registration=data.registration,
                period_start=data.period_start,
                period_end=data.period_end,
                currency=data.currency,
                amount=number,
                assessment=data.assessment,
            ).model_dump(mode="json")
            rows.append(
                {
                    **row,
                    "source_journal_reference": entry["reference"],
                    "source_account_code": entry["account_code"],
                    "source_posting_date": entry["date"],
                    "source_record_id": entry["source_record_id"],
                }
            )
        total = sum((Decimal(row["amount"]) for row in rows), Decimal(0))
        if total != data.expected_amount:
            raise ValueError(
                "Credit-minus-debit book turnover differs from the independent signed amount control"
            )
    if not rows:
        rows = [
            TurnoverAmount(
                id="assessed-nil",
                reference="ASSESSED-NIL",
                registration=data.registration,
                period_start=data.period_start,
                period_end=data.period_end,
                currency=data.currency,
                amount="0",
                assessment=data.assessment,
            ).model_dump(mode="json")
        ]
    return rows, {data.currency: str(total)}


async def prepare(db, ctx, eng, data, request_id):
    from app.db.models.platform import FinancialPeriod, LegalEntity
    from app.modules.accounting.models import ImportBatch
    from app.modules.intelligence import service
    from app.modules.jurisdictions.workspace import resolved

    binding, _ = await resolved(db, ctx, eng)
    period = await db.get(FinancialPeriod, eng.period_id)
    entity = await db.get(LegalEntity, eng.entity_id)
    if (
        not period
        or not period.start_date <= data.period_start <= data.period_end <= period.end_date
    ):
        raise HTTPException(
            422, "Turnover ledger period must be covered by the engagement financial period"
        )
    if not entity or entity.functional_currency != data.currency:
        raise HTTPException(
            422, "Use the entity functional currency; no turnover FX conversion is inferred"
        )
    snapshot, receipt = await service.snapshot(db, ctx, eng, data.snapshot_id)
    batch = await db.get(ImportBatch, snapshot.batch_id)
    if not batch or batch.kind not in {"gl", "journals"}:
        raise HTTPException(
            422,
            "Committed GL/journal detail required; trial balances cannot establish turnover movements",
        )
    entries = await service.ledger(
        db, ctx, eng, snapshot, data.account_ids, data.period_end, data.period_start
    )
    try:
        rows, totals = source_rows(data, entries, binding.country)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    contributors = {str(ctx.user_id)}
    for source in (snapshot, batch):
        if source.created_by is not None:
            contributors.add(str(source.created_by))
    return await service.append(
        db,
        ctx,
        eng,
        "workflow-source",
        {
            "table_type": "turnover-amounts",
            "rows": rows,
            "row_count": len(rows),
            "control_totals": totals,
            "review_status": "UNVERIFIED",
            "title": data.label,
            "parser_version": CONTRACT,
            "source_identity": "snapshot:" + str(snapshot.id),
            "source_sha256": snapshot.sha256,
            "source_snapshot_id": str(snapshot.id),
            "source_range": {
                "from": data.period_start.isoformat(),
                "through": data.period_end.isoformat(),
            },
            "allowed_source_roles": ["books"],
            "allowed_workflows": ["tax-turnover-bridge"],
            "contributors": sorted(contributors),
            "native_metadata": data.model_dump(mode="json"),
            "ledger_line_count": len(entries),
            "generated_nil_row": not entries,
            "sign_basis": "BOOK_REVENUE_CREDIT_MINUS_DEBIT",
            "population_completeness": "DECLARED_SNAPSHOT_ACCOUNT_REGISTRATION_PERIOD_ONLY",
            "limitations": [
                "Accounts and registration allocation are explicit reviewed selections, not inferred revenue classification or registry ownership",
                "Opening balances are excluded; credit-minus-debit movements preserve debit reversals without absolute-value conversion",
                "Amounts use functional currency already equal to the return currency; tax classification and FX conversion require separate evidence",
                "This source establishes only books, never filed return evidence; independent review and separate return populations remain required",
                "A zero-line selection yields a declared zero row only against explicit zero controls and a nil assessment",
            ],
        },
        [receipt],
        request_id,
    )
