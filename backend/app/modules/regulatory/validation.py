"""Replay actual bounded calculators against reviewer-supplied expected results.

Fixtures validate software arithmetic/applicability, not the truth of legal inputs.
No expected result is inferred by this module and no engagement evidence is created.
"""

import calendar
import hashlib
import json
import platform
from datetime import date
from decimal import Decimal, localcontext
from importlib.metadata import version
from pathlib import Path
from types import CodeType, SimpleNamespace

from fastapi import HTTPException

from app.modules.jurisdictions.packages import fingerprint
from app.modules.regulatory.validation_schemas import RuleFixture

CONTRACT = "regulatory-fixture-validation/1"


class FixtureMismatch(ValueError):
    def __init__(self, message, outcomes):
        super().__init__(message)
        self.outcomes = outcomes


def normalized_code(code):
    if not isinstance(code, CodeType):
        raise ValueError("A trusted Python calculator implementation is required")
    return {
        "bytecode": code.co_code.hex(),
        "names": list(code.co_names),
        "variables": list(code.co_varnames),
        "freevars": list(code.co_freevars),
        "cellvars": list(code.co_cellvars),
        "arguments": code.co_argcount,
        "positional_only": code.co_posonlyargcount,
        "keyword_only": code.co_kwonlyargcount,
        "flags": code.co_flags,
        "exceptions": code.co_exceptiontable.hex(),
        "constants": [constant(value) for value in code.co_consts],
    }


def constant(value):
    if isinstance(value, CodeType):
        return {"code": normalized_code(value)}
    if value is None or isinstance(value, (str, bool, int)):
        return {"type": type(value).__name__, "value": value}
    if isinstance(value, bytes):
        return {"bytes": value.hex()}
    if isinstance(value, float):
        return {"float": value.hex()}
    if isinstance(value, complex):
        return {"complex": [value.real.hex(), value.imag.hex()]}
    if isinstance(value, (tuple, list)):
        return {type(value).__name__: [constant(item) for item in value]}
    if isinstance(value, (set, frozenset)):
        items = [constant(item) for item in value]
        return {
            type(value).__name__: sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
        }
    if isinstance(value, dict):
        return {
            "dict": sorted(
                [[constant(key), constant(item)] for key, item in value.items()],
                key=lambda item: json.dumps(item[0], sort_keys=True),
            )
        }
    if value is Ellipsis:
        return {"ellipsis": True}
    raise ValueError("Unsupported trusted calculator constant")


def implementation_hash(method):
    app = Path(__file__).resolve().parents[2]
    paths = [
        "modules/regulatory/validation.py",
        "modules/regulatory/validation_schemas.py",
        "modules/regulatory/schemas.py",
        "modules/jurisdictions/profiles.py",
    ]
    if method in {"checklist", "flat_rate"}:
        paths.append("modules/regulatory/evaluation.py")
    elif method == "benefit_profile":
        paths.extend(
            [
                "modules/regulatory/benefit_profiles.py",
                "modules/country_workflows/audit_schemas.py",
                "modules/country_workflows/practice_calculations.py",
                "modules/country_workflows/audit_calculations.py",
            ]
        )
    elif method == "payroll_profile":
        paths.extend(
            [
                "modules/regulatory/payroll_profiles.py",
                "modules/country_workflows/payroll_schemas.py",
                "modules/country_workflows/payroll_calculations.py",
            ]
        )
    else:
        raise ValueError("Unsupported rule validation method")
    digest = hashlib.sha256(CONTRACT.encode())
    for name in sorted(paths):
        digest.update(name.encode() + b"\0" + hashlib.sha256((app / name).read_bytes()).digest())
    functions = [evaluate_case, run, require_current]
    if method in {"checklist", "flat_rate"}:
        from app.modules.regulatory.evaluation import evaluate

        functions.append(evaluate)
    elif method == "benefit_profile":
        from app.modules.country_workflows import practice_calculations as calculator

        functions.extend(
            [calculator.benefits, calculator.rounded, calculator.money, calculator.result]
        )
    else:
        from app.modules.country_workflows import payroll_calculations as payroll_calculator

        functions.extend(
            [payroll_calculator.payroll_rules, payroll_calculator.key, payroll_calculator.rounding]
        )
    for function in functions:
        payload = {
            "code": normalized_code(getattr(function, "__code__", None)),
            "defaults": constant(function.__defaults__),
            "keyword_defaults": constant(function.__kwdefaults__),
        }
        digest.update(fingerprint(payload).encode())
    for dependency in ("pydantic", "Babel"):
        digest.update(dependency.encode() + b"\0" + version(dependency).encode())
    digest.update(platform.python_version().encode())
    return digest.hexdigest()


def provenance(rule):
    return {
        "id": "FIXTURE-RULE",
        "source_evidence_version_id": None,
        "source_sha256": rule.citations[0].document_sha256,
        "source_url": str(rule.citations[0].url),
        "source_version": "FIXTURE-ONLY",
        "applicability_review": "Fixture arithmetic only; legal source approval is separate",
        "effective_from": rule.effective_from.isoformat(),
        "effective_to": rule.effective_to.isoformat()
        if rule.effective_to
        else date.max.isoformat(),
    }


def evaluate_case(rule, case):
    if case.kind != rule.method:
        raise ValueError("Fixture kind differs from the rule implementation")
    if rule.method in {"checklist", "flat_rate"}:
        from app.modules.regulatory.evaluation import evaluate

        output = evaluate(
            rule, case.facts, case.period_start, case.period_end, case.transaction_date
        )
        amount = output.get("calculation", {}).get("unrounded_amount")
        return {"applicability": output["applicability"], "amount": amount}, (
            output["applicability"] == "APPLICABLE"
            and (
                rule.method == "checklist"
                or (amount is not None and Decimal(str(case.facts["tax_base"])) > 0)
            )
        )
    data = SimpleNamespace(as_of=case.as_of, tolerance=Decimal(0), currency="INR")
    if rule.method == "benefit_profile":
        from app.modules.country_workflows.practice_calculations import benefits

        assert case.employee is not None and rule.benefit_parameters is not None
        employee = case.employee.model_dump(mode="json")
        output = benefits(
            data,
            {
                "employees": [employee],
                "rules": [{**rule.benefit_parameters.model_dump(mode="json"), **provenance(rule)}],
            },
        )
        row = output["rows"][0]
        return {"state": row["state"], "amount": row.get("expected_benefit")}, (
            row.get("expected_benefit") is not None and case.employee.monthly_basic_salary > 0
        )
    from app.modules.country_workflows.payroll_calculations import payroll_rules

    assert case.basis is not None and rule.payroll_parameters is not None
    basis = case.basis.model_dump(mode="json")
    parameters = rule.payroll_parameters
    if parameters.formula != "employer-minus-eps" and case.pension_amount is not None:
        raise ValueError("Pension fixture offsets apply only to employer-minus-EPS")
    rules = [{**parameters.model_dump(mode="json"), **provenance(rule)}]
    bases = [basis]
    reported = [{**basis, "id": "FIXTURE-REPORTED", "amount": str(case.reported_amount)}]
    if case.pension_amount is not None:
        pension = {
            **basis,
            "id": "FIXTURE-PENSION-BASIS",
            "component": "PF:EPS",
            "rule_group": "FIXTURE-PENSION",
            "eligible": True,
        }
        bases.append(pension)
        rules.append(
            {
                **rules[0],
                "id": "FIXTURE-PENSION-RULE",
                "component": "PF:EPS",
                "rule_group": "FIXTURE-PENSION",
                "formula": "fixed",
                "rate": None,
                "salary_cap": None,
                "threshold_from": "0",
                "threshold_to": None,
                "fixed_amount": str(case.pension_amount),
                "rounding": "paise",
            }
        )
        reported.append(
            {**pension, "id": "FIXTURE-PENSION-REPORTED", "amount": str(case.pension_amount)}
        )
    output = payroll_rules(data, {"bases": bases, "rules": rules, "reported": reported})
    row = next(
        item
        for item in output["rows"]
        if item["basis_source_id"] == basis["id"] and item["component"] == basis["component"]
    )
    return {"state": row["state"], "amount": row["expected_amount"]}, (
        row["expected_amount"] is not None and case.basis.amount > 0 and case.basis.eligible
    )


def run(rule, rule_sha256, cases):
    if not cases:
        raise ValueError("At least one independently specified validation fixture is required")
    if len(cases) > 20 or len({case.id for case in cases}) != len(cases):
        raise ValueError("Supply at most twenty uniquely identified validation fixtures")
    outcomes = []
    demonstrated = False
    calculation_count = 0
    blocking_contract = False
    if rule.method == "payroll_profile" and rule.effective_to is not None:
        first = rule.effective_from
        if first.day != 1:
            first = (
                date(first.year + 1, 1, 1)
                if first.month == 12 and first.year < 9999
                else date(first.year, first.month + 1, 1)
                if first.month < 12
                else None
            )
        complete_month = (
            first.replace(day=calendar.monthrange(first.year, first.month)[1])
            if first is not None
            else None
        )
        blocking_contract = complete_month is None or complete_month > rule.effective_to
    for case in cases:
        with localcontext() as arithmetic:
            arithmetic.prec = 80
            actual, positive = evaluate_case(rule, case)
        expected = {
            "applicability"
            if case.kind in {"checklist", "flat_rate"}
            else "state": case.expected_applicability
            if case.kind in {"checklist", "flat_rate"}
            else case.expected_state,
            "amount": str(case.expected_amount) if case.expected_amount is not None else None,
        }
        actual_amount, expected_amount = actual.get("amount"), expected["amount"]
        agrees = actual.get("applicability", actual.get("state")) == expected.get(
            "applicability", expected.get("state")
        ) and (
            (actual_amount is None and expected_amount is None)
            or (
                actual_amount is not None
                and expected_amount is not None
                and Decimal(actual_amount) == Decimal(expected_amount)
            )
        )
        outcomes.append({"id": case.id, "expected": expected, "actual": actual, "passed": agrees})
        demonstrated |= positive and agrees
        calculation_count += int(positive and agrees)
        if (
            blocking_contract
            and case.basis is not None
            and agrees
            and actual.get("state") == "RULE_MISSING_OR_SPLIT_PERIOD"
        ):
            params = rule.payroll_parameters
            first_day = date.fromisoformat(case.basis.period + "-01")
            last_day = first_day.replace(
                day=calendar.monthrange(first_day.year, first_day.month)[1]
            )
            if (
                params is not None
                and all(
                    getattr(case.basis, key) == getattr(params, key)
                    for key in ("component", "rule_group", "jurisdiction")
                )
                and case.basis.amount >= params.threshold_from
                and (params.threshold_to is None or case.basis.amount < params.threshold_to)
                and first_day <= rule.effective_to
                and last_day >= rule.effective_from
            ):
                demonstrated = True
    if not demonstrated or not all(item["passed"] for item in outcomes):
        raise FixtureMismatch(
            "Validation fixtures disagree with the implementation or contain no applicable calculation",
            outcomes,
        )
    payload = {
        "contract": CONTRACT,
        "rule_sha256": rule_sha256,
        "implementation_sha256": implementation_hash(rule.method),
        "method": rule.method,
        "cases": [case.model_dump(mode="json") for case in cases],
        "outcomes": outcomes,
        "case_count": len(cases),
        "applicable_case_count": calculation_count,
        "support": "BLOCKING_ONLY_NO_COMPLETE_WAGE_MONTH"
        if blocking_contract
        else "APPLICABLE_CASE_DEMONSTRATED",
        "passed": True,
        "scope": "SUPPLIED_FIXTURES_ONLY_NOT_LEGAL_QUALIFICATION",
    }
    return {**payload, "receipt_sha256": fingerprint(payload)}


def require_current(rule, obj_sha256, receipt):
    try:
        current_implementation = implementation_hash(rule.method)
    except (ValueError, OSError):
        raise HTTPException(409, "The recorded calculator implementation is unavailable") from None
    if (
        not isinstance(receipt, dict)
        or receipt.get("contract") != CONTRACT
        or receipt.get("rule_sha256") != obj_sha256
        or receipt.get("method") != rule.method
        or receipt.get("implementation_sha256") != current_implementation
        or receipt.get("passed") is not True
        or not receipt.get("cases")
        or fingerprint({key: value for key, value in receipt.items() if key != "receipt_sha256"})
        != receipt.get("receipt_sha256")
    ):
        raise HTTPException(
            409,
            "Current recorded fixture validation is required; prepare and independently approve a new rule version",
        )
    # Validate the retained declarative input contract without trusting executable payloads.
    for case in receipt["cases"]:
        RuleFixture.model_validate(case)
    return receipt
