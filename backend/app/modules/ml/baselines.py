"""Explicit opt-in baselines. No model, language gateway or financial postings."""

import math
from datetime import date
from statistics import median

MODES = {"rules_baseline", "statistical_baseline", "diagnostic_mock"}
VERSION = "audit-review-baselines/1"


def predict(rows, mode):
    if mode not in MODES or not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        raise ValueError("Invalid baseline mode or batch population")
    seen = set()
    amounts = []
    for row in rows:
        if any(
            not isinstance(row.get(k), str) or not row[k].strip()
            for k in (
                "id",
                "client",
                "journal",
                "account",
                "date",
                "currency",
                "functional_currency",
            )
        ):
            raise ValueError("Baseline source identity fields are required")
        if row["id"] in seen:
            raise ValueError("Duplicate baseline source row ID")
        seen.add(row["id"])
        date.fromisoformat(row["date"])
        if any(
            isinstance(row.get(k), bool)
            or not isinstance(row.get(k), (int, float))
            or not math.isfinite(row[k])
            or row[k] < 0
            for k in ("debit", "credit")
        ):
            raise ValueError("Invalid baseline debit/credit")
        amount = row["debit"] + row["credit"]
        if not math.isfinite(amount):
            raise ValueError("Nonfinite baseline amount")
        amounts.append(amount)
    logs = [math.log1p(v) for v in amounts]
    center = median(logs)
    mad = median([abs(v - center) for v in logs])
    predictions = []
    for row, amount, log_amount in zip(rows, amounts, logs, strict=True):
        posting_date = date.fromisoformat(row["date"])
        indicators = {
            "round_thousands": amount > 0 and amount % 1000 == 0,
            "calendar_year_end": posting_date.month == 12 and posting_date.day >= 25,
        }
        deviation = abs(log_amount - center) / (1.4826 * mad) if mad else None
        score = (
            None
            if mode == "diagnostic_mock"
            else (
                min(1.0, deviation / 6)
                if mode == "statistical_baseline" and deviation is not None
                else 0.0
                if mode == "statistical_baseline"
                else sum(indicators.values()) / 2
            )
        )
        predictions.append(
            {
                "transaction_id": row["id"],
                "execution_mode": mode,
                "score": score,
                "supporting_indicators": indicators,
                "robust_log_amount_deviation": deviation
                if mode == "statistical_baseline"
                else None,
                "signal_category": "diagnostic_only"
                if mode == "diagnostic_mock"
                else "review_signal"
                if score
                else "no_baseline_signal",
                "review_status": "UNREVIEWED",
                "fraud_conclusion": False,
            }
        )
    if mode != "diagnostic_mock":
        predictions.sort(key=lambda row: (-row["score"], row["transaction_id"]))
        for rank, prediction in enumerate(predictions, 1):
            prediction["review_rank"] = rank
    return {
        "execution_mode": mode,
        "model_version": None,
        "feature_version": VERSION,
        "preprocessing_version": VERSION,
        "model_family": None,
        "predictions": predictions,
        "calibrated_probability": False,
        "production_validated": False,
        "score_meaning": "No inference; explicit diagnostic fixture"
        if mode == "diagnostic_mock"
        else "Batch-relative robust log-amount deviation, scaled for review ordering"
        if mode == "statistical_baseline"
        else "Fraction of two triggered calendar/round-amount review heuristics",
        "limitations": [
            "No trained model or external language model was used",
            "Scores are review indicators, not fraud probabilities or financial calculations",
            "Small or constant batches have no useful statistical dispersion; zero is not clearance",
            "Synthetic or batch-level behavior does not establish real-client accuracy",
            "Reviewed labels and independent held-out evaluation are required before model promotion",
        ],
    }
