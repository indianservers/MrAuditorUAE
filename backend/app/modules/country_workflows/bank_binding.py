"""Explicit reviewed account scope and ledger/bank alias binding; no authentication."""

from copy import deepcopy
from datetime import date

from fastapi import HTTPException

from app.modules.country_workflows.bank_accounts import PROFILE_VERSION, ROLES, identifier

BANK_ROLES = {
    "bank-brs": "statement",
    "bank-subsequent-clearance": "statement",
    "obligation-bank-allocations": "bank",
    "india-msme-payment-timing": "bank",
    "india-msme-interest": "bank",
    "india-msme-annual-tax": "bank",
    "merchant-settlement-bridge": "bank",
}


def financial_window(data, sources):
    if data.workflow == "india-msme-annual-tax":
        return data.settlement_start, data.tax_observed_through
    if data.workflow == "merchant-settlement-bridge":
        return data.period_start, data.as_of
    if data.workflow in {
        "obligation-bank-allocations",
        "india-msme-payment-timing",
        "india-msme-interest",
    }:
        # The allocator separately checks every movement against this explicit
        # settlement window. Earlier statement-header dates are not payments.
        return data.settlement_start, data.as_of
    end = data.review_through if data.workflow == "bank-subsequent-clearance" else data.as_of
    starts = [data.as_of]
    for source in sources.values():
        starts.extend(date.fromisoformat(row["date"]) for row in source["rows"] if row.get("date"))
        if data.workflow == "bank-brs":
            for key in ("source_range", "native_metadata"):
                if source.get(key, {}).get("from"):
                    starts.append(date.fromisoformat(source[key]["from"]))
    return min(starts), end


def bind(data, country, sources, body, receipt):
    if data.workflow not in BANK_ROLES or str(data.bank_account_review_id) != receipt["id"]:
        raise ValueError("The reviewed bank account link does not belong to this workflow request")
    if (
        body.get("workflow") != "bank-account-evidence"
        or body.get("bank_account_contract") != PROFILE_VERSION
    ):
        raise ValueError("Select a supported bank account evidence comparison")
    if (
        body.get("review_status") != "REVIEWED"
        or body.get("blocked")
        or any(
            row.get("state") != "MATCHED" or row.get("exceptions") for row in body.get("rows", [])
        )
    ):
        raise ValueError(
            "Select an independently reviewed account comparison without unresolved observations"
        )
    scope = body["bank_account_scope"]
    if (
        scope["account"] != data.account
        or scope["currency"] != data.currency
        or scope["owner_country"] != country
    ):
        raise ValueError(
            "Reviewed account, currency or owner country differs from the financial scope"
        )
    start, end = financial_window(data, sources)
    from app.modules.country_workflows.bank_observation_scope import saved_scope

    observations = saved_scope(body)
    if observations and (
        body.get("as_of") != data.as_of.isoformat()
        or observations["through"] != end.isoformat()
        or observations["from"] > start.isoformat()
    ):
        raise ValueError(
            "Assessed account observation coverage must match the financial cutoff and entire window end"
        )
    if not observations and body.get("as_of") != end.isoformat():
        raise ValueError(
            "Bank account evidence comparison date must equal the financial review window end"
        )
    rows = body.get("rows", [])
    if len(rows) != 3 or {row["source_role"] for row in rows} != set(ROLES):
        raise ValueError("Retain all three reviewed account observations")
    for row in rows:
        if (
            not date.fromisoformat(row["valid_from"])
            <= start
            <= end
            <= date.fromisoformat(row["valid_through"])
        ):
            raise ValueError(
                "Every account evidence validity interval must cover the entire financial review window"
            )
    bank = next(row for row in rows if row["source_role"] == "bank")
    role = BANK_ROLES[data.workflow]
    source = sources[role]
    native = source.get("native_format") in {"camt053", "swift-mt940"}
    actuals = {row["account"] for row in source["rows"]}
    if native:
        actual = source["native_metadata"]["account"]
        if any(value != actual for value in actuals) or identifier(actual) != identifier(
            bank["account_number"]
        ):
            raise ValueError(
                "Native statement account does not agree to the reviewed bank account number"
            )
        basis = "NATIVE_ACCOUNT_NUMBER_AGREES_TO_REVIEWED_DOCUMENTS"
    else:
        if len(actuals) > 1:
            raise ValueError(
                "A reviewed account link cannot merge different statement account identifiers"
            )
        actual = next(iter(actuals), data.account)
        if actual != data.account and identifier(actual) != identifier(bank["account_number"]):
            raise ValueError(
                "Statement account is neither the selected ledger label nor the reviewed bank account number"
            )
        basis = (
            "DECLARED_LEDGER_ACCOUNT_LABEL_ONLY"
            if actual == data.account
            else "CANONICAL_ACCOUNT_NUMBER_AGREES_TO_REVIEWED_DOCUMENTS"
        )
    prepared = dict(sources)
    prepared[role] = {
        **source,
        "rows": [{**row, "account": data.account} for row in source["rows"]],
    }
    metadata = {
        "status": "REVIEWED_ACCOUNT_DOCUMENTS_LINKED",
        "review_receipt": deepcopy(receipt),
        "review_as_of": body["as_of"],
        **({"observation_scope": observations} if observations else {}),
        "account": data.account,
        "currency": data.currency,
        "bank_source_role": role,
        "original_bank_source_account": actual,
        "bank_country": bank["bank_country"],
        "reviewed_bank_account_number": bank["account_number"],
        "source_account_binding": basis,
        "account_label_mapping_applied": actual != data.account,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "assessment": data.bank_account_scope_assessment.strip(),
        "bank_authentication_status": "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON",
    }
    return prepared, metadata


async def resolve(db, ctx, eng, data):
    from app.modules.intelligence import service

    selected = await service.event(db, ctx, eng.id, data.bank_account_review_id, True)
    if selected.kind != "country-workflow":
        raise HTTPException(422, "Select an independently reviewed bank account evidence result")
    return (
        selected.body,
        service.event_receipt(selected),
        set(selected.body.get("contributors", [str(selected.created_by)])),
    )
