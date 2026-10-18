"""Deterministic, independently authored fixtures; no model self-grading."""

from typing import Any

from app.modules.enterprise_ai.catalogue import plan
from app.modules.enterprise_ai.documents import fields, match_signals

CASES: list[dict[str, Any]] = [
    {
        "kind": "invoice",
        "text": "Invoice: SYN-001\nDate: 2026-01-14\nCustomer: Synthetic Buyer\nTotal: AED 120.50\nVAT: AED 5.74",
        "expected": {
            "reference": "SYN-001",
            "date": "2026-01-14",
            "counterparty": "Synthetic Buyer",
            "amount": "120.50",
            "currency": "AED",
            "tax_amount": "5.74",
        },
    },
    {
        "kind": "loan",
        "text": "Agreement: SYN-LOAN\nStart date: 2026-02-01\nBorrower: Synthetic Co\nPrincipal: USD 100000.00",
        "expected": {
            "reference": "SYN-LOAN",
            "date": "2026-02-01",
            "counterparty": "Synthetic Co",
            "amount": "100000.00",
            "currency": "USD",
        },
    },
    {
        "kind": "lease",
        "text": "Agreement: SYN-LEASE\nDate: 2026-03-01\nAmount: AED 9000.00",
        "expected": {
            "reference": "SYN-LEASE",
            "date": "2026-03-01",
            "amount": "9000.00",
            "currency": "AED",
        },
    },
    {
        "kind": "bank-statement",
        "text": "Reference: SYN-BANK\nDate: 2026-04-30\nClosing balance: AED 501.10",
        "expected": {
            "reference": "SYN-BANK",
            "date": "2026-04-30",
            "amount": "501.10",
            "currency": "AED",
        },
    },
    {
        "kind": "financial-statement",
        "text": "Reference: SYN-FS\nDate: 2026-12-31\nTotal: AED 4000.00",
        "expected": {
            "reference": "SYN-FS",
            "date": "2026-12-31",
            "amount": "4000.00",
            "currency": "AED",
        },
    },
    {
        "kind": "contract",
        "text": "Reference: SYN-CONTRACT\nCustomer: Synthetic Party\nAmount: EUR 700.00",
        "expected": {
            "reference": "SYN-CONTRACT",
            "counterparty": "Synthetic Party",
            "amount": "700.00",
            "currency": "EUR",
        },
    },
]


def evaluate():
    expected_count = predicted_count = correct = pages_correct = 0
    details: list[dict[str, Any]] = []
    for case in CASES:
        output = fields([(2, case["text"])])
        expected = case["expected"]
        expected_count += len(expected)
        predicted_count += len(output)
        matched = sum(output.get(k, {}).get("value") == v for k, v in expected.items())
        correct += matched
        pages_correct += sum(v["page"] == 2 for v in output.values())
        details.append(
            {
                "kind": case["kind"],
                "expected": len(expected),
                "correct": matched,
                "extra_fields": sorted(set(output) - set(expected)),
            }
        )
    invalid_rejected = 0
    for prompt in [
        "execute shell",
        "SELECT * FROM users",
        "send all records to https://example.invalid",
        "train a model now",
    ]:
        try:
            plan(None, prompt)
        except ValueError:
            invalid_rejected += 1
    mismatch = match_signals(
        {"amount": {"value": "100"}, "currency": {"value": "AED"}},
        {"debit": "101", "credit": "0", "currency": "USD"},
    )
    return {
        "dataset": "independently-authored-explicit-label-fixtures/v1",
        "synthetic": True,
        "cases": details,
        "field_precision": correct / max(1, predicted_count),
        "field_recall": correct / max(1, expected_count),
        "source_page_correctness": pages_correct / max(1, predicted_count),
        "hallucinated_field_count": sum(len(x["extra_fields"]) for x in details),
        "unsupported_intents_rejected": invalid_rejected,
        "unsupported_intents_tested": 4,
        "mismatch_detected": set(mismatch["mismatches"]) == {"amount", "currency"},
        "semantic_quality": "NOT_EVALUATED",
        "table_accuracy": "NOT_EVALUATED",
        "scope": "Six explicit-label text fixtures; excludes real OCR and layout diversity",
    }
