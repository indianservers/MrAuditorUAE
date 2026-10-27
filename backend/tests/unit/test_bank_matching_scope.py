from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.intelligence.reconciliation_scope import CONTRACT, prepare, validate
from app.modules.intelligence.schemas import ReconcileInput, TableInput


def row(account="100", currency="AED"):
    return dict(id="R", account_code=account, currency=currency, amount="1")


@pytest.mark.parametrize("original", [None, "00000123", "شركة ألف", "100"])
def test_explicit_file_mapping_preserves_original_identity_and_needs_review(original):
    original_row = row(original)
    mapped, binding = prepare([original_row], "100", "Reviewed single original statement account")
    assert original_row["account_code"] == original
    assert mapped[0]["original_account_code"] == original and mapped[0]["account_code"] == "100"
    with pytest.raises(ValueError, match="independent review"):
        validate("100", [row()], mapped, dict(bank_account_binding=binding))
    scope = validate(
        "100", [row()], mapped, dict(review_status="REVIEWED", bank_account_binding=binding)
    )
    assert scope["statement_original_account_code"] == original
    assert scope["bank_authentication"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize("accounts", [[None, "100"], ["0001", "1"], ["100", "200"]])
def test_mapping_cannot_merge_source_accounts_or_infer_missing_rows(accounts):
    with pytest.raises(ValueError, match="cannot merge"):
        prepare([row(code) for code in accounts], "100", "Reviewed source account mapping")


@pytest.mark.parametrize(
    "left,right",
    [
        ([row()], [row(None)]),
        ([row()], [row("200")]),
        ([row("200")], [row()]),
        ([row()], [row(), row("200")]),
        ([row()], []),
    ],
)
def test_unidentified_foreign_or_mixed_account_populations_never_match(left, right):
    with pytest.raises(ValueError):
        validate("100", left, right)


@pytest.mark.parametrize(
    "left,right", [([row()], [row(currency="USD")]), ([row()], [row(), row(currency="USD")])]
)
def test_single_bank_scope_does_not_net_or_translate_currencies(left, right):
    with pytest.raises(ValueError, match="cannot mix currencies"):
        validate("100", left, right)


@pytest.mark.parametrize("change", ["contract", "code", "original"])
def test_mapping_receipt_must_agree_with_every_retained_row(change):
    rows, binding = prepare([row("0001")], "100", "Reviewed account declaration")
    binding[
        {
            "contract": "contract",
            "code": "matching_account_code",
            "original": "original_account_code",
        }[change]
    ] = "WRONG"
    with pytest.raises(ValueError, match="mapping does not agree"):
        validate("100", [row()], rows, dict(review_status="REVIEWED", bank_account_binding=binding))


def test_direct_account_column_and_empty_book_population_keep_their_declared_scope():
    scope = validate("100", [], [row()], dict(review_status="REVIEWED"))
    assert scope["contract"] == CONTRACT and scope["source_basis"] == "ORIGINAL_ACCOUNT_COLUMN"
    assert scope["balance_bridge"] == "NOT_A_CLOSING_BALANCE_BRS"


@pytest.mark.parametrize(
    "label,reason,kind",
    [
        ("100", "", "bank"),
        ("", "An assessment without label", "bank"),
        ("100", "Reviewed account binding", "open-items"),
        (" 100", "Reviewed account binding", "bank"),
    ],
)
def test_source_mapping_request_is_explicit_and_bank_only(label, reason, kind):
    with pytest.raises(ValidationError):
        TableInput(
            evidence_version_id=uuid4(),
            table_kind=kind,
            bank_account_label=label,
            bank_account_mapping_rationale=reason,
        )


def test_bank_snapshot_pair_must_use_the_same_single_account_but_other_comparisons_remain_explicit():
    account, other = uuid4(), uuid4()
    base = dict(snapshot_id=uuid4(), comparison_snapshot_id=uuid4(), account_ids=[account])
    with pytest.raises(ValidationError):
        ReconcileInput(**base, comparison_account_ids=[other])
    assert ReconcileInput(**base, comparison_account_ids=[account]).account_ids == [account]
    assert ReconcileInput(**base, comparison_account_ids=[other], reconciliation_type="receivables")


@pytest.mark.parametrize("which", ["source-multi", "source-duplicate", "destination-duplicate"])
def test_bank_selection_does_not_admit_multiple_or_duplicate_accounts(which):
    account, other = uuid4(), uuid4()
    base = dict(
        snapshot_id=uuid4(),
        comparison_snapshot_id=uuid4(),
        account_ids=[account],
        comparison_account_ids=[account],
    )
    if which == "source-multi":
        base["account_ids"] = [account, other]
    elif which == "source-duplicate":
        base["account_ids"] = [account, account]
    else:
        base["comparison_account_ids"] = [account, account]
    with pytest.raises(ValidationError):
        ReconcileInput(**base)


async def test_historical_bank_result_without_scoped_account_contract_needs_recalculation():
    from fastapi import HTTPException

    from app.modules.intelligence.matching_review import verify_review

    with pytest.raises(HTTPException, match="single independently reviewed account"):
        await verify_review(
            None, None, None, SimpleNamespace(body=dict(reconciliation_type="bank"))
        )
