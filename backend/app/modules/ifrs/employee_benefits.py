"""Aggregate IAS 19/payroll bridge, not an HR master or actuarial valuation."""


def employee_benefits(data):
    obligation = (
        data.opening_obligation
        + data.current_service_cost
        + data.past_service_cost
        + data.net_interest
        + data.remeasurement_oci
        - data.settlements
    )
    payable = (
        data.opening_payroll_payable
        + data.payroll_expense
        + data.leave_bonus_accrual
        - data.payroll_deductions
        - data.confirmed_bank_payments
    )
    issues = []
    if obligation < 0 or payable < 0:
        raise ValueError(
            "Negative obligation/payroll payable requires separate asset/recovery assessment"
        )
    if data.scheme == "defined_benefit" and not data.actuarial_report_reference.strip():
        issues.append(
            {
                "code": "ACTUARIAL_INPUTS_MISSING",
                "blocking": True,
                "remediation": "Supply reviewed actuarial report; statutory settlement is not IAS 19 measurement",
            }
        )
    if data.scheme == "defined_contribution" and any(
        [data.opening_obligation, data.net_interest, data.remeasurement_oci, data.past_service_cost]
    ):
        raise ValueError(
            "Defined-contribution schemes require a contribution payable schedule, not defined-benefit rollforward inputs"
        )
    for code, difference in [
        ("BENEFIT_LEDGER_DIFFERENCE", obligation - data.closing_ledger_provision),
        ("PAYROLL_LEDGER_DIFFERENCE", payable - data.closing_payroll_ledger_payable),
    ]:
        if difference:
            issues.append(
                {
                    "code": code,
                    "difference": difference,
                    "blocking": True,
                    "remediation": "Reconcile approved source totals to ledger; no balancing entry is generated",
                }
            )
    return {
        "employment_framework": data.employment_framework,
        "scheme": data.scheme,
        "obligation_rollforward": {
            "opening": data.opening_obligation,
            "service_cost": data.current_service_cost,
            "past_service_cost": data.past_service_cost,
            "net_interest": data.net_interest,
            "remeasurement_oci": data.remeasurement_oci,
            "settlements": data.settlements,
            "closing": obligation,
            "ledger": data.closing_ledger_provision,
            "difference": obligation - data.closing_ledger_provision,
        },
        "payroll_bridge": {
            "opening": data.opening_payroll_payable,
            "expense": data.payroll_expense,
            "leave_bonus_accrual": data.leave_bonus_accrual,
            "deductions": data.payroll_deductions,
            "confirmed_bank_payments": data.confirmed_bank_payments,
            "closing": payable,
            "ledger": data.closing_payroll_ledger_payable,
            "difference": payable - data.closing_payroll_ledger_payable,
        },
        "statutory_settlement_estimate": data.statutory_settlement_estimate,
        "profit_loss_movement": data.current_service_cost
        + data.past_service_cost
        + data.net_interest,
        "oci_movement": data.remeasurement_oci,
        "issues": issues,
        "execution_scope": "Aggregate reconciliation from reviewed supplied values; no actuarial valuation, salary generation, payment instruction or bank verification",
        "payment_state": "NO_PAYMENT_INSTRUCTION_CREATED",
    }
