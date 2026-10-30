"""FIFO arithmetic on assessed opening/receipt/issue evidence, not a valuation opinion."""

import re
from collections import defaultdict, deque
from datetime import date
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.modules.country_workflows.audit_calculations import result
from app.modules.country_workflows.inventory_controls import stock_key, verify_quantity_controls
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "inventory-fifo-cost/1"
Value = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]
Total = Annotated[Decimal, Field(max_digits=64, decimal_places=16, allow_inf_nan=False)]
Identifier = Annotated[str, Field(min_length=1, max_length=120)]


class CostIdentity(Strict):
    site: Identifier
    sku: Identifier
    lot: str = Field(default="", max_length=120)
    uom: Identifier
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def exact(self):
        if any(
            getattr(self, field) != getattr(self, field).strip()
            for field in ("site", "sku", "lot", "uom")
        ):
            raise ValueError("FIFO cost identities must be exact, without surrounding whitespace")
        return self


class CostMovement(CostIdentity):
    id: Identifier
    date: date
    sequence: int = Field(ge=0, le=1000000000, strict=True)
    kind: Literal["opening", "receipt", "issue"]
    quantity: Value = Field(gt=0)
    unit_cost: Value | None = Field(default=None, ge=0)
    source_evidence_version_id: UUID
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_reference: Identifier
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("date", mode="before")
    @classmethod
    def calendar_date(cls, value):
        if type(value) is date:
            return value
        if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return value
        raise ValueError("FIFO date requires an exact calendar date without a timestamp")

    @field_validator("sequence", mode="before")
    @classmethod
    def canonical_sequence(cls, value):
        if type(value) is int:
            return value
        if isinstance(value, str) and re.fullmatch(r"[0-9]{1,10}", value):
            return int(value)
        raise ValueError("FIFO sequence requires a nonnegative whole-number ordinal")

    @model_validator(mode="after")
    def cost_basis(self):
        if (self.kind == "issue") != (self.unit_cost is None):
            raise ValueError(
                "Opening/receipt rows need assessed unit cost; issue cost must be calculated by FIFO"
            )
        if any(
            value != value.strip() or not value.strip()
            for value in (self.id, self.evidence_reference, self.assessment)
        ):
            raise ValueError("Retain exact nonblank movement references and assessments")
        return self


class CostControl(CostIdentity):
    expected_rows: int = Field(ge=1, le=5000, strict=True)
    opening_quantity: Value = Field(ge=0)
    receipt_quantity: Value = Field(ge=0)
    issue_quantity: Value = Field(ge=0)
    opening_cost: Total = Field(ge=0)
    receipt_cost: Total = Field(ge=0)
    rounding_places: int = Field(ge=0, le=8, strict=True)
    rounding_method: Literal["HALF_UP", "HALF_EVEN"]


def verify_controls(rows, controls):
    if not 1 <= len(rows) <= 5000 or not 1 <= len(controls) <= 5000:
        raise ValueError("FIFO requires between 1 and 5000 movements and control partitions")
    declared = {
        stock_key(item.model_dump()): item
        for item in (CostControl.model_validate(x) for x in controls)
    }
    if len(declared) != len(controls):
        raise ValueError("Duplicate FIFO control partition")
    actual: dict[tuple, dict[str, Any]] = {}
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for row in rows:
            values = actual.setdefault(
                stock_key(row),
                {
                    "expected_rows": 0,
                    "opening_quantity": Decimal(0),
                    "receipt_quantity": Decimal(0),
                    "issue_quantity": Decimal(0),
                    "opening_cost": Decimal(0),
                    "receipt_cost": Decimal(0),
                },
            )
            values["expected_rows"] += 1
            values[row["kind"] + "_quantity"] += Decimal(row["quantity"])
            if row["kind"] != "issue":
                values[row["kind"] + "_cost"] += Decimal(row["quantity"]) * Decimal(
                    row["unit_cost"]
                )
        if actual.keys() != declared.keys() or any(
            any(getattr(declared[key], field) != value for field, value in group.items())
            for key, group in actual.items()
        ):
            raise ValueError(
                "Independent FIFO row, directional quantity and opening/receipt value controls do not agree for every partition"
            )
    return declared


def documents(rows):
    return [
        {
            "source_evidence_version_id": row["source_evidence_version_id"],
            "source_sha256": row["source_sha256"],
        }
        for row in rows
    ]


def compare(data, sources):
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        return _compare(data, sources)


def _compare(data, sources):
    movements = sources["movements"]
    if movements.get("inventory_fifo_controls") is None or not movements["rows"]:
        raise ValueError("FIFO requires a nonempty independently controlled movement population")
    controls = verify_controls(movements["rows"], movements["inventory_fifo_controls"])
    books = sources["books"]
    if (
        not books.get("inventory_controls_verified")
        or books.get("inventory_quantity_controls") is None
    ):
        raise ValueError("FIFO closing books require independent quantity controls")
    verify_quantity_controls(books["rows"], books["inventory_quantity_controls"])
    keyed = {stock_key(row): row for row in books["rows"]}
    if len(keyed) != len(books["rows"]):
        raise ValueError("Duplicate FIFO closing book partition")
    grouped = defaultdict(list)
    for row in movements["rows"]:
        if not data.period_start <= date.fromisoformat(row["date"]) <= data.as_of:
            raise ValueError("FIFO movement dates must remain inside the declared cost period")
        if row["kind"] == "opening" and date.fromisoformat(row["date"]) != data.period_start:
            raise ValueError(
                "Opening layers must be dated at the explicit period start; sequence retains their assessed FIFO order"
            )
        grouped[stock_key(row)].append(row)
    positions, allocations, events, closing_layers = [], [], [], []
    blocked = False
    for index, key in enumerate(sorted(grouped.keys() | keyed.keys()), 1):
        book = keyed.get(key)
        control = controls.get(key)
        layers: deque[dict[str, Any]] = deque()
        seen = set()
        traded = False
        incomplete = False
        issue_cost = Decimal(0)
        issues = []
        for row in sorted(grouped.get(key, []), key=lambda item: (item["date"], item["sequence"])):
            order = row["date"], row["sequence"]
            if order in seen:
                raise ValueError("FIFO date/sequence is ambiguous within a partition")
            seen.add(order)
            if row["kind"] == "opening" and traded:
                raise ValueError("Opening FIFO layers cannot follow period transactions")
            traded |= row["kind"] != "opening"
            quantity = Decimal(row["quantity"])
            covered_cost = Decimal(0)
            missing = Decimal(0)
            if row["kind"] != "issue":
                layers.append(
                    {
                        "source_row_id": row["id"],
                        "remaining": quantity,
                        "unit_cost": Decimal(row["unit_cost"]),
                    }
                )
                covered_cost = quantity * Decimal(row["unit_cost"])
            else:
                remaining = quantity
                while remaining and layers:
                    layer = layers[0]
                    taken = min(remaining, layer["remaining"])
                    cost = taken * layer["unit_cost"]
                    allocations.append(
                        {
                            "site": key[0],
                            "sku": key[1],
                            "uom": key[2],
                            "currency": key[3],
                            "lot": key[4],
                            "issue_source_row_id": row["id"],
                            "layer_source_row_id": layer["source_row_id"],
                            "quantity": str(taken),
                            "unit_cost": str(layer["unit_cost"]),
                            "cost": str(cost),
                        }
                    )
                    covered_cost += cost
                    remaining -= taken
                    layer["remaining"] -= taken
                    if not layer["remaining"]:
                        layers.popleft()
                missing = remaining
                incomplete |= missing > 0
                issue_cost += covered_cost
            events.append(
                {
                    "source_row_id": row["id"],
                    "site": key[0],
                    "sku": key[1],
                    "uom": key[2],
                    "currency": key[3],
                    "lot": key[4],
                    "date": row["date"],
                    "sequence": row["sequence"],
                    "kind": row["kind"],
                    "quantity": row["quantity"],
                    "covered_cost": str(covered_cost),
                    "unallocated_issue_quantity": str(missing),
                    "state": "INCOMPLETE" if missing else "CALCULATED",
                    "evidence_reference": row["evidence_reference"],
                }
            )
        if incomplete:
            issues.append("ISSUE_WITHOUT_AVAILABLE_COST_LAYERS")
        if control is None:
            issues.append("MISSING_MOVEMENT_POPULATION")
        if book is None:
            issues.append("MISSING_CLOSING_BOOK_POSITION")
        expected_quantity = (
            control.opening_quantity + control.receipt_quantity - control.issue_quantity
            if control
            else None
        )
        raw_cost = (
            sum((layer["remaining"] * layer["unit_cost"] for layer in layers), Decimal(0))
            if not incomplete and control
            else None
        )
        for layer in layers:
            closing_layers.append(
                {
                    "position_id": f"fifo:{index}",
                    "site": key[0],
                    "sku": key[1],
                    "uom": key[2],
                    "currency": key[3],
                    "lot": key[4],
                    "layer_source_row_id": layer["source_row_id"],
                    "remaining_quantity": str(layer["remaining"]),
                    "unit_cost": str(layer["unit_cost"]),
                    "remaining_cost": str(layer["remaining"] * layer["unit_cost"]),
                    "basis": "INCOMPLETE_PROVISIONAL" if incomplete else "FIFO_CLOSING_COST",
                }
            )
        rounded_cost = book_cost = difference = raw_book_cost = None
        if book:
            if (
                date.fromisoformat(book["count_date"]) != data.as_of
                or book["ownership"] != "owned"
                or Decimal(book["quantity"]) < 0
            ):
                issues.append("BOOK_DATE_OWNERSHIP_OR_QUANTITY_REQUIRES_REVIEW")
            if expected_quantity is not None and Decimal(book["quantity"]) != expected_quantity:
                issues.append("CLOSING_QUANTITY_DIFFERENCE")
        if control and raw_cost is not None:
            quantum = Decimal(1).scaleb(-control.rounding_places)
            rounding = ROUND_HALF_UP if control.rounding_method == "HALF_UP" else ROUND_HALF_EVEN
            rounded_cost = raw_cost.quantize(quantum, rounding=rounding)
            if book:
                raw_book_cost = Decimal(book["quantity"]) * Decimal(book["unit_cost"])
                book_cost = raw_book_cost.quantize(quantum, rounding=rounding)
                difference = book_cost - rounded_cost
                if difference != 0:
                    issues.append("FIFO_GROSS_COST_DIFFERENCE")
        blocked |= bool(issues)
        positions.append(
            {
                "id": f"fifo:{index}",
                "site": key[0],
                "sku": key[1],
                "uom": key[2],
                "currency": key[3],
                "lot": key[4],
                "books_source_row_id": book["id"] if book else None,
                "expected_closing_quantity": str(expected_quantity)
                if expected_quantity is not None
                else None,
                "book_quantity": book["quantity"] if book else None,
                "raw_fifo_closing_cost": str(raw_cost) if raw_cost is not None else None,
                "covered_issue_cost": str(issue_cost),
                "raw_cost_rollforward_difference": str(
                    control.opening_cost + control.receipt_cost - issue_cost - raw_cost
                )
                if control and raw_cost is not None
                else None,
                "raw_book_gross_cost": str(raw_book_cost) if raw_book_cost is not None else None,
                "fifo_rounding_difference": str(rounded_cost - raw_cost)
                if rounded_cost is not None and raw_cost is not None
                else None,
                "book_rounding_difference": str(book_cost - raw_book_cost)
                if book_cost is not None and raw_book_cost is not None
                else None,
                "rounded_fifo_closing_cost": str(rounded_cost)
                if rounded_cost is not None
                else None,
                "rounded_book_gross_cost": str(book_cost) if book_cost is not None else None,
                "book_minus_fifo": str(difference) if difference is not None else None,
                "rounding_places": control.rounding_places if control else None,
                "rounding_method": control.rounding_method if control else None,
                "exceptions": issues,
                "state": "EXCEPTIONS" if issues else "MATCHED",
            }
        )
    return {
        **result(
            positions,
            blocked,
            [
                "FIFO applies only to explicitly assessed opening layers, receipts and issues; opening sequence and cost inclusion require independent policy/source review",
                "Gross-cost arithmetic does not establish NRV, ownership, physical count, tax treatment, framework applicability or an inventory opinion",
                "Returns, transfers, production conversions, retrospective revaluations and negative-stock costing are not inferred by this profile",
                "Each site/SKU/lot/UOM/currency partition remains separate; no FX or unit conversion is inferred",
                "An issue without then-available layers remains unresolved; later receipts do not retroactively fill it",
            ],
        ),
        "inventory_fifo_contract": CONTRACT,
        "inventory_fifo_scope": {
            "period_start": data.period_start.isoformat(),
            "as_of": data.as_of.isoformat(),
            "assessment": data.inventory_scope_assessment,
        },
        "fifo_allocations": allocations,
        "fifo_event_costs": events,
        "fifo_closing_layers": closing_layers,
        "inventory_fifo_controls": movements["inventory_fifo_controls"],
    }
