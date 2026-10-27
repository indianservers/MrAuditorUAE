"""Assessed inventory valuation evidence and recorded GL controls, not an opinion."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from typing import Annotated, Any
from uuid import UUID

from pydantic import Field, model_validator

from app.modules.country_workflows.audit_calculations import result
from app.modules.country_workflows.inventory_controls import stock_key, verify_quantity_controls
from app.modules.jurisdictions.profiles import Strict

Value = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]
ControlValue = Annotated[Decimal, Field(max_digits=64, decimal_places=16, allow_inf_nan=False)]
Identifier = Annotated[str, Field(min_length=1, max_length=120)]


class InventoryValuation(Strict):
    id: Identifier
    site: Identifier
    sku: Identifier
    lot: str = Field(default="", max_length=120)
    uom: Identifier
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    as_of: date
    quantity: Value = Field(ge=0)
    assessed_unit_cost: Value = Field(ge=0)
    selling_unit_price: Value = Field(ge=0)
    completion_unit_cost: Value = Field(ge=0)
    selling_unit_cost: Value = Field(ge=0)
    cost_observation_date: date
    nrv_observation_date: date
    cost_evidence_version_id: UUID
    cost_source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    nrv_evidence_version_id: UUID
    nrv_source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    cost_reference: Identifier
    nrv_reference: Identifier
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def exact(self):
        for value in (
            self.id,
            self.site,
            self.sku,
            self.uom,
            self.cost_reference,
            self.nrv_reference,
            self.assessment,
        ):
            if not value.strip() or value != value.strip():
                raise ValueError(
                    "Inventory valuation identities and assessments require exact nonblank text"
                )
        if self.lot != self.lot.strip():
            raise ValueError("Retain exact inventory lot identity")
        return self


class InventoryValueControl(Strict):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    expected_rows: int = Field(ge=1, le=5000, strict=True)
    cost_value: ControlValue = Field(ge=0)
    nrv_value: ControlValue


def unit_nrv(row):
    return (
        Decimal(row["selling_unit_price"])
        - Decimal(row["completion_unit_cost"])
        - Decimal(row["selling_unit_cost"])
    )


def verify_controls(rows, controls):
    declared = {
        item.currency: item
        for item in (InventoryValueControl.model_validate(control) for control in controls)
    }
    if len(declared) != len(controls):
        raise ValueError("Duplicate inventory valuation currency controls")
    actual: dict[str, dict[str, Any]] = {}
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for row in rows:
            group = actual.setdefault(
                row["currency"],
                {"expected_rows": 0, "cost_value": Decimal(0), "nrv_value": Decimal(0)},
            )
            group["expected_rows"] += 1
            quantity = Decimal(row["quantity"])
            group["cost_value"] += quantity * Decimal(row["assessed_unit_cost"])
            group["nrv_value"] += quantity * unit_nrv(row)
        if actual.keys() != declared.keys() or any(
            any(getattr(declared[currency], field) != value for field, value in group.items())
            for currency, group in actual.items()
        ):
            raise ValueError(
                "Independent inventory valuation row, extended-cost and extended-NRV controls do not agree for every currency"
            )
    return {
        currency: {
            field: value if field == "expected_rows" else str(value)
            for field, value in group.items()
        }
        for currency, group in actual.items()
    }


def documents(rows):
    return [
        {
            "source_evidence_version_id": row[prefix + "_evidence_version_id"],
            "source_sha256": row[prefix + "_source_sha256"],
        }
        for row in rows
        for prefix in ("cost", "nrv")
    ]


def compare(data, sources):
    tables = {role: source["rows"] for role, source in sources.items()}
    if not tables["books"] and not tables["valuations"]:
        raise ValueError(
            "Select an explicit inventory population; nil inventory requires a separate evidenced assessment"
        )
    book_source = sources["books"]
    if (
        not book_source.get("inventory_controls_verified")
        or book_source.get("inventory_quantity_controls") is None
    ):
        raise ValueError(
            "Inventory valuation requires independent book quantity controls for every partition"
        )
    verify_quantity_controls(tables["books"], book_source["inventory_quantity_controls"])
    valuations = sources["valuations"]
    if valuations.get("inventory_valuation_controls") is None:
        raise ValueError("Inventory valuation requires independent evidence value controls")
    verify_controls(tables["valuations"], valuations["inventory_valuation_controls"])
    keyed: dict[str, dict[tuple, dict[str, Any]]] = {}
    for role in ("books", "valuations"):
        keyed[role] = {stock_key(row): row for row in tables[role]}
        if len(keyed[role]) != len(tables[role]):
            raise ValueError("Duplicate inventory valuation site/SKU/lot/UOM/currency partition")
    controls = {}
    for row in tables["controls"]:
        key = row["account"], row["currency"]
        if key in controls or date.fromisoformat(row["as_of"]) != data.as_of:
            raise ValueError(
                "Retain unique inventory account/currency GL controls at the reporting date"
            )
        controls[key] = row
    rows: list[dict[str, Any]] = []
    recorded: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    incomplete: set[tuple[str, str]] = set()
    blocked = False
    for index, identity in enumerate(sorted(keyed["books"].keys() | keyed["valuations"].keys()), 1):
        book, assessment = (keyed[role].get(identity) for role in ("books", "valuations"))
        issues = (["MISSING_BOOK_POSITION"] if book is None else []) + (
            ["MISSING_VALUATION_EVIDENCE"] if assessment is None else []
        )
        hard = bool(issues)
        book_quantity = Decimal(book["quantity"]) if book else None
        observed_nrv = unit_nrv(assessment) if assessment else None
        recorded_unit = None
        if book:
            book_quantity = Decimal(book["quantity"])
            if not book.get("account"):
                issues.append("MISSING_INVENTORY_ACCOUNT")
                hard = True
            if book["ownership"] != "owned":
                issues.append("OWNERSHIP_NOT_CONFIRMED")
                hard = True
            if book_quantity < 0:
                issues.append("NEGATIVE_BOOK_QUANTITY")
                hard = True
            if date.fromisoformat(book["count_date"]) != data.as_of:
                issues.append("BOOK_REPORTING_DATE_DIFFERENCE")
                hard = True
            if book["condition"] != "good":
                issues.append("BOOK_CONDITION_REQUIRES_REVIEW")
            recorded_unit = Decimal(book["unit_cost"])
            if data.inventory_gl_basis == "recorded-lower-of-cost-nrv":
                if book["unit_nrv"] is None:
                    issues.append("RECORDED_NRV_MISSING")
                    hard = True
                    recorded_unit = None
                else:
                    recorded_unit = min(recorded_unit, Decimal(book["unit_nrv"]))
            if book.get("account"):
                account_key = book["account"], book["currency"]
                if recorded_unit is None:
                    incomplete.add(account_key)
                else:
                    recorded[account_key] += book_quantity * recorded_unit
        if assessment:
            if date.fromisoformat(assessment["as_of"]) != data.as_of or any(
                date.fromisoformat(assessment[field]) > data.review_through
                for field in ("cost_observation_date", "nrv_observation_date")
            ):
                raise ValueError(
                    "Inventory valuation assessment date or observation date is outside the declared review scope"
                )
            if unit_nrv(assessment) < 0:
                issues.append("NEGATIVE_NRV_REQUIRES_SEPARATE_ASSESSMENT")
                hard = True
        comparable = (
            book is not None
            and assessment is not None
            and Decimal(assessment["quantity"]) == book_quantity
            and book_quantity >= 0
        )
        if book and assessment and not comparable:
            issues.append("VALUATION_QUANTITY_DIFFERENCE")
            hard = True
        cost_delta = nrv_delta = expected = None
        if comparable and book is not None and assessment is not None:
            cost_delta = Decimal(book["unit_cost"]) - Decimal(assessment["assessed_unit_cost"])
            nrv = unit_nrv(assessment)
            nrv_delta = Decimal(book["unit_nrv"]) - nrv if book["unit_nrv"] is not None else None
            if cost_delta != 0:
                issues.append("UNIT_COST_DIFFERENCE")
            if book["unit_nrv"] is None:
                issues.append("BOOK_NRV_NOT_RECORDED")
            elif nrv_delta != 0:
                issues.append("UNIT_NRV_DIFFERENCE")
            if nrv >= 0:
                expected = Decimal(book["quantity"]) * min(
                    Decimal(assessment["assessed_unit_cost"]), nrv
                )
                if Decimal(book["quantity"]) > 0 and nrv < Decimal(
                    assessment["assessed_unit_cost"]
                ):
                    issues.append("NRV_BELOW_ASSESSED_COST")
        book_value = (
            book_quantity * recorded_unit
            if recorded_unit is not None and book_quantity is not None
            else None
        )
        rows.append(
            {
                "id": f"inventory-valuation:{index}",
                "kind": "valuation-test",
                "site": identity[0],
                "sku": identity[1],
                "uom": identity[2],
                "currency": identity[3],
                "lot": identity[4],
                "account": book.get("account") if book else None,
                "books_source_row_id": book["id"] if book else None,
                "book_ownership": book["ownership"] if book else None,
                "book_condition": book["condition"] if book else None,
                "book_date": book["count_date"] if book else None,
                "valuation_source_row_id": assessment["id"] if assessment else None,
                "book_quantity": book["quantity"] if book else None,
                "assessment_quantity": assessment["quantity"] if assessment else None,
                "book_unit_cost": book["unit_cost"] if book else None,
                "assessed_unit_cost": assessment["assessed_unit_cost"] if assessment else None,
                "book_unit_nrv": book["unit_nrv"] if book else None,
                "assessed_unit_nrv": str(observed_nrv) if observed_nrv is not None else None,
                "unit_cost_difference": str(cost_delta) if cost_delta is not None else None,
                "unit_nrv_difference": str(nrv_delta) if nrv_delta is not None else None,
                "recorded_gl_basis_value": str(book_value) if book_value is not None else None,
                "assessed_lower_cost_nrv_value": str(expected) if expected is not None else None,
                "recorded_minus_assessed_value": str(book_value - expected)
                if book_value is not None and expected is not None
                else None,
                "valuation_evidence": assessment,
                "exceptions": issues,
                "state": "EXCEPTIONS" if issues else "MATCHED",
            }
        )
        blocked |= hard
    for index, key in enumerate(sorted(recorded.keys() | incomplete | controls.keys()), 1):
        control = controls.get(key)
        complete = key in recorded and key not in incomplete
        difference = Decimal(control["amount"]) - recorded[key] if control and complete else None
        state = (
            "MISSING_OR_INCOMPLETE_BOOK_CONTROL"
            if not complete
            else "MISSING_GL_CONTROL"
            if not control
            else "INCOMPLETE_GL_COMPARISON"
            if difference is None
            else "GL_CONTROL_DIFFERENCE"
            if abs(difference) > data.tolerance
            else "MATCHED"
        )
        blocked |= state != "MATCHED"
        rows.append(
            {
                "id": f"inventory-gl:{index}",
                "kind": "gl-control",
                "account": key[0],
                "currency": key[1],
                "recorded_book_value": str(recorded[key]) if complete else None,
                "gl_amount": control["amount"] if control else None,
                "difference": str(difference) if difference is not None else None,
                "gl_source_row_id": control["id"] if control else None,
                "state": state,
            }
        )
    return {
        **result(
            rows,
            blocked,
            [
                "Assessed cost and selling/completion/selling-cost inputs require independent source interpretation and applicable framework selection; no FIFO/weighted-average policy or legal eligibility is inferred",
                "GL controls compare the explicitly selected recorded basis; assessed price differences are separate tests and are not automatically posted",
                "No physical verification, ownership assurance, title confirmation, drawing-power calculation, or inventory audit opinion is issued",
                "Negative NRV remains unresolved; no automatic floor, liability or onerous-contract treatment is inferred",
                "Document hashes and declared references establish retained evidence identity, not publisher authenticity or source interpretation",
                "Every site/SKU/lot/UOM/currency position and account/currency control stays separate; no unit or currency conversion is inferred",
            ],
        ),
        "inventory_valuation_contract": "inventory-valuation-control/1",
        "inventory_valuation_scope": {
            "as_of": data.as_of.isoformat(),
            "review_through": data.review_through.isoformat(),
            "gl_basis": data.inventory_gl_basis,
            "assessment": data.inventory_scope_assessment,
        },
    }
