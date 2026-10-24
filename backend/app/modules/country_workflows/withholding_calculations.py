"""Separate liability and credit comparisons with explicit current-observation selection."""

from datetime import date
from decimal import Decimal
from typing import Any

from app.modules.country_workflows.audit_calculations import result

KEY_FIELDS = (
    "registration",
    "counterparty",
    "legal_role",
    "tax_kind",
    "rule_reference",
    "tax_year_start",
    "tax_year_end",
    "period",
    "transaction_reference",
    "transaction_date",
    "currency",
)

ASSESSMENT_FIELDS = (
    "assessment_evidence_version_id",
    "assessment_sha256",
    "assessment_kind",
    "assessment_period_start",
    "assessment_period_end",
    "assessment_amount_limit",
)


def certificate_pools(records):
    pools: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records.values():
        if record.get("assessment_kind") != "certificate" or not record.get(
            "assessment_evidence_version_id"
        ):
            continue
        key = (record["assessment_evidence_version_id"], record["source_reference"])
        scope = tuple(
            Decimal(record[field])
            if field == "assessment_amount_limit" and record.get(field) is not None
            else record.get(field)
            for field in (
                "assessment_sha256",
                "assessment_period_start",
                "assessment_period_end",
                "assessment_amount_limit",
                "registration",
                "counterparty",
                "legal_role",
                "tax_kind",
                "currency",
                "source_version",
            )
        )
        pool = pools.setdefault(key, {"scope": scope, "amount": Decimal(0)})
        if pool["scope"] != scope:
            raise ValueError(
                "Conflicting certificate scope or limit for the same document/reference"
            )
        pool["amount"] += Decimal(record["amount"])
    return pools


def assessment_issues(record, kind, pools):
    if record is None:
        return ["CURRENT_ASSESSMENT_RECORD_MISSING"]
    issues = []
    if not record.get("assessment_evidence_version_id") or not record.get("assessment_sha256"):
        issues.append("RETAINED_ASSESSMENT_DOCUMENT_MISSING")
    if record.get("assessment_kind") != kind:
        issues.append("ASSESSMENT_KIND_MISSING_OR_DIFFERENT")
    start, end = record.get("assessment_period_start"), record.get("assessment_period_end")
    if not start or not end or not start <= record["transaction_date"] <= end:
        issues.append("TRANSACTION_OUTSIDE_ASSESSED_COVERAGE")
    if kind == "certificate" and record.get("assessment_kind") == "certificate":
        pool = pools.get((record.get("assessment_evidence_version_id"), record["source_reference"]))
        limit = record.get("assessment_amount_limit")
        if limit is None or (pool is not None and pool["amount"] > Decimal(limit)):
            issues.append("CERTIFICATE_SHARED_AMOUNT_LIMIT_EXCEEDED")
    return issues


def withholding(data, tables):
    liability = data.workflow == "india-withholding-liability"
    allowed = {"deductor", "collector"} if liability else {"deductee", "collectee"}
    if data.withholding_role not in allowed:
        raise ValueError("Select the legal role appropriate to liability or credit evidence")
    selected: dict[str, dict[tuple[str, ...], dict[str, Any]]] = {}
    excluded: dict[str, dict[tuple[str, ...], list[str]]] = {}
    all_keys: set[tuple[str, ...]] = set()
    for role, records in tables.items():
        current: dict[tuple[str, ...], dict[str, Any]] = {}
        inactive: dict[tuple[str, ...], list[str]] = {}
        observations = set()
        for record in records:
            if record["legal_role"] != data.withholding_role:
                raise ValueError("Every source must use the explicitly selected legal role")
            if date.fromisoformat(record["transaction_date"]) > data.as_of or record[
                "period"
            ] > data.as_of.strftime("%Y-%m"):
                raise ValueError(
                    "Future withholding transaction or reporting month is outside cutoff"
                )
            if (
                role == "deposited"
                and record.get("payment_date")
                and date.fromisoformat(record["payment_date"]) > data.as_of
            ):
                raise ValueError("Future deposit cannot settle the reporting-date liability")
            key = tuple(record[field] for field in KEY_FIELDS)
            observation = (key, record["source_reference"], record["source_version"])
            if observation in observations:
                raise ValueError(
                    "Duplicate source observation or contradictory status for the same source version"
                )
            observations.add(observation)
            if (
                role == "deposited"
                and record.get("payment_date")
                and record["payment_date"] < record["transaction_date"]
            ):
                raise ValueError(
                    "Deposit predates transaction; assess advance allocation separately"
                )
            all_keys.add(key)
            if record["record_status"] != "current":
                inactive.setdefault(key, []).append(record["id"])
                continue
            if key in current:
                raise ValueError(
                    "Multiple current withholding observations; resolve amendments, do not sum versions"
                )
            current[key] = record
        selected[role], excluded[role] = current, inactive
    pools = certificate_pools(selected.get("certificate", {}))
    rows = []
    base_role = "expected" if liability else "books"
    for index, key in enumerate(sorted(all_keys), 1):
        present = {role: records.get(key) for role, records in selected.items()}
        missing = [role for role, record in present.items() if record is None]
        baseline = present[base_role]
        amounts = {
            role: Decimal(record["amount"]) if record else None for role, record in present.items()
        }
        baseline_amount = amounts[base_role]
        differences = {
            role: str(value - baseline_amount)
            if value is not None and baseline_amount is not None
            else None
            for role, value in amounts.items()
            if role != base_role
        }
        state = "MATCHED"
        if missing:
            state = "MISSING_CURRENT_RECORD"
        elif any(
            abs(Decimal(value)) > data.tolerance
            for value in differences.values()
            if value is not None
        ):
            state = "VARIANCE"
        elif liability:
            deposit = present["deposited"]
            if baseline is None or deposit is None:
                raise ValueError(
                    "Current expected and deposit observations are required for timing"
                )
            due = baseline.get("due_date")
            paid = deposit.get("payment_date")
            if not due or not paid:
                state = "TIMING_NOT_VERIFIED"
            elif deposit.get("due_date") and deposit["due_date"] != due:
                state = "DUE_DATE_DIFFERENCE"
            elif paid > due:
                state = "LATE_DEPOSIT"
        assessment_role = "expected" if liability else "certificate"
        assessed = present[assessment_role]
        issues = assessment_issues(assessed, "rule" if liability else "certificate", pools)
        comparison_state = state
        if issues and state != "MISSING_CURRENT_RECORD":
            state = "ASSESSMENT_NOT_SUPPORTED"
        provenance = (
            {field: assessed.get(field) for field in ASSESSMENT_FIELDS} if assessed else None
        )
        if provenance is not None and not liability and assessed is not None:
            pool = pools.get(
                (assessed.get("assessment_evidence_version_id"), assessed["source_reference"])
            )
            provenance["certificate_scope_used_amount"] = str(pool["amount"]) if pool else None
        rows.append(
            {
                "id": f"withholding-{index}",
                **dict(zip(KEY_FIELDS, key, strict=True)),
                "state": state,
                "comparison_state": comparison_state,
                "assessment_issues": issues,
                "assessment_role": assessment_role,
                "assessment_provenance": provenance,
                "amounts": {
                    role: str(value) if value is not None else None
                    for role, value in amounts.items()
                },
                "differences_from_" + base_role: differences,
                "source_ids": {
                    role: record["id"] if record else None for role, record in present.items()
                },
                "selected_source_references": {
                    role: {
                        "reference": record["source_reference"],
                        "version": record["source_version"],
                    }
                    if record
                    else None
                    for role, record in present.items()
                },
                "excluded_source_ids": {
                    role: values.get(key, []) for role, values in excluded.items()
                },
                "missing_roles": missing,
                "liability_calculation": "DECLARED_EXPECTATION_NOT_LEGAL_COMPUTATION"
                if liability
                else "NOT_APPLICABLE",
                "credit_entitlement": "NOT_DETERMINED",
            }
        )
    return {
        **result(
            rows,
            any(row["assessment_issues"] for row in rows),
            [
                "Legal roles are separate; beneficiary credit never clears a deductor/collector liability",
                "Current/superseded/cancelled status is an assessed source selection, not live portal verification",
                "Expected amounts, rule references, tax years and due dates require independent professional assessment",
                "Retained document hashes, declared coverage and certificate caps support review; they do not qualify document authenticity or legal applicability",
                "Matched credit evidence does not establish eligibility, recoverability or a right to refund",
                "Each current record is a cumulative transaction observation; raw challan allocation, partial deposits, FX and overlapping provider observations need separately reviewed normalization",
            ],
        ),
        "withholding_role": data.withholding_role,
        "assessment_contract_version": "withholding-assessment/1",
        "comparison_basis": "LIABILITY" if liability else "BENEFICIARY_CREDIT",
        "selected_current_totals": {
            role: str(sum((Decimal(record["amount"]) for record in records.values()), Decimal(0)))
            for role, records in selected.items()
        },
    }
