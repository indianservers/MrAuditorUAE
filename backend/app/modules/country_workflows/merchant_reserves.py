"""Dated processor reserves and independently controlled reserve receivable balances."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, model_validator

from app.modules.country_workflows.audit_schemas import Currency, Identifier, Money
from app.modules.country_workflows.merchant_settlements import (
    expected_net,
)
from app.modules.country_workflows.merchant_settlements import (
    identity as batch_key,
)
from app.modules.country_workflows.merchant_settlements import (
    verify_controls as verify_settlements,
)
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "dated-merchant-reserve-ledger/1"
ROLES = {
    "settlements": "merchant-settlements",
    "movements": "merchant-reserve-movements",
    "balances": "merchant-reserve-balances",
    "ledger": "balance-controls",
}


class ReserveMovement(Strict):
    id: Identifier
    merchant: Identifier
    processor: Identifier
    settlement_id: Identifier
    currency: Currency
    date: date
    sequence: int = Field(ge=1, le=2147483647)
    kind: Literal["HELD", "RELEASED"]
    amount: Money = Field(gt=0)
    reference: Identifier
    evidence_reference: Identifier
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def assessed(self):
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess the original reserve movement and chronology")
        return self


class ReserveBalance(Strict):
    id: Identifier
    merchant: Identifier
    processor: Identifier
    currency: Currency
    period_start: date
    period_end: date
    opening_balance: Money = Field(ge=0)
    closing_balance: Money = Field(ge=0)
    ledger_account: Identifier
    account_assessment: str = Field(min_length=10, max_length=2000)
    evidence_reference: Identifier

    @model_validator(mode="after")
    def ordered(self):
        if self.period_end < self.period_start:
            raise ValueError("Reserve balance period must be ordered")
        if len(self.account_assessment.strip()) < 10:
            raise ValueError("Assess the processor reserve to ledger-account mapping")
        return self


ROW_TYPES: dict[str, type[Strict]] = {
    "merchant-reserve-movements": ReserveMovement,
    "merchant-reserve-balances": ReserveBalance,
}


def verify_controls(rows, controls, table_type):
    fields = (
        ("held", "released")
        if table_type == "merchant-reserve-movements"
        else ("opening_balance", "closing_balance")
    )
    currencies = {row["currency"] for row in rows}
    if not controls or not currencies <= set(controls):
        raise ValueError(
            "Declare independent reserve controls, including explicit zeros for a nil movement population"
        )
    for currency, declared in controls.items():
        if set(declared) != set(fields):
            raise ValueError(
                "Reserve controls require each separate held/released or opening/closing total"
            )
        for field in fields:
            if table_type == "merchant-reserve-movements":
                amount = sum(
                    (
                        Decimal(row["amount"])
                        for row in rows
                        if row["currency"] == currency and row["kind"] == field.upper()
                    ),
                    Decimal(0),
                )
            else:
                amount = sum(
                    (Decimal(row[field]) for row in rows if row["currency"] == currency), Decimal(0)
                )
            if amount != Decimal(declared[field]):
                raise ValueError("Independent reserve control differs: " + field)


def party(row):
    return row["merchant"], row["processor"], row["currency"]


def compare(data, sources, country):
    from app.modules.country_workflows.audit_calculations import result

    tables = {role: source["rows"] for role, source in sources.items()}
    verify_settlements(
        tables["settlements"], sources["settlements"].get("merchant_component_controls", {})
    )
    for role in ("movements", "balances"):
        controls = sources[role].get("merchant_reserve_controls", {})
        verify_controls(tables[role], controls, ROLES[role])
        if set(controls) != {data.currency}:
            raise ValueError(
                "Review one explicitly controlled reserve currency at a time; no FX netting"
            )
    balances = {}
    for row in tables["balances"]:
        if (
            row["currency"] != data.currency
            or row["period_start"] != data.period_start.isoformat()
            or row["period_end"] != data.as_of.isoformat()
        ):
            raise ValueError(
                "Reserve currency or opening/closing window differs from the selected period"
            )
        key = party(row)
        if key in balances:
            raise ValueError("Duplicate merchant/processor/currency reserve position")
        balances[key] = row
    batches = {}
    batch_scopes = set()
    for row in tables["settlements"]:
        if row["id"] in batches or batch_key(row) in batch_scopes:
            raise ValueError("Duplicate processor reserve batch identity")
        if (
            row["currency"] != data.currency
            or row["tax_country"] != country
            or row["fee_tax_kind"]
            not in {"FOREIGN_TAX", "NO_TAX_ASSESSED", "UAE_VAT" if country == "AE" else "INDIA_GST"}
        ):
            raise ValueError("Processor reserve batch currency or country assessment differs")
        batches[row["id"]] = row
        batch_scopes.add(batch_key(row))
    by_party = defaultdict(list)
    by_batch: defaultdict[str, defaultdict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    seen_refs, seen_order, ids = set(), set(), set()
    for row in tables["movements"]:
        batch = batches.get(row["settlement_id"])
        if batch is None or party(row) != party(batch):
            raise ValueError(
                "Reserve movement must reference the exact processor batch and merchant/currency"
            )
        if not data.period_start <= date.fromisoformat(row["date"]) <= data.as_of:
            raise ValueError("Reserve movement is outside the explicit reporting window")
        ref = (*party(row), row["kind"], row["reference"])
        order = (*party(row), row["date"], row["sequence"])
        if row["id"] in ids or ref in seen_refs or order in seen_order:
            raise ValueError(
                "Duplicate reserve movement, original reference or declared chronology position"
            )
        ids.add(row["id"])
        seen_refs.add(ref)
        seen_order.add(order)
        by_party[party(row)].append(row)
        by_batch[row["settlement_id"]][row["kind"]] += Decimal(row["amount"])
    rows = []
    for index, batch in enumerate(tables["settlements"], 1):
        allocated = by_batch[batch["id"]]
        issues = []
        for field, kind in (("reserve_held", "HELD"), ("reserve_released", "RELEASED")):
            if allocated[kind] != Decimal(batch[field]):
                issues.append(kind + "_COMPONENT_DIFFERENCE")
        if expected_net(batch) != Decimal(batch["amount"]):
            issues.append("PROCESSOR_NET_ARITHMETIC_DIFFERENCE")
        rows.append(
            {
                "id": f"reserve-batch-{index}",
                "kind": "BATCH_RESERVE_CONTROL",
                "source_settlement_id": batch["id"],
                **dict(zip(("merchant", "processor", "currency"), party(batch), strict=True)),
                "batch": batch["batch"],
                "reported_held": batch["reserve_held"],
                "reported_released": batch["reserve_released"],
                "dated_held": str(allocated["HELD"]),
                "dated_released": str(allocated["RELEASED"]),
                "differences": {
                    "held": str(allocated["HELD"] - Decimal(batch["reserve_held"])),
                    "released": str(allocated["RELEASED"] - Decimal(batch["reserve_released"])),
                    "net": str(Decimal(batch["amount"]) - expected_net(batch)),
                },
                "issues": issues,
                "state": issues[0] if issues else "MATCHED",
            }
        )
    ledger_expectations: defaultdict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"opening": Decimal(0), "closing": Decimal(0), "balance_ids": []}
    )
    keys = set(balances) | set(by_party) | {party(row) for row in tables["settlements"]}
    for index, key in enumerate(sorted(keys), 1):
        position = balances.get(key)
        moves = sorted(by_party[key], key=lambda row: (row["date"], row["sequence"]))
        current = Decimal(position["opening_balance"]) if position is not None else None
        issues = [] if position is not None else ["RESERVE_BALANCE_MISSING"]
        trace = []
        for movement in moves:
            change = Decimal(movement["amount"]) * (1 if movement["kind"] == "HELD" else -1)
            if current is not None:
                current += change
                if current < 0 and "RELEASE_EXCEEDS_AVAILABLE_RESERVE" not in issues:
                    issues.append("RELEASE_EXCEEDS_AVAILABLE_RESERVE")
            trace.append(
                {
                    **{
                        field: movement[field]
                        for field in (
                            "id",
                            "settlement_id",
                            "date",
                            "sequence",
                            "kind",
                            "amount",
                            "reference",
                            "evidence_reference",
                        )
                    },
                    "balance_after": str(current) if current is not None else None,
                }
            )
        difference = (
            Decimal(position["closing_balance"]) - current
            if position is not None and current is not None
            else None
        )
        if difference is not None and difference != 0:
            issues.append("RESERVE_ROLLFORWARD_DIFFERENCE")
        if position is not None:
            bucket = ledger_expectations[(position["ledger_account"], key[2])]
            bucket["opening"] += Decimal(position["opening_balance"])
            bucket["closing"] += Decimal(position["closing_balance"])
            bucket["balance_ids"].append(position["id"])
        rows.append(
            {
                "id": f"reserve-position-{index}",
                "kind": "RESERVE_POSITION",
                **dict(zip(("merchant", "processor", "currency"), key, strict=True)),
                "source_balance_id": position["id"] if position else None,
                "ledger_account": position["ledger_account"] if position else None,
                "opening_balance": position["opening_balance"] if position else None,
                "computed_closing": str(current) if current is not None else None,
                "reported_closing": position["closing_balance"] if position else None,
                "closing_difference": str(difference) if difference is not None else None,
                "differences": {"closing": str(difference) if difference is not None else None},
                "movement_ids": [row["id"] for row in moves],
                "movement_trace": trace,
                "issues": issues,
                "state": issues[0] if issues else "MATCHED",
            }
        )
    opening_date = (data.period_start - timedelta(days=1)).isoformat()
    closing_date = data.as_of.isoformat()
    ledger = {}
    for row in tables["ledger"]:
        account = row["account"], row["currency"]
        key = (*account, row["as_of"])
        if (
            account not in ledger_expectations
            or row["side"] != "receivable"
            or row["as_of"] not in {opening_date, closing_date}
            or Decimal(row["amount"]) < 0
        ):
            raise ValueError(
                "Ledger controls must be non-negative reserve receivables for declared accounts and exact opening/closing dates"
            )
        if key in ledger:
            raise ValueError("Duplicate reserve ledger account/date control")
        ledger[key] = row
    for index, (key, amounts) in enumerate(sorted(ledger_expectations.items()), 1):
        issues = []
        differences, source_ids = {}, {}
        for label, when in (("opening", opening_date), ("closing", closing_date)):
            control = ledger.get((*key, when))
            delta = Decimal(control["amount"]) - amounts[label] if control is not None else None
            source_ids[label] = control["id"] if control is not None else None
            differences[label] = str(delta) if delta is not None else None
            if control is None:
                issues.append(label.upper() + "_LEDGER_CONTROL_MISSING")
            elif delta:
                issues.append(label.upper() + "_LEDGER_DIFFERENCE")
        rows.append(
            {
                "id": f"reserve-ledger-{index}",
                "kind": "LEDGER_CONTROL",
                "account": key[0],
                "currency": key[1],
                "source_balance_ids": amounts["balance_ids"],
                "processor_opening": str(amounts["opening"]),
                "processor_closing": str(amounts["closing"]),
                "ledger_difference": differences,
                "differences": differences,
                "ledger_source_ids": source_ids,
                "issues": issues,
                "state": issues[0] if issues else "MATCHED",
            }
        )
    rows.sort(
        key=lambda row: {"RESERVE_POSITION": 0, "LEDGER_CONTROL": 1, "BATCH_RESERVE_CONTROL": 2}[
            row["kind"]
        ]
    )
    return {
        **result(
            rows,
            any(row["issues"] for row in rows),
            [
                "Dated component allocations and declared statement order only; no processor authentication or bank receipt is established",
                "GL comparisons use explicitly assessed reserve receivable accounts and original currency; no FX, impairment, tax recovery or legal entitlement is computed",
                "Opening/closing and held/released controls are independent; equal net changes cannot hide missing components",
                "No journal, payout instruction, cash reservation or reserve ownership confirmation is created",
            ],
        ),
        "merchant_reserve_contract": CONTRACT,
        "reserve_control_receipts": {
            role: sources[role]["merchant_reserve_controls"] for role in ("movements", "balances")
        },
        "period_start": data.period_start.isoformat(),
        "currency": data.currency,
        "payment_state": "NOT_ASSESSED_BY_RESERVE_ROLLFORWARD",
    }
