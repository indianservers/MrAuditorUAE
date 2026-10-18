"""Fixed independent arithmetic oracles; expected values never call engine formulas."""

import json
import sys
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.accounting.calculations import trial_balance
from app.modules.dmtt.calculations import calculate as dmtt
from app.modules.ifrs.calculations import calculate as ifrs
from app.modules.tax.calculations import standard_tax
from app.modules.tax.schemas import RuleParameters
from app.modules.tp.calculations import loan_schedule, statistics
from app.modules.vat.calculations import transaction
from tests.phase5.test_calculations import ECL_INPUT, LEASE
from tests.phase7.test_vat_calculations import invoice, rule
from tests.phase8.test_calculations import loan
from tests.phase9.test_dmtt import entity, group


def evaluate():
    receipts = []

    def check(identifier, inputs, expected, actual, source, tolerance="0.00000001"):
        differences = {
            key: str(D(str(actual[key])) - D(str(value))) for key, value in expected.items()
        }
        receipts.append(
            {
                "id": identifier,
                "input": inputs,
                "expected": expected,
                "actual": {key: str(actual[key]) for key in expected},
                "difference": differences,
                "tolerance": tolerance,
                "status": "PASS"
                if all(abs(D(x)) <= D(tolerance) for x in differences.values())
                else "FAIL",
                "oracle_source": source,
                "engine_rule_version": "Repository Phase12 candidate; period-specific professional legal validation remains required",
            }
        )

    check(
        "CT-1500000",
        {"income": "1500000", "threshold": "375000", "rate": "0.09"},
        {"tax": "101250"},
        {"tax": standard_tax("1500000", RuleParameters())},
        "Independent arithmetic: (1500000-375000)*0.09",
    )
    data = {**LEASE, "payments": [{"date": "2027-01-01", "amount": "2200"}]}
    lease = ifrs("lease", data)
    check(
        "IFRS-LEASE",
        data,
        {"initial_liability": "2000", "interest": "200", "closing": "0"},
        {
            "initial_liability": lease["initial_liability"],
            "interest": lease["schedule"][0]["interest"],
            "closing": lease["schedule"][0]["closing"],
        },
        "Independent one-year PV: 2200/1.1; interest=200",
    )
    data = {**ECL_INPUT, "exposures": [{"reference": "P12-ECL", "amount": "2000", "stage": 1}]}
    check(
        "IFRS-ECL",
        data,
        {"total_ecl": "130"},
        ifrs("ecl", data),
        "Independent probability weighted loss: 2000*(0.7*0.1*0.5+0.3*0.2*0.5)",
    )
    inv = invoice(amount="2100", unit_price="2100", discount="0", tax_inclusive=True)
    check(
        "VAT-INCLUSIVE",
        inv.model_dump(mode="json"),
        {"net": "2000", "tax": "100"},
        transaction(inv, rule(), rule()),
        "Independent inclusive VAT division: 2100/1.05",
    )
    values = [2, 4, 6, 8]
    check(
        "TP-INCLUSIVE-QUARTILES",
        {"values": values, "convention": "inclusive"},
        {"lower_quartile": "3.5", "median": "5", "upper_quartile": "6.5"},
        statistics(values),
        "Independent linear interpolation ranks 1.75,2.5,3.25",
    )
    data = loan(principal="50000", annual_rate="0.075")
    check(
        "LOAN-ACT365",
        data.model_dump(mode="json"),
        {"total_interest": "3750", "principal_outstanding": "50000"},
        loan_schedule(data),
        "Independent annual simple interest: 50000*.075*365/365",
    )
    g = group()
    e = entity(current_tax="1800000")
    check(
        "DMTT-2025",
        {
            "group": g.model_dump(mode="json"),
            "entity": e.model_dump(mode="json"),
            "income": "20000000",
        },
        {"etr": "0.09", "sbie": "248000", "uae_dmtt": "1185120"},
        dmtt(g, [(e, D("20000000"))]),
        "Independent selected 2025 assumptions: SBIE=1000000*.096+2000000*.076; topup=(.15-.09)*(20000000-248000); not full-law assurance",
    )
    legs = [
        ("cash", "125", "0", True),
        ("equity", "0", "125", True),
        ("cash", "75", "0", False),
        ("revenue", "0", "75", False),
        ("expense", "35", "0", False),
        ("cash", "0", "35", False),
    ]
    inputs = [
        {
            "account_code": code,
            "functional_currency": "AED",
            "base_debit": debit,
            "base_credit": credit,
            "opening": opening,
        }
        for code, debit, credit, opening in legs
    ]
    tb = trial_balance(inputs, "AED")
    actual = {row["account_code"]: row["closing"] for row in tb}
    actual["total"] = sum(actual.values())
    check(
        "TB-OPENING-MOVEMENTS",
        inputs,
        {"cash": "165", "equity": "-125", "revenue": "-75", "expense": "35", "total": "0"},
        actual,
        "Independent six-leg double entry fixture; cash=125+75-35",
        "0",
    )
    return receipts


if __name__ == "__main__":
    result = evaluate()
    (ROOT / "docs/phase-12/financial-results.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "passed": sum(x["status"] == "PASS" for x in result),
                "failed": sum(x["status"] != "PASS" for x in result),
            }
        )
    )
    raise SystemExit(any(x["status"] != "PASS" for x in result))
