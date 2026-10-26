"""Positive party-balance evidence; never dispatches or authenticates confirmations."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.modules.country_workflows.audit_calculations import control_rows, result
from app.modules.jurisdictions.profiles import Strict

ID = Annotated[str, Field(min_length=1, max_length=120)]
Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]
SHA = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class PartyConfirmation(Strict):
    id: ID
    account: ID
    counterparty: ID
    side: Literal["receivable", "payable"]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    as_of: date
    confirmation_type: Literal["positive"] = "positive"
    requested_amount: Money
    response_amount: Money | None = None
    status: Literal["not-sent", "pending", "received", "disputed", "undeliverable", "unreliable"]
    requested_on: date | None = None
    responded_on: date | None = None
    contact_verified: bool = False
    independently_received: bool = False
    request_reference: str = Field(default="", max_length=120)
    response_reference: str = Field(default="", max_length=120)
    request_evidence_version_id: UUID | None = None
    request_source_sha256: SHA | None = None
    response_evidence_version_id: UUID | None = None
    response_source_sha256: SHA | None = None
    followup_evidence_version_id: UUID | None = None
    followup_source_sha256: SHA | None = None
    followup_kind: Literal["alternative-procedures", "exception-investigation"] | None = None
    followup_on: date | None = None
    followup_reference: str = Field(default="", max_length=120)
    followup_assessment: str = Field(default="", max_length=2000)
    scope_assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def evidence_scope(self):
        for value in (self.id, self.account, self.counterparty):
            if not value.strip() or value != value.strip():
                raise ValueError("Confirmation scope identifiers must be exact nonblank values")
        for value in (self.request_reference, self.response_reference, self.followup_reference):
            if value != value.strip():
                raise ValueError("Confirmation document references require exact values")
        if len(self.scope_assessment.strip()) < 10:
            raise ValueError("Record the positive party-balance scope assessment")
        for prefix in ("request", "response", "followup"):
            if bool(getattr(self, prefix + "_evidence_version_id")) != bool(
                getattr(self, prefix + "_source_sha256")
            ):
                raise ValueError(
                    "Each confirmation document needs both its retained version and hash"
                )
        has_response = self.status in {"received", "disputed", "unreliable"}
        if self.status == "not-sent":
            if self.requested_on or self.request_evidence_version_id or self.request_reference:
                raise ValueError("An unsent confirmation cannot carry sent-request evidence")
        elif (
            not self.requested_on
            or not self.request_evidence_version_id
            or not self.request_reference
        ):
            raise ValueError(
                "A sent confirmation requires its dated retained request and reference"
            )
        if has_response:
            if (
                self.response_amount is None
                or not self.responded_on
                or not self.response_evidence_version_id
                or not self.response_reference
                or self.requested_on is None
                or self.responded_on < self.requested_on
            ):
                raise ValueError(
                    "A written response needs amount, date, retained evidence and reference after the request"
                )
        elif (
            self.response_amount is not None
            or self.responded_on
            or self.response_evidence_version_id
            or self.response_reference
            or self.independently_received
        ):
            raise ValueError("A non-response cannot contain response assertions")
        if self.followup_evidence_version_id:
            if (
                not self.followup_kind
                or not self.followup_on
                or not self.followup_reference
                or len(self.followup_assessment.strip()) < 10
            ):
                raise ValueError(
                    "Follow-up evidence requires its kind, reference and meaningful assessment"
                )
            required = (
                "exception-investigation"
                if self.status in {"received", "disputed"}
                else "alternative-procedures"
            )
            if self.followup_kind != required:
                raise ValueError(
                    "Follow-up kind must distinguish response investigation from alternative procedures"
                )
            if (self.responded_on and self.followup_on < self.responded_on) or (
                self.requested_on and self.followup_on < self.requested_on
            ):
                raise ValueError(
                    "Follow-up procedures cannot precede the retained request or response"
                )
        elif (
            self.followup_kind
            or self.followup_on
            or self.followup_reference
            or self.followup_assessment
        ):
            raise ValueError("A follow-up assessment requires its retained document")
        return self


def documents(rows):
    return [
        {
            "source_evidence_version_id": row[prefix + "_evidence_version_id"],
            "source_sha256": row[prefix + "_source_sha256"],
        }
        for row in rows
        for prefix in ("request", "response", "followup")
        if row.get(prefix + "_evidence_version_id")
    ]


def party_key(row):
    return tuple(row[field] for field in ("account", "counterparty", "side", "currency"))


def verify_response_totals(rows, declared):
    if declared is None:
        raise ValueError("Independent written-response currency totals are required")
    actual: dict[str, Decimal] = {}
    with localcontext() as context:
        context.prec = 80
        for row in rows:
            if row["response_amount"] is not None:
                actual[row["currency"]] = actual.get(row["currency"], Decimal(0)) + Decimal(
                    row["response_amount"]
                )
    if actual != {currency: Decimal(value) for currency, value in declared.items()}:
        raise ValueError("Independent written-response currency totals do not agree")


def compare(data, sources):
    tables = {role: source["rows"] for role, source in sources.items()}
    verify_response_totals(
        tables["responses"], sources["responses"].get("confirmation_response_totals")
    )
    if not tables["items"]:
        raise ValueError(
            "Select a reporting-date open-item population; this procedure does not qualify nil party balances"
        )
    rows = control_rows(data, tables)
    blocked = any(row["state"] != "MATCHED" for row in rows)
    groups = defaultdict(list)
    for item in tables["items"]:
        groups[party_key(item)].append(item)
    letters = {}
    for letter in tables["responses"]:
        key = party_key(letter)
        if key in letters:
            raise ValueError(
                "Select one current positive confirmation per account/counterparty/side/currency"
            )
        letters[key] = letter
    for index, key in enumerate(sorted(groups.keys() | letters.keys()), 1):
        items, letter = groups.get(key, []), letters.get(key)
        book = sum((Decimal(item["amount"]) for item in items), Decimal(0))
        difference = (
            Decimal(letter["response_amount"]) - book
            if items and letter and letter["response_amount"] is not None
            else None
        )
        state, hard = "NOT_REQUESTED_REQUIRES_EVIDENCE", True
        if not items:
            state = "UNKNOWN_PARTY_POPULATION"
        elif letter:
            in_scope = (
                letter["as_of"] == data.as_of.isoformat()
                and Decimal(letter["requested_amount"]) == book
            )
            in_window = all(
                not letter.get(field) or date.fromisoformat(letter[field]) <= data.review_through
                for field in ("requested_on", "responded_on", "followup_on")
            )
            has_followup = bool(letter["followup_evidence_version_id"])
            if not in_scope:
                state = "CONFIRMATION_SCOPE_MISMATCH"
            elif not in_window:
                state = "OUTSIDE_REVIEW_WINDOW"
            elif letter["status"] in {"received", "disputed"}:
                if not letter["contact_verified"] or not letter["independently_received"]:
                    state = "INDEPENDENCE_ASSESSMENT_MISSING"
                elif difference is None:
                    state = "RESPONSE_AMOUNT_MISSING"
                elif letter["status"] == "disputed" or abs(difference) > data.tolerance:
                    state = (
                        "RESPONSE_EXCEPTION_REQUIRES_REVIEW"
                        if has_followup
                        else "RESPONSE_EXCEPTION_FOLLOWUP_MISSING"
                    )
                    hard = not has_followup
                else:
                    state, hard = "MATCHED", False
            else:
                state = (
                    "ALTERNATIVE_PROCEDURES_REQUIRE_REVIEW"
                    if has_followup
                    else "ALTERNATIVE_PROCEDURES_MISSING"
                )
                hard = not has_followup
        blocked |= hard
        rows.append(
            {
                "id": f"party-confirmation:{index}",
                "kind": "party-confirmation",
                "account": key[0],
                "counterparty": key[1],
                "side": key[2],
                "currency": key[3],
                "book_balance": str(book) if items else None,
                "open_item_count": len(items),
                "open_item_source_ids": [item["id"] for item in items],
                "confirmation_source_row_id": letter["id"] if letter else None,
                "confirmation_status": letter["status"] if letter else "not-requested",
                "requested_amount": letter["requested_amount"] if letter else None,
                "response_amount": letter["response_amount"] if letter else None,
                "difference": str(difference) if difference is not None else None,
                "confirmation_evidence": letter,
                "state": state,
            }
        )
    return {
        **result(
            rows,
            blocked,
            [
                "Only positive confirmations of explicitly scoped account/counterparty/side/currency balances are supported; no cross-party, account or currency netting or FX conversion",
                "Request, response and follow-up hashes establish retained document identity, not sender authenticity, receipt independence or sufficient audit evidence",
                "No confirmation is dispatched; contact verification and direct receipt are assessed declarations, not automated verification",
                "Non-responses, unreliable responses and response exceptions require retained follow-up evidence and documented independent review; they are never automatically cleared",
                "Open-item/GL agreement establishes supplied-population arithmetic, not complete receivable/payable existence, recoverability or an audit opinion",
            ],
        ),
        "confirmation_contract": "positive-party-balance-confirmations/1",
        "confirmation_scope": {
            "as_of": data.as_of.isoformat(),
            "review_through": data.review_through.isoformat(),
            "open_items": len(tables["items"]),
            "party_positions": len(groups),
            "confirmation_rows": len(letters),
        },
    }
