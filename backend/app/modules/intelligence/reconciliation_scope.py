"""Declared bank-account isolation; labels and mappings do not authenticate a bank."""

CONTRACT = "single-bank-account-scope/1"


def prepare(rows, label, assessment):
    if not label:
        return rows, None
    originals = {row.get("account_code") for row in rows}
    if len(originals) != 1:
        raise ValueError(
            "A bank account declaration cannot merge mixed or partially identified source accounts"
        )
    original = next(iter(originals))
    return [dict(row, original_account_code=original, account_code=label) for row in rows], {
        "contract": CONTRACT,
        "matching_account_code": label,
        "original_account_code": original,
        "assessment": assessment,
        "basis": "DECLARED_FILE_ACCOUNT" if original is None else "EXPLICIT_ORIGINAL_TO_GL_LABEL",
        "bank_authentication": "NOT_ESTABLISHED",
    }


def validate(account_code, left, right, source_body=None):
    if not right:
        raise ValueError(
            "Bank reconciliation requires an independently controlled statement population"
        )
    if any(row.get("account_code") != account_code for row in [*left, *right]):
        raise ValueError(
            "Every bank row must identify the selected single GL account; prepare an explicit independently reviewed account-label mapping"
        )
    bank_currencies = {row["currency"] for row in right}
    if len(bank_currencies) != 1 or any(row["currency"] not in bank_currencies for row in left):
        raise ValueError(
            "One bank account cannot mix currencies; use original-currency country bank sources for foreign-currency reconciliation"
        )
    if source_body is not None and source_body.get("review_status") != "REVIEWED":
        raise ValueError(
            "The bank supporting table and its account mapping require independent review before matching"
        )
    binding = (source_body or {}).get("bank_account_binding")
    if binding and (
        binding.get("contract") != CONTRACT
        or binding.get("matching_account_code") != account_code
        or {row.get("original_account_code") for row in right}
        != {binding.get("original_account_code")}
    ):
        raise ValueError(
            "Retained bank account mapping does not agree to every original source row"
        )
    return {
        "contract": CONTRACT,
        "matching_account_code": account_code,
        "currency": next(iter(bank_currencies)),
        "statement_original_account_code": binding.get("original_account_code")
        if binding
        else account_code,
        "source_basis": binding["basis"] if binding else "ORIGINAL_ACCOUNT_COLUMN",
        "mapping_assessment": binding.get("assessment") if binding else None,
        "bank_authentication": "NOT_ESTABLISHED",
        "balance_bridge": "NOT_A_CLOSING_BALANCE_BRS",
    }
