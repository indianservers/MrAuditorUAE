"""Governed preparation of existing authorized ledger snapshots for v2 CPU models."""

import json
from datetime import date
from decimal import Decimal
from hashlib import sha256

from app.modules.ml.contracts import JournalHeader, chronological_splits

JOURNAL_TYPES = [
    "sales",
    "purchases",
    "payroll",
    "bank",
    "accrual",
    "prepayment",
    "depreciation",
    "reclassification",
    "closing",
    "other",
]
ACCOUNT_TYPES = ["Assets", "Liabilities", "Equity", "Income", "Expenses"]
TASKS = ["journal-type", "account-mapping", "journal-anomaly", "review-ranking"]


def prepare_reviewed(rows, task, labels, train_end: date, validation_end: date):
    if task not in TASKS:
        raise ValueError("Unknown foundation task")
    taxonomy = (
        JOURNAL_TYPES
        if task == "journal-type"
        else ACCOUNT_TYPES
        if task == "account-mapping"
        else ["normal", "relevant_exception"]
    )
    label_key = "account" if task == "account-mapping" else "journal"
    identifiers = {row[label_key] for row in rows}
    if not set(labels) <= identifiers or any(label not in taxonomy for label in labels.values()):
        raise ValueError("Source observations require reviewed taxonomy labels")
    prior = {
        r[label_key]: r["target"]
        for r in rows
        if r.get("label_origin") == "auditor_reviewed" and r.get("target") in taxonomy
    }
    labels = {**prior, **labels}
    journals: dict[str, JournalHeader] = {}
    groups: dict[str, list[dict]] = {}
    for row in rows:
        journal = row["journal"]
        if journal in journals and journals[journal].posting_date != date.fromisoformat(
            row["date"]
        ):
            raise ValueError("Conflicting journal dates")
        journals[journal] = JournalHeader(
            id=journal,
            posting_date=date.fromisoformat(row["date"]),
            reversal_of=row.get("reversal_of"),
        )
        groups.setdefault(journal, []).append(row)
    fingerprints: dict[str, str] = {}
    connected = []
    for journal, lines in groups.items():
        normalized = sorted(
            (
                r["date"],
                r["account"],
                str(Decimal(str(r["debit"]))),
                str(Decimal(str(r["credit"]))),
                r["currency"],
                r.get("description") or "",
            )
            for r in lines
        )
        fingerprint = sha256(json.dumps(normalized).encode()).hexdigest()
        if fingerprint in fingerprints:
            connected.append((journal, fingerprints[fingerprint]))
        fingerprints[fingerprint] = journal
    assignments = chronological_splits(
        list(journals.values()), train_end, validation_end, connected
    )
    parent = {key: key for key in journals}

    def root(key):
        while parent[key] != key:
            key = parent[key]
        return key

    for left, right in connected + [
        (j.id, j.reversal_of) for j in journals.values() if j.reversal_of in journals
    ]:
        parent[root(left)] = root(right)
    dates: dict[str, date] = {}
    for key, journal in journals.items():
        dates[root(key)] = max(dates.get(root(key), journal.posting_date), journal.posting_date)
    data = [
        {
            **r,
            "debit": str(Decimal(str(r["debit"]))),
            "credit": str(Decimal(str(r["credit"]))),
            "split": assignments[r["journal"]],
            "target": labels.get(r[label_key]),
            "label_origin": "auditor_reviewed" if r[label_key] in labels else None,
        }
        for r in rows
    ]
    for row in data:
        row["related_group"] = root(row["journal"])
        row["split_date"] = dates[root(row["journal"])].isoformat()
    manifest = {
        "version": "reviewed-dataset/2",
        "task": task,
        "taxonomy": taxonomy,
        "label_origin": "auditor_reviewed",
        "label_count": len(labels),
        "training_eligible": set(labels) == identifiers,
        "split_policy": "chronological; reversals and exact duplicate journals connected",
        "train_end": train_end.isoformat(),
        "validation_end": validation_end.isoformat(),
        "sha256": sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
        "counts": {s: sum(r["split"] == s for r in data) for s in ("train", "validation", "test")},
        "generalization_claim": None,
    }
    return {"rows": data, "split": [r["split"] for r in data], "synthetic": False}, manifest


def numeric_boundary(rows):
    """No accounting arithmetic occurs here; only bounded numeric ML conversion."""
    import math

    result = []
    for row in rows:
        values = {key: float(Decimal(str(row[key]))) for key in ("debit", "credit")}
        if any(not math.isfinite(v) or v < 0 for v in values.values()):
            raise ValueError("ML_INPUT_INVALID: amount exceeds numeric ML range")
        result.append({**row, **values})
    return result


def review_baseline(rows, cutoff: date, weights: dict[str, float], working_days: list[int]):
    """Explicit explainable fallback with a frozen, earlier-period reference population."""
    import math
    from statistics import median

    allowed = {"amount", "rare_pair", "manual", "outside_calendar"}
    if set(weights) != allowed or any(
        not math.isfinite(v) or not 0 <= v <= 10 for v in weights.values()
    ):
        raise ValueError("Invalid baseline weights")
    if not working_days or any(day not in range(7) for day in working_days):
        raise ValueError("Invalid entity working calendar")
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["journal"], []).append(row)
    reference = [
        lines for lines in grouped.values() if date.fromisoformat(lines[0]["date"]) <= cutoff
    ]
    scoring = [lines for lines in grouped.values() if date.fromisoformat(lines[0]["date"]) > cutoff]
    if len(reference) < 10 or not scoring or sum(map(len, scoring)) > 10000:
        raise ValueError("Baseline requires at least ten earlier journals and 1–10000 later lines")

    def magnitude(lines):
        return sum(
            (Decimal(str(r["debit"])) + Decimal(str(r["credit"])) for r in lines), Decimal(0)
        )

    logs = [math.log1p(float(magnitude(lines))) for lines in reference]
    center = median(logs)
    scale = max(0.1, 1.4826 * median(abs(v - center) for v in logs))
    pairs: dict[str, int] = {}
    signatures: dict[str, int] = {}

    def signature(lines):
        content = sorted(
            (
                r["account"],
                str(Decimal(str(r["debit"]))),
                str(Decimal(str(r["credit"]))),
                (r.get("description") or "").strip().casefold(),
                r.get("counterparty") or "",
            )
            for r in lines
        )
        return sha256(json.dumps(content, ensure_ascii=False).encode()).hexdigest()

    for lines in reference:
        pair = "|".join(sorted({r["account"] for r in lines}))
        pairs[pair] = pairs.get(pair, 0) + 1
        sig = signature(lines)
        signatures[sig] = signatures.get(sig, 0) + 1
    config = {
        "cutoff": cutoff.isoformat(),
        "weights": weights,
        "working_days": working_days,
        "log_median": center,
        "log_mad_scale": scale,
        "pairs": pairs,
    }
    predictions = []
    for lines in scoring:
        pair = "|".join(sorted({r["account"] for r in lines}))
        factors = {
            "amount": min(10, abs(math.log1p(float(magnitude(lines))) - center) / scale),
            "rare_pair": -math.log((pairs.get(pair, 0) + 1) / (len(reference) + 1)),
            "manual": float(any(r.get("manual") is True for r in lines)),
            "outside_calendar": float(
                (date.fromisoformat(lines[0]["date"]).weekday() + 1) % 7 not in working_days
            ),
        }
        score = sum(weights[key] * value for key, value in factors.items())
        predictions.append(
            {
                "transaction_id": lines[0]["journal"],
                "evidence_line_ids": [r["id"] for r in lines],
                "execution_mode": "statistical_baseline",
                "score": score,
                "financial_exposure": {
                    "gross_debits": str(sum((Decimal(str(r["debit"])) for r in lines), Decimal(0))),
                    "meaning": "Observed functional-currency debit population; not a loss estimate",
                },
                "rules_indicators": factors,
                "duplicate_or_recurring_reference_matches": signatures.get(signature(lines), 0),
                "duplicate_characteristic_meaning": "Matching account/amount/text/party pattern may be normal recurrence; requires evidence review",
                "auditor_assigned_risk": None,
                "final_conclusion": None,
                "review_status": "UNREVIEWED",
                "fraud_probability": False,
            }
        )
    return {
        "execution_mode": "statistical_baseline",
        "pipeline_version": "review-baseline/2",
        "preprocessing": config,
        "feature_version": "review-baseline/2",
        "predictions": sorted(predictions, key=lambda r: r["score"], reverse=True),
        "quality_metrics": None,
        "limitation": "No reviewed outcomes supplied; accuracy and queue precision are unmeasured",
        "production_validated": False,
    }
