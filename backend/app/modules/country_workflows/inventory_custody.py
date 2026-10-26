"""Explicit offsite custody quantities and retained correspondence; never title assurance."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.modules.country_workflows.audit_calculations import result
from app.modules.country_workflows.audit_schemas import Identifier
from app.modules.jurisdictions.profiles import Strict

Quantity = Annotated[Decimal, Field(ge=0, max_digits=28, decimal_places=8, allow_inf_nan=False)]
SHA = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
FIELDS = ("custodian", "site", "sku", "lot", "uom")


class CustodyScope(Strict):
    custodian: Identifier
    site: Identifier
    sku: Identifier
    lot: str = Field(default="", max_length=120)
    uom: Identifier

    @model_validator(mode="after")
    def exact(self):
        for field in (*FIELDS, "id", "position_id"):
            value = getattr(self, field, None)
            if value is not None and (value != value.strip() or (field != "lot" and not value)):
                raise ValueError(
                    "Custody position identifiers and units must be exact nonblank values"
                )
        return self


class CustodyPosition(CustodyScope):
    id: Identifier
    as_of: date
    quantity: Quantity
    ownership: Literal["entity-owned", "third-party-owned", "unconfirmed"]
    title_reference: Identifier


class CustodyQuantityControl(CustodyScope):
    position_id: Identifier
    quantity: Quantity
    response_quantity: Quantity | None = None


class CustodyConfirmation(CustodyScope):
    id: Identifier
    position_id: Identifier
    as_of: date
    requested_quantity: Quantity
    response_quantity: Quantity | None = None
    status: Literal["received", "disputed", "pending", "undeliverable", "unreliable"]
    condition: (
        Literal["good", "damaged", "obsolete", "expired", "unknown", "not-applicable"] | None
    ) = None
    held_for_entity: Literal["yes", "no", "unknown", "none-held"] = "unknown"
    requested_on: date
    responded_on: date | None = None
    contact_verified: bool = False
    independently_received: bool = False
    request_evidence_version_id: UUID
    request_source_sha256: SHA
    request_reference: Identifier
    response_evidence_version_id: UUID | None = None
    response_source_sha256: SHA | None = None
    response_reference: str = Field(default="", max_length=120)
    followup_evidence_version_id: UUID | None = None
    followup_source_sha256: SHA | None = None
    followup_kind: Literal["alternative-procedures", "exception-investigation"] | None = None
    followup_on: date | None = None
    followup_reference: str = Field(default="", max_length=120)
    followup_assessment: str = Field(default="", max_length=2000)
    scope_assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def correspondence(self):
        for value in (
            self.request_reference,
            self.response_reference,
            self.followup_reference,
            self.scope_assessment,
            self.followup_assessment,
        ):
            if value != value.strip():
                raise ValueError("Custody document references and assessments require exact text")
        if len(self.scope_assessment.strip()) < 10:
            raise ValueError("Record the custody quantity and condition scope assessment")
        for prefix in ("response", "followup"):
            if bool(getattr(self, prefix + "_evidence_version_id")) != bool(
                getattr(self, prefix + "_source_sha256")
            ):
                raise ValueError("Each custody document needs its retained version and SHA-256")
        written = self.status in {"received", "disputed", "unreliable"}
        if written:
            if (
                self.response_quantity is None
                or self.condition is None
                or not self.responded_on
                or not self.response_evidence_version_id
                or not self.response_reference
                or self.responded_on < max(self.requested_on, self.as_of)
            ):
                raise ValueError(
                    "A written custody response requires quantity, condition, date, retained document and reference"
                )
        elif any(
            (
                self.response_quantity is not None,
                self.condition is not None,
                self.responded_on is not None,
                self.response_evidence_version_id is not None,
                bool(self.response_reference),
                self.independently_received,
                self.held_for_entity != "unknown",
            )
        ):
            raise ValueError(
                "An unanswered custody request cannot carry written-response assertions"
            )
        if (
            self.held_for_entity == "none-held" or self.condition == "not-applicable"
        ) and self.response_quantity != 0:
            raise ValueError(
                "None-held custody and not-applicable condition require an explicit written zero quantity"
            )
        if self.followup_evidence_version_id:
            required_kind = (
                "alternative-procedures"
                if self.status in {"pending", "undeliverable", "unreliable"}
                else "exception-investigation"
            )
            if (
                self.followup_kind != required_kind
                or not self.followup_on
                or self.followup_on < (self.responded_on or self.requested_on)
                or not self.followup_reference
                or len(self.followup_assessment.strip()) < 10
            ):
                raise ValueError(
                    "Retained custody follow-up needs dated appropriate procedures, reference and assessment"
                )
        elif any(
            (
                self.followup_kind,
                self.followup_on,
                self.followup_reference,
                self.followup_assessment,
            )
        ):
            raise ValueError("Custody follow-up assertions require retained evidence")
        return self


def key(row):
    return tuple(row[field] for field in FIELDS)


def verify_controls(rows, controls, *, responses=False):
    if controls is None:
        raise ValueError(
            "Declare independent custody quantity controls for every position and unit"
        )
    actual = {}
    physical = set()
    for row in rows:
        identifier = row["position_id"] if responses else row["id"]
        if identifier in actual or key(row) in physical:
            raise ValueError(
                "Select one current custody position/response per custodian, site, SKU, lot and unit"
            )
        physical.add(key(row))
        actual[identifier] = (
            *key(row),
            Decimal(row["requested_quantity"] if responses else row["quantity"]),
            Decimal(row["response_quantity"])
            if responses and row["response_quantity"] is not None
            else None,
        )
    declared = {}
    for control in controls:
        if control["position_id"] in declared:
            raise ValueError("Duplicate custody quantity control position")
        declared[control["position_id"]] = (
            *key(control),
            Decimal(control["quantity"]),
            Decimal(control["response_quantity"])
            if control.get("response_quantity") is not None
            else None,
        )
    if actual != declared:
        raise ValueError(
            "Custody quantity controls must match every exact position, unit, request and actual response"
        )


def compare(data, sources):
    books, replies = sources["positions"], sources["responses"]
    for source, responses in ((books, False), (replies, True)):
        verify_controls(
            source["rows"], source.get("custody_quantity_controls"), responses=responses
        )
    positions = {row["id"]: row for row in books["rows"]}
    letters = {row["position_id"]: row for row in replies["rows"]}
    rows = []
    blocked = False
    for index, identifier in enumerate(sorted(positions.keys() | letters.keys()), 1):
        position, letter = positions.get(identifier), letters.get(identifier)
        state, hard, difference = "CUSTODY_RESPONSE_MISSING", True, None
        if position and date.fromisoformat(position["as_of"]) != data.as_of:
            raise ValueError("Custody book positions must use the reporting date")
        if position is None:
            state = "UNKNOWN_CUSTODY_POSITION"
        elif letter:
            in_scope = (
                key(position) == key(letter)
                and letter["as_of"] == data.as_of.isoformat()
                and Decimal(letter["requested_quantity"]) == Decimal(position["quantity"])
            )
            in_window = all(
                not letter.get(field) or date.fromisoformat(letter[field]) <= data.review_through
                for field in ("requested_on", "responded_on", "followup_on")
            )
            if not in_scope:
                state = "CUSTODY_SCOPE_MISMATCH"
            elif not in_window:
                state = "OUTSIDE_REVIEW_WINDOW"
            elif position["ownership"] != "entity-owned":
                state = "ENTITY_OWNERSHIP_NOT_DECLARED"
            elif letter["status"] in {"pending", "undeliverable", "unreliable"}:
                hard = not bool(letter["followup_evidence_version_id"])
                state = (
                    "CUSTODY_ALTERNATIVE_PROCEDURES_MISSING"
                    if hard
                    else "CUSTODY_ALTERNATIVE_PROCEDURES_REQUIRE_REVIEW"
                )
            elif not letter["contact_verified"] or not letter["independently_received"]:
                state = "CUSTODY_INDEPENDENCE_ASSESSMENT_MISSING"
            elif letter["held_for_entity"] not in {"yes", "none-held"}:
                state = "HELD_FOR_ENTITY_NOT_CONFIRMED"
            else:
                difference = Decimal(letter["response_quantity"]) - Decimal(position["quantity"])
                exception = (
                    difference != 0
                    or letter["condition"] not in {"good", "not-applicable"}
                    or letter["status"] == "disputed"
                )
                hard = exception and not bool(letter["followup_evidence_version_id"])
                state = (
                    "CUSTODY_EXCEPTION_FOLLOWUP_MISSING"
                    if hard
                    else "CUSTODY_EXCEPTION_REQUIRES_REVIEW"
                    if exception
                    else "MATCHED"
                )
        blocked |= hard
        scope = position or letter
        assert scope is not None
        rows.append(
            {
                "id": f"custody:{index}",
                "position_source_id": position["id"] if position else None,
                "confirmation_source_id": letter["id"] if letter else None,
                **{field: scope[field] for field in FIELDS},
                "book_quantity": position["quantity"] if position else None,
                "declared_ownership": position["ownership"] if position else None,
                "title_reference": position["title_reference"] if position else None,
                "requested_quantity": letter["requested_quantity"] if letter else None,
                "response_quantity": letter["response_quantity"] if letter else None,
                "quantity_difference": str(difference) if difference is not None else None,
                "condition": letter["condition"] if letter else None,
                "held_for_entity": letter["held_for_entity"] if letter else None,
                "confirmation_evidence": letter,
                "state": state,
            }
        )
    if not rows:
        rows.append({"id": "custody-population", "state": "CUSTODY_POPULATION_MISSING"})
        blocked = True
    return {
        **result(
            rows,
            blocked,
            [
                "Quantity and condition responses concern supplied offsite custody positions; no physical attendance, title authenticity or valuation is established",
                "Quantities compare exactly within custodian/site/SKU/lot/unit; monetary tolerance, currency netting and unit conversion do not apply",
                "Contact verification and direct receipt are assessed declarations; retained hashes establish document identity, not sender authentication",
                "Non-responses and unreliable replies require retained alternative procedures and independent review; they never become confirmations",
                "Empty schedules do not qualify nil offsite inventory; title, lien, consignment, completeness and applicable audit methodology need separate evidence",
            ],
        ),
        "custody_confirmation_contract": "offsite-inventory-confirmations/1",
        "custody_quantity_controls": [
            {"source_role": role, **control}
            for role, source in sources.items()
            for control in source["custody_quantity_controls"]
        ],
    }
