"""Independent fixed-value arithmetic checks, without changing golden values."""

import json
import sys
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.ifrs.calculations import calculate
from app.modules.tax.calculations import interest, standard_tax
from app.modules.tax.schemas import RuleParameters
from tests.phase5.test_calculations import ECL_INPUT, LEASE
from tests.phase6.test_calculations import interest_input
from validate_phase12_financials import evaluate


def main():
    results = evaluate()

    def check(name, actual, expected, rationale):
        difference = D(str(actual)) - D(expected)
        results.append(
            {
                "id": name,
                "actual": str(actual),
                "expected": expected,
                "difference": str(difference),
                "status": "PASS" if difference == 0 else "FAIL",
                "oracle_source": rationale,
            }
        )

    for amount, expected in [
        ("-1", "0"),
        ("0", "0"),
        ("374999", "0"),
        ("375000", "0"),
        ("375001", "0.09"),
        ("1000000", "56250"),
    ]:
        check(
            "CT-BAND-" + amount,
            standard_tax(amount, RuleParameters()),
            expected,
            "Fixed boundary oracle: max(income-375000,0)*0.09",
        )
    for stage, expected in [(1, "65"), (2, "165"), (3, "500")]:
        check(
            f"ECL-STAGE-{stage}",
            calculate(
                "ecl",
                {
                    **ECL_INPUT,
                    "exposures": [
                        {"reference": "SYN-1", "amount": "1000", "stage": stage}
                    ],
                },
            )["total_ecl"],
            expected,
            "Fixed probability-weighted scenario loss oracle, zero discount rate",
        )
    liability = calculate("lease", LEASE)
    for field, expected in [("initial_liability", "1000"), ("initial_rou", "1000")]:
        check(
            "LEASE-" + field, liability[field], expected, "Single year:1100/1.10=1000"
        )
    for field, expected in [
        ("adjusted_ebitda", "50000000"),
        ("limit", "15000000"),
        ("current_disallowed", "5000000"),
    ]:
        check(
            "INTEREST-" + field,
            interest(interest_input(), RuleParameters())[field],
            expected,
            "Adjusted EBITDA30m+20m=50m;30%=15m;20m-15m=5m",
        )
    (ROOT / "docs/qa-campaign/financial-results.json").write_text(
        json.dumps(results, indent=2), encoding="utf8"
    )
    print(
        json.dumps(
            {
                "passed": sum(r["status"] == "PASS" for r in results),
                "failed": sum(r["status"] == "FAIL" for r in results),
            }
        )
    )
    return any(r["status"] == "FAIL" for r in results)


if __name__ == "__main__":
    raise SystemExit(main())
