"""Explicit gross-to-net merchant evidence, never inferred tax or payment execution."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.modules.country_workflows.audit_schemas import Currency, Identifier, Money
from app.modules.country_workflows.bank_dates import date_details
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "explicit-gross-net-bank/2"

COMPONENTS = (
    "sales",
    "refunds",
    "chargebacks",
    "fees",
    "fee_tax",
    "withholding",
    "reserve_held",
    "reserve_released",
    "amount",
)
ROLES = {
    "books": "merchant-activity",
    "processor": "merchant-settlements",
    "bank": "transactions",
    "allocations": "merchant-bank-allocations",
}


class MerchantActivity(Strict):
    id: Identifier
    merchant: Identifier
    processor: Identifier
    batch: Identifier
    reference: Identifier
    date: date
    currency: Currency
    kind: Literal["SALE", "REFUND", "CHARGEBACK"]
    amount: Money = Field(gt=0)
    evidence_reference: Identifier


class MerchantSettlement(Strict):
    id: Identifier
    merchant: Identifier
    processor: Identifier
    batch: Identifier
    currency: Currency
    period_start: date
    period_end: date
    settlement_date: date
    sales: Money = Field(ge=0)
    refunds: Money = Field(ge=0)
    chargebacks: Money = Field(ge=0)
    fees: Money = Field(ge=0)
    fee_tax: Money = Field(ge=0)
    withholding: Money = Field(ge=0)
    reserve_held: Money = Field(ge=0)
    reserve_released: Money = Field(ge=0)
    amount: Money
    tax_country: Literal["AE", "IN"]
    fee_tax_kind: Literal["UAE_VAT", "INDIA_GST", "FOREIGN_TAX", "NO_TAX_ASSESSED"]
    tax_assessment_reference: Identifier
    evidence_reference: Identifier
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def ordered(self):
        if not self.period_start <= self.period_end <= self.settlement_date:
            raise ValueError("Merchant activity period and settlement date must be ordered")
        if self.fee_tax_kind == "NO_TAX_ASSESSED" and self.fee_tax != 0:
            raise ValueError("No-tax assessment cannot carry fee tax")
        if len(self.assessment.strip()) < 10:
            raise ValueError("Retain a meaningful merchant tax/component assessment")
        return self


class MerchantAllocation(Strict):
    id: Identifier
    settlement_id: Identifier
    bank_transaction_id: Identifier
    currency: Currency
    amount: Money
    evidence_reference: Identifier
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("amount")
    @classmethod
    def nonzero(cls, value):
        if value == 0:
            raise ValueError("Merchant bank allocations must be explicitly nonzero")
        return value


ROW_TYPES: dict[str, type[Strict]] = {
    "merchant-activity": MerchantActivity,
    "merchant-settlements": MerchantSettlement,
    "merchant-bank-allocations": MerchantAllocation,
}


def verify_controls(rows, controls):
    currencies = {row["currency"] for row in rows}
    if set(controls) != currencies:
        raise ValueError(
            "Declare independent merchant component controls for every source currency"
        )
    for currency in currencies:
        if set(controls[currency]) != set(COMPONENTS):
            raise ValueError(
                "Merchant component controls must include every gross-to-net component"
            )
        for field in COMPONENTS:
            total = sum(
                (Decimal(row[field]) for row in rows if row["currency"] == currency), Decimal(0)
            )
            if total != Decimal(controls[currency][field]):
                raise ValueError("Merchant component control does not agree: " + field)


def identity(row):
    return row["merchant"], row["processor"], row["batch"], row["currency"]


def expected_net(row):
    return (
        Decimal(row["sales"])
        - sum(
            (
                Decimal(row[field])
                for field in (
                    "refunds",
                    "chargebacks",
                    "fees",
                    "fee_tax",
                    "withholding",
                    "reserve_held",
                )
            ),
            Decimal(0),
        )
        + Decimal(row["reserve_released"])
    )


def compare(data, sources, country):
    from app.modules.country_workflows.audit_calculations import result

    tables = {role: source["rows"] for role, source in sources.items()}
    verify_controls(
        tables["processor"], sources["processor"].get("merchant_component_controls", {})
    )
    if (
        sources["bank"].get("source_snapshot_id")
        or sources["bank"].get("parser_version") == "committed-ledger-1"
    ):
        raise ValueError(
            "Merchant settlement requires independent bank movements, not committed books"
        )
    batches, by_key = {}, {}
    for row in tables["processor"]:
        if row["currency"] != data.currency:
            raise ValueError(
                "Merchant processor currency differs from the selected settlement currency"
            )
        if identity(row) in by_key:
            raise ValueError("Duplicate merchant/processor/batch/currency settlement scope")
        if row["tax_country"] != country or row["fee_tax_kind"] not in {
            "FOREIGN_TAX",
            "NO_TAX_ASSESSED",
            "UAE_VAT" if country == "AE" else "INDIA_GST",
        }:
            raise ValueError("Merchant fee-tax assessment differs from the engagement country")
        if (
            not data.period_start
            <= date.fromisoformat(row["period_start"])
            <= date.fromisoformat(row["settlement_date"])
            <= data.as_of
        ):
            raise ValueError("Merchant settlement is outside the declared review period")
        batches[row["id"]] = row
        by_key[identity(row)] = row
    activity: dict[tuple, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    activity_ids = defaultdict(list)
    seen = set()
    for row in tables["books"]:
        key = identity(row)
        original = (*key, row["kind"], row["reference"])
        if original in seen:
            raise ValueError(
                "Duplicate original merchant activity reference within a batch and kind"
            )
        seen.add(original)
        batch = by_key.get(key)
        if batch is None:
            raise ValueError(
                "Book merchant activity has no independently reported settlement batch"
            )
        if not batch["period_start"] <= row["date"] <= batch["period_end"]:
            raise ValueError("Book merchant activity date falls outside its reported batch period")
        activity[key][row["kind"]] += Decimal(row["amount"])
        activity_ids[key].append(row["id"])
    bank = {}
    for row in tables["bank"]:
        if row["account"] != data.account or row["currency"] != data.currency:
            raise ValueError("Merchant bank source mixes accounts or currencies")
        if not data.period_start <= date.fromisoformat(row["date"]) <= data.as_of:
            raise ValueError("Merchant bank movement falls outside the declared review period")
        bank[row["id"]] = row
    allocated: dict[str, Decimal] = defaultdict(Decimal)
    bank_used: dict[str, Decimal] = defaultdict(Decimal)
    allocation_ids = defaultdict(list)
    pairs = set()
    for row in tables["allocations"]:
        batch, movement = batches.get(row["settlement_id"]), bank.get(row["bank_transaction_id"])
        if batch is None or movement is None:
            raise ValueError(
                "Merchant allocation references a missing exact settlement or bank row"
            )
        if movement.get("is_reversal") or date_details(movement)["booking_date_review_required"]:
            raise ValueError(
                "Merchant settlement requires unreversed booked-date evidence, not value-date fallback"
            )
        pair = (row["settlement_id"], row["bank_transaction_id"])
        amount = Decimal(row["amount"])
        if (
            pair in pairs
            or row["currency"] != batch["currency"]
            or row["currency"] != movement["currency"]
        ):
            raise ValueError("Duplicate merchant allocation pair or inconsistent currency")
        pairs.add(pair)
        if amount * Decimal(movement["amount"]) <= 0 or amount * Decimal(batch["amount"]) <= 0:
            raise ValueError("Merchant allocation must preserve the bank and settlement direction")
        if movement["date"] < batch["settlement_date"]:
            raise ValueError("Bank settlement precedes its declared processor settlement date")
        allocated[batch["id"]] += amount
        bank_used[movement["id"]] += amount
        allocation_ids[batch["id"]].append(row["id"])
        if abs(bank_used[movement["id"]]) > abs(Decimal(movement["amount"])) or abs(
            allocated[batch["id"]]
        ) > abs(Decimal(batch["amount"])):
            raise ValueError("Merchant allocation exceeds the bank movement or reported settlement")
    rows = []
    for batch in tables["processor"]:
        key = identity(batch)
        values = {field: Decimal(batch[field]) for field in COMPONENTS}
        expected = expected_net(batch)
        issues = []
        differences = {}
        for field, kind in (
            ("sales", "SALE"),
            ("refunds", "REFUND"),
            ("chargebacks", "CHARGEBACK"),
        ):
            difference = activity[key][kind] - values[field]
            differences[field] = str(difference)
            if difference:
                issues.append("BOOK_" + kind + "_DIFFERENCE")
        if expected != values["amount"]:
            issues.append("PROCESSOR_NET_ARITHMETIC_DIFFERENCE")
        if allocated[batch["id"]] != values["amount"]:
            issues.append("BANK_SETTLEMENT_DIFFERENCE")
        rows.append(
            {
                **batch,
                "kind": "MERCHANT_SETTLEMENT",
                "book_activity_ids": activity_ids[key],
                "allocation_ids": allocation_ids[batch["id"]],
                "book_differences": differences,
                "expected_net": str(expected),
                "net_arithmetic_difference": str(values["amount"] - expected),
                "bank_allocated": str(allocated[batch["id"]]),
                "bank_difference": str(values["amount"] - allocated[batch["id"]]),
                "issues": issues,
                "state": "SETTLEMENT_DIFFERENCE" if issues else "MATCHED",
            }
        )
    for movement in tables["bank"]:
        residual = Decimal(movement["amount"]) - bank_used[movement["id"]]
        if residual:
            rows.append(
                {
                    "id": "bank-residual:" + movement["id"],
                    "kind": "BANK_RESIDUAL",
                    "bank_transaction_id": movement["id"],
                    "currency": movement["currency"],
                    "amount": str(residual),
                    "state": "UNALLOCATED_BANK_MOVEMENT",
                }
            )
    receipt = result(
        rows,
        any(row["state"] != "MATCHED" for row in rows),
        [
            "Gross sales, refunds and chargebacks are compared separately; no amount-only or inferred bank allocation",
            "Fee tax, withholding and reserves are assessed source components; no statutory rate, recovery eligibility, credit entitlement or reserve roll-forward is calculated",
            "Bank amounts use credit-positive signed movements. Independent approval checks shared capacity against active merchant and obligation allocations within this tenant legal entity; calculations do not reserve cash or execute payments or journals",
            "Uploaded source controls do not establish complete merchant populations or authenticate processor/bank evidence",
        ],
    )
    receipt["merchant_settlement_contract"] = CONTRACT
    receipt["transaction_dates"] = [
        {"source_role": "bank", "source_row_id": movement["id"], **date_details(movement)}
        for movement in tables["bank"]
    ]
    receipt["bank_authentication_status"] = "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON"
    return receipt
