"""Source-linked accounting, payroll and procurement extensions of shared audit workflows."""

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from babel.numbers import get_currency_precision

from app.modules.country_workflows.audit_calculations import control_rows, money, result
from app.modules.ifrs.calculations import ecl, fixed_assets
from app.modules.ifrs.schemas import ECL, Asset, FixedAssets


def rounded(value, currency):
    return value.quantize(
        Decimal(1).scaleb(-get_currency_precision(currency)), rounding=ROUND_HALF_UP
    )


def provision_matrix(data, tables):
    rows = control_rows(data, tables)
    blocked = any(r["state"] != "MATCHED" for r in rows)
    rates = [
        r
        for r in tables["rates"]
        if date.fromisoformat(r["effective_from"])
        <= data.as_of
        <= date.fromisoformat(r["effective_to"])
    ]
    exposures = defaultdict(list)
    for item in tables["items"]:
        days = max(0, (data.as_of - date.fromisoformat(item["due_date"])).days)
        selected = [
            r
            for r in rates
            if r["min_overdue_days"] <= days <= r["max_overdue_days"]
            and r.get("segment", "") in {"", item.get("segment", "")}
        ]
        state = (
            "PAYABLE_NOT_ELIGIBLE"
            if item["side"] != "receivable"
            else (
                "CREDIT_ALLOCATION_REQUIRED"
                if money(item) < 0
                else "RATE_MISSING"
                if not selected
                else "AMBIGUOUS_RATE"
                if len(selected) != 1
                else "MATCHED"
            )
        )
        if state != "MATCHED":
            blocked = True
            rows.append({"id": "exposure:" + item["id"], "state": state, "amount": item["amount"]})
        else:
            exposures[item["currency"]].append((item, selected[0], days))
    totals = {}
    for currency, group in exposures.items():
        # Stage is unused by the existing provision-matrix branch; no SICR inference is made.
        request = ECL.model_validate(
            {
                "approach": "provision_matrix",
                "effective_interest_rate": "0",
                "historical_data_source": "Reviewed retained loss-rate evidence",
                "sicr_methodology": "Not inferred; provision-matrix calculation only",
                "default_definition": "Independently reviewed matrix assumptions",
                "write_off_policy": "No automatic write-offs",
                "exposures": [
                    {
                        "reference": i["id"],
                        "amount": i["amount"],
                        "stage": 2,
                        "segment": rate["id"],
                        "override_loss": i.get("specific_ecl"),
                        "override_reason": i.get("specific_assessment", ""),
                    }
                    for i, rate, _ in group
                ],
                "segment_loss_rates": {
                    rate["id"]: rate["weighted_loss_rate"] for _, rate, _ in group
                },
                "scenarios": [
                    {
                        "name": "Reviewed weighted matrix",
                        "probability": "1",
                        "pd_12_month": "0",
                        "pd_lifetime": "0",
                        "lgd": "0",
                    }
                ],
            }
        )
        calculated = ecl(request)
        totals[currency] = str(calculated["total_ecl"])
        by_ref = {r["reference"]: r for r in calculated["schedule"]}
        for item, rate, days in group:
            rows.append(
                {
                    "id": "exposure:" + item["id"],
                    "item_id": item["id"],
                    "currency": currency,
                    "balance": item["amount"],
                    "overdue_days": days,
                    "loss_rate_source_id": rate["id"],
                    "weighted_loss_rate": rate["weighted_loss_rate"],
                    "ecl": str(by_ref[item["id"]]["ecl"]),
                    "state": "MATCHED",
                }
            )
    return {
        **result(
            rows,
            blocked,
            [
                "Uses the existing IFRS 9 provision-matrix engine with professionally supplied weighted loss rates",
                "No loss rates, credit-note allocations, SICR judgments or postings are inferred or approved",
                "Per-currency totals remain separate; unsupported items block approval rather than disappear",
            ],
        ),
        "total_ecl_by_currency": totals,
        "calculation_engine": "ifrs.ecl/provision_matrix",
    }


def cash_forecast(data, tables):
    groups = defaultdict(list)
    for row in tables["forecast"]:
        if not data.as_of < date.fromisoformat(row["date"]) <= data.review_through:
            raise ValueError(
                "Forecast dates must fall after reporting and within the review horizon"
            )
        groups[(row["scenario"], row["currency"])].append(row)
    rows = []
    blocked = False
    for (scenario, currency), group in sorted(groups.items()):
        group.sort(key=lambda r: r["date"])
        if len({r["date"] for r in group}) != len(group):
            raise ValueError("Duplicate scenario/currency forecast date")
        previous = None
        for row in group:
            opening = money(row, "opening_cash")
            funding = money(row, "committed_funding")
            exceptions = []
            if previous is not None and abs(opening - previous) > data.tolerance:
                exceptions.append("OPENING_CASH_BRIDGE_DIFFERENCE")
                blocked = True
            if funding and not row["funding_evidence"]:
                exceptions.append("FUNDING_EVIDENCE_MISSING")
                blocked = True
            # Carry the recalculated cash chain rather than resetting it to an inconsistent input.
            expected = opening if previous is None else previous
            closing = expected + money(row, "inflows") - money(row, "outflows") + funding
            gap = max(Decimal(0), money(row, "minimum_cash") - closing)
            if gap:
                exceptions.append("MINIMUM_CASH_BREACH")
            rows.append(
                {
                    "id": row["id"],
                    "scenario": scenario,
                    "currency": currency,
                    "date": row["date"],
                    "recalculated_closing": str(closing),
                    "funding_gap": str(gap),
                    "exceptions": exceptions,
                    "state": "EXCEPTIONS" if exceptions else "MATCHED",
                }
            )
            previous = closing
        if date.fromisoformat(group[-1]["date"]) != data.review_through:
            rows.append(
                {"id": f"horizon:{scenario}:{currency}", "state": "FORECAST_HORIZON_MISSING"}
            )
            blocked = True
    if not groups:
        blocked = True
        rows.append({"id": "forecast-population", "state": "FORECAST_MISSING"})
    return result(
        rows,
        blocked,
        [
            "Scenarios, minimum cash and funding commitments are supplied assumptions requiring review",
            "Forecast interval completeness and the appropriate going-concern horizon need professional assessment",
            "A positive forecast does not establish a going-concern conclusion",
        ],
    )


def procurement(data, tables):
    grouped: defaultdict[tuple[str, str, str, str], defaultdict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    types = {"orders": "order", "receipts": "receipt", "invoices": "invoice", "payments": "payment"}
    for role, entries in tables.items():
        for row in entries:
            if row["document_type"] != types[role]:
                raise ValueError("Purchase document type does not match its source role")
            if date.fromisoformat(row["date"]) > data.as_of:
                raise ValueError("Purchase document is after the scoped audit date")
            k = (row["order_id"], row["line_reference"], row["vendor"], row["currency"])
            grouped[k][role].append(row)
    rows = []
    proposals = []
    blocked = False
    for index, (k, group) in enumerate(sorted(grouped.items()), 1):
        exceptions = []
        if len(group["orders"]) != 1:
            exceptions.append("ORDER_MISSING_OR_AMBIGUOUS")
            blocked = True
        for role in ("receipts", "invoices", "payments"):
            if not group[role]:
                exceptions.append("MISSING_" + role.upper())
        qty = {role: sum((money(r, "quantity") for r in group[role]), Decimal(0)) for role in types}
        amounts = {role: sum((money(r) for r in group[role]), Decimal(0)) for role in types}
        for role in ("orders", "receipts", "invoices"):
            if any(
                abs(money(r) - money(r, "quantity") * money(r, "unit_price")) > data.tolerance
                for r in group[role]
            ):
                exceptions.append("EXTENSION_DIFFERENCE_" + role.upper())
        if qty["receipts"] > qty["orders"]:
            exceptions.append("RECEIPT_EXCEEDS_ORDER")
        if qty["invoices"] > qty["receipts"]:
            exceptions.append("INVOICE_EXCEEDS_RECEIPT")
        if group["orders"] and any(
            abs(money(r, "unit_price") - money(group["orders"][0], "unit_price")) > data.tolerance
            for r in group["invoices"]
        ):
            exceptions.append("PRICE_DIFFERENCE")
        if abs(amounts["invoices"] - amounts["payments"]) > data.tolerance:
            exceptions.append("PAYMENT_DIFFERENCE")
        outstanding = max(Decimal(0), amounts["invoices"] - amounts["payments"])
        if outstanding:
            holds = []
            if any(code not in {"PAYMENT_DIFFERENCE", "MISSING_PAYMENTS"} for code in exceptions):
                holds.append("MATCHING_EXCEPTION")
            for document in [*group["orders"], *group["invoices"]]:
                if document.get("approval_status") != "approved":
                    holds.append("DOCUMENT_APPROVAL_REQUIRED")
                if document.get("payment_hold"):
                    holds.append("SOURCE_PAYMENT_HOLD")
                if not document.get("bank_change_verified"):
                    holds.append("INDEPENDENT_BANK_DETAILS_VERIFICATION_REQUIRED")
                if not document.get("approved_by") or document.get("approved_by") == document.get(
                    "prepared_by"
                ):
                    holds.append("SEGREGATION_OF_DUTIES_NOT_ESTABLISHED")
            proposals.append(
                {
                    "order_id": k[0],
                    "line_reference": k[1],
                    "vendor": k[2],
                    "currency": k[3],
                    "amount": str(outstanding),
                    "state": "HOLD" if holds else "DRAFT_REQUIRES_PAYMENT_APPROVAL",
                    "holds": sorted(set(holds)),
                    "payment_instruction_created": False,
                    "source_invoice_ids": [r["id"] for r in group["invoices"]],
                }
            )
        rows.append(
            {
                "id": f"purchase-{index}",
                "order_id": k[0],
                "line_reference": k[1],
                "vendor": k[2],
                "currency": k[3],
                "quantities": {r: str(v) for r, v in qty.items()},
                "amounts": {r: str(v) for r, v in amounts.items()},
                "exceptions": exceptions,
                "source_ids": {role: [r["id"] for r in group[role]] for role in types},
                "state": "EXCEPTIONS" if exceptions else "MATCHED",
            }
        )
    return {
        **result(
            rows,
            blocked,
            [
                "Bounded positive-quantity purchase lines; returns, tax-inclusive pricing and service acceptance need separate assessment",
                "Partial receipts and unpaid invoices may be legitimate; exception dispositions require evidence",
            ],
        ),
        "payment_proposals": proposals,
    }


def vendor_conflicts(data, tables):
    employees = defaultdict(list)
    rows = []
    for role in ("vendors", "employees"):
        for row in tables[role]:
            if date.fromisoformat(row["effective_from"]) > data.as_of or (
                row.get("effective_to") and date.fromisoformat(row["effective_to"]) < data.as_of
            ):
                continue
            if role == "employees":
                employees[row["bank_account_hash"]].append(row["id"])
    for vendor in tables["vendors"]:
        if date.fromisoformat(vendor["effective_from"]) > data.as_of or (
            vendor.get("effective_to") and date.fromisoformat(vendor["effective_to"]) < data.as_of
        ):
            continue
        shared = employees.get(vendor["bank_account_hash"], [])
        rows.append(
            {
                "id": vendor["id"],
                "vendor_id": vendor["id"],
                "employee_ids": shared,
                "state": "SHARED_BANK_ACCOUNT" if shared else "MATCHED",
            }
        )
    return result(
        rows,
        limitations=[
            "Bank identifiers must use the same independently validated normalization/hash scheme",
            "A shared bank account is an investigation signal, not evidence of fraud or beneficial ownership",
        ],
    )


def expenses(data, tables):
    hashes = defaultdict(list)
    for claim in tables["claims"]:
        hashes[claim["receipt_sha256"]].append(claim["id"])
    rows = []
    for claim in tables["claims"]:
        if date.fromisoformat(claim["date"]) > data.as_of:
            raise ValueError("Expense claim is after the audit date")
        exceptions = []
        if money(claim) > money(claim, "approved_limit") + data.tolerance:
            exceptions.append("POLICY_LIMIT_EXCEEDED")
        if not claim["approved"]:
            exceptions.append("APPROVAL_MISSING")
        reused = hashes[claim["receipt_sha256"]]
        if len(reused) > 1:
            exceptions.append("REUSED_RECEIPT")
        rows.append(
            {
                "id": claim["id"],
                "employee": claim["employee"],
                "currency": claim["currency"],
                "amount": claim["amount"],
                "related_claim_ids": [i for i in reused if i != claim["id"]],
                "exceptions": exceptions,
                "state": "EXCEPTIONS" if exceptions else "MATCHED",
            }
        )
    return result(
        rows,
        limitations=[
            "Policy limits and approval status are reviewed source inputs; personal-use classification is not inferred",
            "Receipt reuse may represent a valid split claim and requires investigation",
        ],
    )


def benefits(data, tables):
    rows = []
    blocked = False
    for employee in tables["employees"]:
        end = date.fromisoformat(employee["service_end"])
        if end > data.as_of:
            raise ValueError("Service end is after the audit date")
        rules = [
            r
            for r in tables["rules"]
            if r["regime"] == employee["regime"]
            and r["cohort"] == employee["cohort"]
            and r["work_model"] == employee["work_model"]
            and (
                "selected_service_end_dates" not in r
                or employee["service_end"] in r["selected_service_end_dates"]
            )
            and date.fromisoformat(r["effective_from"])
            <= end
            <= date.fromisoformat(r["effective_to"])
        ]
        state = (
            "ALTERNATIVE_SCHEME_REQUIRES_ASSESSMENT"
            if employee["scheme"] != "gratuity"
            else "WORK_MODEL_CHANGE_REQUIRES_SEGMENTED_ASSESSMENT"
            if not employee["work_model_constant_for_service"]
            else "WORK_MODEL_REQUIRES_ASSESSMENT"
            if employee["work_model"] == "other"
            else (
                "RULE_MISSING" if not rules else "AMBIGUOUS_RULE" if len(rules) != 1 else "MATCHED"
            )
        )
        if state != "MATCHED":
            rows.append(
                {
                    "id": employee["id"],
                    "regime": employee["regime"],
                    "cohort": employee["cohort"],
                    "work_model": employee["work_model"],
                    "state": state,
                }
            )
            blocked = True
            continue
        rule = rules[0]
        days = (
            (end - date.fromisoformat(employee["service_start"])).days
            + 1
            - employee["excluded_service_days"]
        )
        years = Decimal(days) / money(rule, "year_days")
        first = min(years, money(rule, "first_tier_years"))
        later = max(Decimal(0), years - first)
        part_time = employee["work_model"] == "part-time"
        salary = money(
            employee, "full_time_monthly_basic_salary" if part_time else "monthly_basic_salary"
        )
        proportion = (
            money(employee, "annual_contract_hours") / money(employee, "annual_full_time_hours")
            if part_time
            else Decimal(1)
        )
        expected = (
            salary
            / money(rule, "salary_divisor")
            * (first * money(rule, "first_tier_days") + later * money(rule, "later_tier_days"))
        )
        if years < money(rule, "minimum_service_years"):
            expected = Decimal(0)
        full_time_equivalent = min(expected, salary * money(rule, "maximum_salary_months"))
        expected = rounded(full_time_equivalent * proportion, employee["currency"])
        difference = money(employee) - expected
        rows.append(
            {
                "id": employee["id"],
                "currency": employee["currency"],
                "regime": employee["regime"],
                "cohort": employee["cohort"],
                "work_model": employee["work_model"],
                "work_model_assessment": employee["work_model_assessment"],
                "work_model_constant_for_service": employee["work_model_constant_for_service"],
                "annual_contract_hours": employee["annual_contract_hours"],
                "annual_full_time_hours": employee["annual_full_time_hours"],
                "benefit_proportion": str(proportion),
                "full_time_salary_basis": str(salary),
                "full_time_equivalent_benefit": str(full_time_equivalent),
                "eligible_service_days": days,
                "service_years": str(years),
                "rule_source_id": rule["id"],
                "rule_document_version_id": rule["source_evidence_version_id"],
                **(
                    {
                        "rule_source_document_id": rule["source_document_id"],
                        "published_rule_version_id": rule["published_rule_version_id"],
                        "published_rule_sha256": rule["published_rule_sha256"],
                        "rule_source_copies": rule["source_copies"],
                    }
                    if rule.get("published_rule_version_id")
                    else {}
                ),
                "rule_document_sha256": rule["source_sha256"],
                "rule_version": rule["source_version"],
                "rule_url": rule["source_url"],
                "applicability_review": rule["applicability_review"],
                "expected_benefit": str(expected),
                "paid_benefit": employee["amount"],
                "difference": str(difference),
                "state": "BENEFIT_DIFFERENCE" if abs(difference) > data.tolerance else "MATCHED",
            }
        )
    return result(
        rows,
        blocked,
        [
            "No UAE statutory rates are hardcoded; every regime, tier, divisor, eligibility and cap is supplied evidence",
            "Inclusive eligible days divided by the supplied year basis; rule applicability must be professionally validated",
            "Alternative schemes and unsupported transitional/contractual treatment block this bounded computation",
            "Part-time calculations use explicitly assessed full-time salary and annual contract-hour comparators; no work model, pension cohort or statutory applicability is inferred",
        ],
    )


def assets(data, tables):
    groups = defaultdict(list)
    seen = set()
    for asset in tables["register"]:
        if asset["reference"] in seen:
            raise ValueError("Duplicate asset reference in the register")
        seen.add(asset["reference"])
        groups[(asset["account"], asset["currency"])].append(asset)
    controls = {}
    for control in tables["controls"]:
        key = (control["account"], control["currency"])
        if control["as_of"] != data.as_of.isoformat() or key in controls:
            raise ValueError("Asset control date differs or account/currency control is duplicated")
        controls[key] = control
    rows = []
    blocked = False
    for index, key in enumerate(sorted(groups.keys() | controls.keys()), 1):
        group = groups[key]
        control = controls.get(key)
        carrying = sum((money(a, "recorded_carrying") for a in group), Decimal(0))
        delta = carrying - money(control) if control else None
        state = (
            "GL_CONTROL_MISSING"
            if not control
            else (
                "GL_CONTROL_DIFFERENCE"
                if delta is not None and abs(delta) > data.tolerance
                else "MATCHED"
            )
        )
        blocked |= state != "MATCHED"
        rows.append(
            {
                "id": f"asset-control-{index}",
                "account": key[0],
                "currency": key[1],
                "register_carrying": str(carrying),
                "difference": str(delta) if delta is not None else None,
                "state": state,
            }
        )
        if not group:
            continue
        calculation = fixed_assets(
            FixedAssets.model_validate(
                {
                    "period_start": data.period_start,
                    "period_end": data.as_of,
                    "assets": [
                        {k: v for k, v in a.items() if k in Asset.model_fields} for a in group
                    ],
                }
            )
        )
        by_reference = {r["reference"]: r for r in calculation["schedule"]}
        for asset in group:
            computed = by_reference[asset["reference"]]
            exceptions = []
            disposed = (
                asset.get("disposal_date") and asset["disposal_date"] <= data.as_of.isoformat()
            )
            if not asset["ownership_evidence"]:
                exceptions.append("OWNERSHIP_EVIDENCE_MISSING")
            if not disposed and not asset["physical_evidence"]:
                exceptions.append("PHYSICAL_EVIDENCE_MISSING")
            blocked |= bool(exceptions)
            if (
                abs(money(asset, "recorded_depreciation") - computed["depreciation"])
                > data.tolerance
            ):
                exceptions.append("DEPRECIATION_DIFFERENCE")
            if (
                abs(money(asset, "recorded_carrying") - computed["closing_carrying"])
                > data.tolerance
            ):
                exceptions.append("CARRYING_DIFFERENCE")
            rows.append(
                {
                    "id": asset["id"],
                    "reference": asset["reference"],
                    "currency": key[1],
                    "expected_depreciation": str(computed["depreciation"]),
                    "expected_carrying": str(computed["closing_carrying"]),
                    "exceptions": exceptions,
                    "state": "EXCEPTIONS" if exceptions else "MATCHED",
                }
            )
    return {
        **result(
            rows,
            blocked,
            [
                "Reuses IFRS fixed-assets calculations; lives, residuals, impairment and ownership remain reviewed source assumptions",
                "Physical evidence is a reference, not automatic attendance or verification; no approved ledger is changed",
            ],
        ),
        "calculation_engine": "ifrs.fixed_assets",
    }


def stock_bridge(data, tables):
    from app.modules.country_workflows.calculations import inventory
    from app.modules.country_workflows.inventory_controls import stock_key

    def key(row):
        return stock_key(row)

    controlled = data.stock_bridge_mode == "bidirectional-controlled"
    through = data.review_through if controlled else data.as_of
    counts = {}
    for count in tables["counts"]:
        if key(count) in counts or date.fromisoformat(count["count_date"]) > through:
            raise ValueError("Duplicate or future-dated stock count")
        counts[key(count)] = count
    if any(book["count_date"] != data.as_of.isoformat() for book in tables["books"]):
        raise ValueError("Stock books must contain reporting-date balances")
    movements = defaultdict(list)
    seen = set()
    for movement in tables["movements"]:
        count = counts.get(key(movement))
        first, last = sorted([count["count_date"], data.as_of.isoformat()]) if count else (None, None)
        if not count or not first < movement["date"] <= last:
            raise ValueError(
                "Stock movement has no count or lies outside its count-to-reporting bridge"
            )
        identity = (key(movement), movement["date"], movement["evidence_reference"], money(movement, "quantity"))
        if controlled and identity in seen:
            raise ValueError("Duplicate stock movement observation; retain distinct line evidence references")
        seen.add(identity)
        movements[key(movement)].append(movement)
    derived = []
    bridges = []
    for k, count in counts.items():
        delta = sum((money(r, "quantity") for r in movements[k]), Decimal(0))
        backward = count["count_date"] > data.as_of.isoformat()
        signed_delta = -delta if backward else delta
        derived.append(
            {
                **count,
                "quantity": str(money(count, "quantity") + signed_delta),
                "count_date": data.as_of.isoformat(),
            }
        )
        bridges.append(
            {
                "count_source_id": count["id"],
                "original_count_date": count["count_date"],
                "movement_source_ids": [r["id"] for r in movements[k]],
                "movement_quantity": str(delta),
                "site": count["site"], "sku": count["sku"], "lot": count.get("lot", ""),
                "uom": count["uom"], "currency": count["currency"],
                "direction": "ROLL_BACK" if backward else "ROLL_FORWARD" if count["count_date"] < data.as_of.isoformat() else "ALREADY_AT_REPORTING_DATE",
                "original_count_quantity": count["quantity"],
                "applied_movement_quantity": str(signed_delta),
                "reporting_date_quantity": str(money(count, "quantity") + signed_delta),
                "cutoff_basis": "EXCLUSIVE_EARLIER_DAY_END_THROUGH_INCLUSIVE_LATER_DAY_END",
                "original_condition_date": count["count_date"],
                "reporting_date_condition": "NOT_ESTABLISHED_BY_QUANTITY_BRIDGE",
            }
        )
    computed = inventory(data, {"books": tables["books"], "count": derived})
    return {
        **computed,
        "count_bridges": bridges,
        "coverage": {**computed["coverage"], "basis": "Uploaded book monetary value supported by calculated reporting-date quantities from retained counts and movements; not reporting-date physical verification"},
        "calculation_engine": "country_workflows.inventory",
        "count_bridge_mode": data.stock_bridge_mode,
        "cutoff_assessment": data.stock_cutoff_assessment.strip(),
        "limitations": [
            *computed["limitations"],
            "Reporting-date counts are calculated from uploaded counts and movements; no reporting-date physical attendance is inferred",
            "Movement and count population completeness require independent control evidence",
            "Controlled mode checks original row and directional quantity controls by site/SKU/lot/UOM/currency; incompatible units and lots never net",
            "Original count condition is retained; quantity roll-forward or roll-back does not establish reporting-date condition or physical attendance",
        ],
    }


PRACTICE_CALCULATORS = {
    "asset-register-review": assets,
    "inventory-count-bridge": stock_bridge,
    "receivables-ecl": provision_matrix,
    "going-concern-cash": cash_forecast,
    "procurement-match": procurement,
    "vendor-employee-conflicts": vendor_conflicts,
    "employee-expenses": expenses,
    "uae-benefit-review": benefits,
}
