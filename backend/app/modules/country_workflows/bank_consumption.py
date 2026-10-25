"""Approval-time cash capacity across obligation reviews in one engagement.

The review/withdraw routes hold the engagement write lock through append/commit.
An immutable approval claim survives source staleness until explicit withdrawal.
"""

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, DecimalException, localcontext
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import aliased

from app.modules.country_workflows.bank_accounts import identifier
from app.modules.country_workflows.schemas import WorkflowInput
from app.modules.intelligence.models import IntelligenceEvent
from app.modules.jurisdictions.packages import fingerprint

CONTRACT = "bank-cash-consumption/1"
WORKFLOW = "obligation-bank-allocations"
ACTIVE = "ACTIVE_APPROVED_ALLOCATION"
WITHDRAWN = "WITHDRAWN"
MAX_PEERS = 1000
MAX_CLAIMS = 50000


def manifest(data, source, body):
    """Use original source positions, not user-renamable transaction IDs alone."""
    if data.workflow != WORKFLOW or source.get("table_type") != "transactions":
        raise ValueError("Bank cash claims require the obligation allocation workflow")
    allocated = {}
    for row in body["rows"]:
        if row.get("kind") == "bank":
            if row["source_id"] in allocated:
                raise ValueError("Duplicate bank result identity")
            allocated[row["source_id"]] = row
    digest = source.get("evidence_sha256") or source.get("source_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("Bank source needs retained original-file or committed-snapshot integrity")
    family = source.get("native_format") or source.get("parser_version")
    if not family:
        raise ValueError("Bank source parser provenance is missing")
    if family.startswith("country-csv-"):
        family = "canonical-csv"
    bank_scope = body.get("bank_account_evidence") or {}
    account = (
        identifier(bank_scope["reviewed_bank_account_number"])
        if bank_scope.get("status") == "REVIEWED_ACCOUNT_DOCUMENTS_LINKED"
        else identifier(source["native_metadata"]["account"])
        if source.get("native_metadata", {}).get("account")
        else data.account
    )
    basis = (
        "REVIEWED_ACCOUNT_NUMBER"
        if bank_scope.get("status") == "REVIEWED_ACCOUNT_DOCUMENTS_LINKED"
        else "NATIVE_HEADER_ACCOUNT"
        if source.get("native_metadata", {}).get("account")
        else "DECLARED_ACCOUNT_IDENTIFIER"
    )
    sign = Decimal(-1) if data.bank_payment_sign == "debit-negative" else Decimal(1)
    rows: list[dict[str, Any]] = []
    seen = set()
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for ordinal, bank in enumerate(source["rows"], 1):
            if bank["id"] in seen or bank["id"] not in allocated:
                raise ValueError("Bank result and original source identities do not agree")
            seen.add(bank["id"])
            output = allocated[bank["id"]]
            used = Decimal(output["allocated"])
            capacity = Decimal(bank["amount"]) * sign
            if (
                not used.is_finite()
                or used < 0
                or output["currency"] != bank["currency"]
                or Decimal(output["bank_amount"]) != Decimal(bank["amount"])
                or used > max(capacity, Decimal(0))
                or used
                and bank.get("is_reversal")
            ):
                raise ValueError("Bank cash claim disagrees with the original movement capacity")
            if not used:
                continue
            origin: dict[str, Any] = {"sha256": digest, "family": family}
            if source.get("source_snapshot_id"):
                if not bank.get("source_record_id"):
                    raise ValueError("Committed bank movement has no original record identity")
                position = {"record_id": bank["source_record_id"]}
            elif source.get("supporting_table_id"):
                # A supporting selection may be a filtered/reordered original.
                if bank.get("supporting_source_row") is None:
                    raise ValueError("Supporting bank movement has no original row position")
                position = {
                    "row": bank["supporting_source_row"],
                    "sheet": bank.get("supporting_source_worksheet"),
                    "page": bank.get("supporting_source_page"),
                }
            else:
                position = {"row": bank.get("source_row", ordinal)}
            origin_key = fingerprint(origin)
            rows.append(
                {
                    "cash_key": fingerprint({"origin": origin, "position": position}),
                    "economic_key": fingerprint(
                        {
                            "account": account,
                            "currency": bank["currency"],
                            "date": bank["date"],
                            "amount": str(capacity.normalize()),
                            "reference": bank["reference"],
                            "counterparty": bank.get("counterparty") or "",
                        }
                    ),
                    "origin_key": origin_key,
                    "account": account,
                    "account_basis": basis,
                    "currency": bank["currency"],
                    "capacity": str(capacity),
                    "allocated": str(used),
                    "bank_source_row_id": bank["id"],
                    "source_sha256": digest,
                }
            )
        if seen != allocated.keys():
            raise ValueError("Bank result includes movements outside its retained source")
        if sum((Decimal(row["allocated"]) for row in rows), Decimal(0)) != Decimal(
            body["allocation_controls"]["allocated_amount"]
        ):
            raise ValueError("Bank claim total disagrees with allocation controls")
    return {
        "contract": CONTRACT,
        "rows": rows,
        "cash_keys": sorted({row["cash_key"] for row in rows}),
        "economic_keys": sorted({row["economic_key"] for row in rows}),
        "scope": "OBLIGATION_APPROVALS_WITHIN_ONE_ENGAGEMENT",
        "identity_limit": "EDITED_BANK_FIELDS_OR_UNLINKED_ACCOUNT_ALIASES_REQUIRE_SEPARATE_ASSESSMENT",
    }


def capacity_error(manifests):
    """Across different captures, assume indistinguishable rows may overlap."""
    exact: dict[str, Any] = {}
    economic: dict[str, Any] = {}
    count = 0
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for item in manifests:
            if item.get("contract") != CONTRACT or len(item.get("rows", [])) > 5000:
                return "UNVERIFIABLE_CLAIM"
            for row in item["rows"]:
                count += 1
                if count > MAX_CLAIMS:
                    return "CLAIM_REVIEW_BOUND_EXCEEDED"
                amount, capacity = Decimal(row["allocated"]), Decimal(row["capacity"])
                if (
                    not amount.is_finite()
                    or not capacity.is_finite()
                    or amount <= 0
                    or capacity <= 0
                ):
                    return "UNVERIFIABLE_CLAIM"
                entry = exact.setdefault(
                    row["cash_key"],
                    {"capacity": capacity, "currency": row["currency"], "used": Decimal(0)},
                )
                if entry["capacity"] != capacity or entry["currency"] != row["currency"]:
                    return "CONFLICTING_BANK_REPRESENTATIONS"
                entry["used"] += amount
                if entry["used"] > capacity:
                    return "BANK_MOVEMENT_OVERALLOCATED_ACROSS_REVIEWS"
                bucket = economic.setdefault(
                    row["economic_key"],
                    {"capacity": capacity, "origins": defaultdict(lambda: defaultdict(Decimal))},
                )
                if bucket["capacity"] != capacity:
                    return "CONFLICTING_BANK_REPRESENTATIONS"
                bucket["origins"][row["origin_key"]][row["cash_key"]] += amount
        for bucket in economic.values():
            # Different captures cannot prove that identical rows are disjoint.
            worst_case = sum(
                (max(rows.values()) for rows in bucket["origins"].values()), Decimal(0)
            )
            if worst_case > bucket["capacity"]:
                return "INDISTINGUISHABLE_BANK_CASH_OVERALLOCATED"
    return None


def decisions(ctx, eid):
    event = IntelligenceEvent
    marker = event.body["bank_consumption_review"]["status"].astext
    # Old PREPARED notes do not silently release an earlier approval.
    return (
        select(event)
        .where(
            event.tenant_id == ctx.tenant_id,
            event.engagement_id == eid,
            event.kind == "country-workflow",
            event.body["workflow"].astext == WORKFLOW,
            or_(
                event.body["review_status"].astext.in_(["REVIEWED", "REJECTED"]),
                marker.in_([ACTIVE, WITHDRAWN]),
            ),
        )
        .distinct(event.root_id)
        .order_by(event.root_id, event.version.desc())
        .subquery()
    )


def is_active(body):
    marker = (body.get("bank_consumption_review") or {}).get("status")
    return marker == ACTIVE or marker != WITHDRAWN and body.get("review_status") == "REVIEWED"


async def current_decision(db, ctx, eid, root_id):
    latest = aliased(IntelligenceEvent, decisions(ctx, eid))
    return await db.scalar(select(latest).where(latest.root_id == root_id))


async def event_manifest(db, ctx, obj, *, current=False):
    from app.modules.intelligence import service

    try:
        data = WorkflowInput.model_validate(obj.body["parameters"])
        bank = await service.event(db, ctx, obj.engagement_id, data.source_ids["bank"], current)
        built = manifest(data, bank.body, obj.body)
        if obj.body.get("bank_consumption_manifest") not in (None, built):
            raise ValueError("Bank cash manifest changed")
        return built
    except (ValueError, KeyError, TypeError, DecimalException) as error:
        raise HTTPException(
            409, "Bank cash controls cannot be verified; withdraw or regenerate the review"
        ) from error


async def assess(db, ctx, obj, *, current=False):
    from app.modules.intelligence import service

    candidate = await event_manifest(db, ctx, obj, current=current)
    checked, manifests = [], [candidate]
    if candidate["rows"]:
        latest = aliased(IntelligenceEvent, decisions(ctx, obj.engagement_id))
        status = latest.body["bank_consumption_review"]["status"].astext
        contract = latest.body["bank_consumption_manifest"]["contract"].astext
        statement = (
            select(latest.id)
            .where(
                latest.root_id != obj.root_id,
                or_(
                    status == ACTIVE,
                    (latest.body["review_status"].astext == "REVIEWED")
                    & (status.is_(None) | (status != WITHDRAWN)),
                ),
                or_(
                    contract.is_(None),
                    contract != CONTRACT,
                    latest.body["bank_consumption_manifest"]["cash_keys"].has_any(
                        array(candidate["cash_keys"])
                    ),
                    latest.body["bank_consumption_manifest"]["economic_keys"].has_any(
                        array(candidate["economic_keys"])
                    ),
                ),
            )
            .limit(MAX_PEERS + 1)
        )
        identifiers = list((await db.scalars(statement)).all())
        if len(identifiers) > MAX_PEERS:
            raise HTTPException(
                409,
                "Too many historical bank allocation claims; withdraw superseded reviews or qualify their manifests",
            )
        claim_count = len(candidate["rows"])
        for identifier_value in identifiers:
            peer = await service.event(db, ctx, obj.engagement_id, identifier_value, False)
            prior = peer.body.get("bank_consumption_manifest")
            if not isinstance(prior, dict) or prior.get("contract") != CONTRACT:
                prior = await event_manifest(db, ctx, peer)
            claim_count += len(prior.get("rows", []))
            if claim_count > MAX_CLAIMS:
                raise HTTPException(
                    409, "Too many relevant bank claims; withdraw superseded allocation reviews"
                )
            manifests.append(prior)
            checked.append(
                {
                    "id": str(peer.id),
                    "root_id": str(peer.root_id),
                    "title": peer.body.get("title", "Reviewed allocation"),
                }
            )
    try:
        error = capacity_error(manifests)
    except (ValueError, KeyError, TypeError, DecimalException):
        error = "UNVERIFIABLE_CLAIM"
    return candidate, checked, error


async def approve(db, ctx, obj):
    candidate, checked, error = await assess(db, ctx, obj, current=True)
    if error:
        raise HTTPException(
            409,
            f"Shared bank cash approval blocked: {error}. Withdraw or restate conflicting approved allocation reviews.",
        )
    return candidate, {
        "status": ACTIVE,
        "checked_at": datetime.now(UTC).isoformat(),
        "checked_peer_count": len(checked),
        "manifest_sha256": fingerprint(candidate),
    }


async def status(db, ctx, obj):
    decision = await current_decision(db, ctx, obj.engagement_id, obj.root_id)
    state = (
        ACTIVE if decision and is_active(decision.body) else WITHDRAWN if decision else "UNRESERVED"
    )
    try:
        candidate, checked, error = await assess(db, ctx, obj)
        count = len(candidate["rows"])
    except HTTPException as failure:
        if failure.status_code != 409:
            raise
        # Withdrawal must remain available when stale legacy evidence cannot
        # establish amounts. This does not waive tenant or evidence access.
        checked, count, error = [], None, str(failure.detail)
    return {
        "state": state,
        "claim_count": count,
        "approval_error": error,
        "related_reviews": checked,
        "checked_at": datetime.now(UTC).isoformat(),
        "scope": "OBLIGATION_APPROVALS_WITHIN_ONE_ENGAGEMENT",
    }
