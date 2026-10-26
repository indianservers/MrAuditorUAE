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
    request_basis: Literal["stated-balance", "blank-positive"] = "stated-balance"
    scope_balance: Money | None = None
    requested_amount: Money | None = None
    response_amount: Money | None = None
    status: Literal[
        "not-sent",
        "pending",
        "received",
        "disputed",
        "undeliverable",
        "unreliable",
        "partially-received",
    ]
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
    followup_kind: (
        Literal["alternative-procedures", "exception-investigation", "partial-response-procedures"]
        | None
    ) = None
    followup_on: date | None = None
    followup_reference: str = Field(default="", max_length=120)
    followup_assessment: str = Field(default="", max_length=2000)
    scope_assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def evidence_scope(self):
        if self.request_basis == "blank-positive":
            if self.requested_amount is not None or self.scope_balance is None:
                raise ValueError(
                    "A blank positive request needs an explicit assessed scope balance and no written requested amount"
                )
        else:
            if self.requested_amount is None or (
                self.scope_balance is not None and self.scope_balance != self.requested_amount
            ):
                raise ValueError(
                    "A stated-balance request needs its written amount and matching assessed scope"
                )
            self.scope_balance = self.requested_amount
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
        has_response = self.status in {"received", "disputed", "unreliable", "partially-received"}
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
                "partial-response-procedures"
                if self.status == "partially-received"
                else "exception-investigation"
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


class ConfirmationItemCoverage(Strict):
    id: ID
    confirmation_id: ID
    item_id: ID
    as_of: date
    evidence_reference: ID

    @model_validator(mode="after")
    def exact(self):
        if any(
            not value.strip() or value != value.strip()
            for value in (self.id, self.confirmation_id, self.item_id, self.evidence_reference)
        ):
            raise ValueError(
                "Partial-response item links require exact nonblank identifiers and references"
            )
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


def _verify_totals(rows, declared, field, label):
    if declared is None:
        raise ValueError(f"Independent {label} currency totals are required")
    actual: dict[str, Decimal] = {}
    with localcontext() as context:
        context.prec = 80
        for row in rows:
            if row.get(field) is not None:
                actual[row["currency"]] = actual.get(row["currency"], Decimal(0)) + Decimal(
                    row[field]
                )
    if actual != {currency: Decimal(value) for currency, value in declared.items()}:
        raise ValueError(f"Independent {label} currency totals do not agree")


def verify_response_totals(rows, declared):
    _verify_totals(rows, declared, "response_amount", "written-response")


def verify_request_totals(rows, declared):
    _verify_totals(rows, declared, "requested_amount", "written-request")


def item_coverage(data, tables, letters):
    items = {row["id"]: row for row in tables["items"]}
    by_id = {row["id"]: row for row in letters.values()}
    groups = defaultdict(list)
    links = []
    seen = set()
    for link in tables.get("coverage", []):
        identity = link["confirmation_id"], link["item_id"]
        if identity in seen:
            raise ValueError("Duplicate partial-response confirmation/item link")
        seen.add(identity)
        letter, item = by_id.get(identity[0]), items.get(identity[1])
        if (
            not letter
            or not item
            or letter["status"] != "partially-received"
            or party_key(letter) != party_key(item)
        ):
            raise ValueError(
                "Partial-response coverage must link a current partial assessment to its own scoped open item"
            )
        if date.fromisoformat(link["as_of"]) != data.as_of:
            raise ValueError("Partial-response coverage date must equal the reporting date")
        groups[letter["id"]].append(item["id"])
        links.append(
            {
                "source_row_id": link["id"],
                "confirmation_source_row_id": letter["id"],
                "item_id": item["id"],
                "as_of": link["as_of"],
                **{field: item[field] for field in ("account", "counterparty", "side", "currency")},
                "book_amount": item["amount"],
                "evidence_reference": link["evidence_reference"],
            }
        )
    return groups, links


def compare(data, sources):
    tables = {role: source["rows"] for role, source in sources.items()}
    verify_request_totals(
        tables["responses"], sources["responses"].get("confirmation_request_totals")
    )
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
    covered_groups, links = item_coverage(data, tables, letters)
    for index, key in enumerate(sorted(groups.keys() | letters.keys()), 1):
        items, letter = groups.get(key, []), letters.get(key)
        book = sum((Decimal(item["amount"]) for item in items), Decimal(0))
        difference = (
            Decimal(letter["response_amount"]) - book
            if items
            and letter
            and letter["response_amount"] is not None
            and letter["status"] != "partially-received"
            else None
        )
        covered_ids = uncovered_ids = covered_balance = uncovered_balance = partial_difference = (
            None
        )
        partial = bool(letter and letter["status"] == "partially-received")
        if partial and items and letter and covered_groups.get(letter["id"]):
            covered_ids = covered_groups[letter["id"]]
            covered_set = set(covered_ids)
            uncovered_ids = [item["id"] for item in items if item["id"] not in covered_set]
            covered_balance = sum(
                (Decimal(item["amount"]) for item in items if item["id"] in covered_set), Decimal(0)
            )
            uncovered_balance = book - covered_balance
            partial_difference = (
                Decimal(letter["response_amount"]) - covered_balance
                if letter["response_amount"] is not None
                else None
            )
        state, hard = "NOT_REQUESTED_REQUIRES_EVIDENCE", True
        if not items:
            state = "UNKNOWN_PARTY_POPULATION"
        elif letter:
            in_scope = (
                letter["as_of"] == data.as_of.isoformat()
                and Decimal(letter["scope_balance"]) == book
            )
            in_window = all(
                not letter.get(field) or date.fromisoformat(letter[field]) <= data.review_through
                for field in ("requested_on", "responded_on", "followup_on")
            )
            has_followup = bool(letter["followup_evidence_version_id"])
            if not in_scope:
                state = "CONFIRMATION_SCOPE_MISMATCH"
                difference = partial_difference = None
            elif not in_window:
                state = "OUTSIDE_REVIEW_WINDOW"
                difference = partial_difference = None
            elif partial:
                if not letter["contact_verified"] or not letter["independently_received"]:
                    state = "INDEPENDENCE_ASSESSMENT_MISSING"
                elif covered_ids is None:
                    state = "PARTIAL_RESPONSE_ITEM_SCOPE_MISSING"
                elif not uncovered_ids:
                    state = "PARTIAL_RESPONSE_SCOPE_IS_FULL_POPULATION"
                else:
                    state = (
                        "PARTIAL_RESPONSE_REQUIRES_REVIEW"
                        if has_followup
                        else "PARTIAL_RESPONSE_FOLLOWUP_MISSING"
                    )
                    hard = not has_followup
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
                "request_basis": letter["request_basis"] if letter else None,
                "scope_balance": letter["scope_balance"] if letter else None,
                "response_amount": letter["response_amount"] if letter else None,
                "difference": str(difference) if difference is not None else None,
                "response_comparison_basis": "COVERED_ITEMS_ONLY"
                if partial_difference is not None
                else "FULL_PARTY_BALANCE"
                if difference is not None
                else None,
                "covered_book_balance": str(covered_balance)
                if covered_balance is not None
                else None,
                "uncovered_book_balance": str(uncovered_balance)
                if uncovered_balance is not None
                else None,
                "covered_item_source_ids": covered_ids,
                "uncovered_item_source_ids": uncovered_ids,
                "covered_response_difference": str(partial_difference)
                if partial_difference is not None
                else None,
                "partial_response_issues": (
                    ["UNCONFIRMED_ITEMS_REMAIN"]
                    + (
                        ["COVERED_RESPONSE_DIFFERENCE"]
                        if partial_difference is not None
                        and abs(partial_difference) > data.tolerance
                        else []
                    )
                )
                if partial and uncovered_ids
                else [],
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
        "confirmation_contract": "positive-party-balance-confirmations/2",
        "confirmation_coverage_links": links,
        "confirmation_scope": {
            "as_of": data.as_of.isoformat(),
            "review_through": data.review_through.isoformat(),
            "open_items": len(tables["items"]),
            "party_positions": len(groups),
            "confirmation_rows": len(letters),
            "coverage_rows": len(links),
        },
    }
