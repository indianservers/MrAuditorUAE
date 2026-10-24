"""Explainable operational comparisons; no invented market, tariff or statutory data."""

import hashlib
from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.modules.country_workflows.audit_calculations import money, result
from app.modules.ifrs.calculations import revenue
from app.modules.ifrs.schemas import Revenue
from app.modules.intelligence.matching import reconcile_transactions


def trade_key(row):
    return (row["shipment"], row["product"], row["counterparty"], row["currency"], row["uom"])


def trade(data, tables):
    customs = data.workflow == "customs-reconciliation"
    roles = (
        ("declarations", "invoices", "receipts")
        if customs
        else ("invoices", "shipments", "payments")
    )
    groups: defaultdict[tuple, defaultdict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for role in roles:
        for row in tables[role]:
            if date.fromisoformat(row["date"]) > data.as_of:
                raise ValueError("Trade document is after the audit date")
            groups[trade_key(row)][role].append(row)
    rows = []
    blocked = False
    for index, (key, group) in enumerate(sorted(groups.items()), 1):
        exceptions = ["MISSING_" + role.upper() for role in roles if not group[role]]
        quantities = {
            role: sum((money(r, "quantity") for r in group[role]), Decimal(0)) for role in roles
        }
        amounts = {role: sum((money(r) for r in group[role]), Decimal(0)) for role in roles}
        anchor = "declarations" if customs else "invoices"
        quantity_roles = ("invoices", "receipts") if customs else ("shipments",)
        if any(quantities[r] != quantities[anchor] for r in quantity_roles):
            exceptions.append("QUANTITY_DIFFERENCE")
        if customs:
            adjusted = amounts["invoices"] + sum(
                (money(r, "valuation_adjustment") for r in group["declarations"]), Decimal(0)
            )
            if abs(amounts["declarations"] - adjusted) > data.tolerance:
                exceptions.append("CUSTOMS_VALUE_DIFFERENCE")
            for row in group["declarations"]:
                if row["reviewed_duty_rate"] is None or not row["duty_rule_reference"]:
                    exceptions.append("DUTY_RULE_EVIDENCE_MISSING")
                    blocked = True
                elif (
                    abs(money(row, "declared_duty") - money(row) * money(row, "reviewed_duty_rate"))
                    > data.tolerance
                ):
                    exceptions.append("DUTY_DIFFERENCE")
        else:
            if abs(amounts["invoices"] - amounts["payments"]) > data.tolerance:
                exceptions.append("PAYMENT_DIFFERENCE")
            for invoice in group["invoices"]:
                day = date.fromisoformat(invoice["date"])
                bands = [
                    b
                    for b in tables["prices"]
                    if (b["product"], b["currency"], b["uom"]) == key[1:2] + key[3:]
                    and date.fromisoformat(b["effective_from"])
                    <= day
                    <= date.fromisoformat(b["effective_to"])
                ]
                if len(bands) != 1 or money(invoice, "quantity") == 0:
                    exceptions.append("PRICE_NOT_TESTABLE")
                    blocked = True
                else:
                    price = money(invoice) / money(invoice, "quantity")
                    if (
                        not money(bands[0], "minimum_unit_price")
                        <= price
                        <= money(bands[0], "maximum_unit_price")
                    ):
                        exceptions.append("PRICE_OUTSIDE_SOURCED_BAND")
        rows.append(
            {
                "id": f"trade-{index}",
                "shipment": key[0],
                "product": key[1],
                "counterparty": key[2],
                "currency": key[3],
                "uom": key[4],
                "quantities": {r: str(v) for r, v in quantities.items()},
                "amounts": {r: str(v) for r, v in amounts.items()},
                "source_ids": {role: [r["id"] for r in group[role]] for role in roles},
                "exceptions": sorted(set(exceptions)),
                "state": "EXCEPTIONS" if exceptions else "MATCHED",
            }
        )
    return result(
        rows,
        blocked,
        [
            "Document linkage and valuation adjustments require independent source review; partial shipments may explain exceptions",
            "Duty rates and price bands are supplied evidence, not live customs decisions or invented benchmarks",
            "Price/payment exceptions do not establish money laundering; no AML case/report is generated",
        ],
    )


def excise(data, tables):
    stocks: defaultdict[tuple, Decimal] = defaultdict(Decimal)
    boundaries: defaultdict[tuple, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
    closing: dict[tuple, Decimal] = {}
    tax: defaultdict[tuple, Decimal] = defaultdict(Decimal)
    rows = []
    blocked = False
    for movement in tables["movements"]:
        when = date.fromisoformat(movement["date"])
        if not data.period_start <= when <= data.as_of:
            raise ValueError("Excise stock movements must be within the reporting period")
        key = (movement["product"], movement["location"], movement["currency"], movement["uom"])
        kind = movement["kind"]
        if kind == "opening":
            if when != data.period_start:
                raise ValueError("Excise opening balance must use reporting-period start")
            boundaries[key]["opening"] += 1
        if kind == "closing":
            if when != data.as_of:
                raise ValueError("Excise closing balance must use the audit date")
            boundaries[key]["closing"] += 1
            closing[key] = money(movement, "quantity")
        else:
            stocks[key] += money(movement, "quantity") * (
                -1 if kind in {"taxable-release", "transfer-out", "loss"} else 1
            )
        if kind == "taxable-release":
            rates = [
                r
                for r in tables["rules"]
                if (r["product"], r["currency"], r["uom"]) == (key[0], key[2], key[3])
                and date.fromisoformat(r["effective_from"])
                <= when
                <= date.fromisoformat(r["effective_to"])
            ]
            if len(rates) != 1:
                rows.append({"id": movement["id"], "state": "EXCISE_RULE_MISSING_OR_AMBIGUOUS"})
                blocked = True
            else:
                rule = rates[0]
                basis = money(movement, "quantity" if rule["basis"] == "quantity" else "amount")
                tax[(key[0], key[2])] += basis * money(rule, "rate")
    for index, key in enumerate(sorted(stocks.keys() | closing.keys()), 1):
        valid = boundaries[key]["opening"] == boundaries[key]["closing"] == 1
        difference = closing.get(key, Decimal(0)) - stocks[key]
        state = (
            "STOCK_BOUNDARY_MISSING_OR_AMBIGUOUS"
            if not valid
            else (
                "NEGATIVE_STOCK"
                if stocks[key] < 0
                else "STOCK_DIFFERENCE"
                if difference
                else "MATCHED"
            )
        )
        blocked |= state != "MATCHED"
        rows.append(
            {
                "id": f"excise-stock-{index}",
                "product": key[0],
                "location": key[1],
                "currency": key[2],
                "uom": key[3],
                "expected_closing_quantity": str(stocks[key]),
                "difference": str(difference),
                "state": state,
            }
        )
    declarations: dict[tuple, dict] = {}
    for declaration in tables["returns"]:
        if (
            declaration["period_start"] != data.period_start.isoformat()
            or declaration["period_end"] != data.as_of.isoformat()
        ):
            raise ValueError("Excise return must match the declared reporting period")
        tax_key = (declaration["product"], declaration["currency"])
        if tax_key in declarations:
            raise ValueError("Duplicate excise return product/currency")
        declarations[tax_key] = declaration
    for index, tax_key in enumerate(sorted(tax.keys() | declarations.keys()), 1):
        declaration = declarations.get(tax_key)
        tax_difference = money(declaration) - tax[tax_key] if declaration else None
        state = (
            "EXCISE_RETURN_MISSING"
            if declaration is None
            else (
                "EXCISE_TAX_DIFFERENCE"
                if tax_difference is not None and abs(tax_difference) > data.tolerance
                else "MATCHED"
            )
        )
        blocked |= declaration is None
        rows.append(
            {
                "id": f"excise-tax-{index}",
                "product": tax_key[0],
                "currency": tax_key[1],
                "expected_tax": str(tax[tax_key]),
                "difference": str(tax_difference) if tax_difference is not None else None,
                "state": state,
            }
        )
    return result(
        rows,
        blocked,
        [
            "Taxable-release designation, product scope, rates and valuation basis are reviewed inputs, not statutory determinations",
            "Quantity/value multiplication is unrounded; reconcile using the declared approved tolerance and statutory rounding assessment",
            "Transfer counterpart completeness and excise warehouse eligibility require separate evidence",
        ],
    )


def gold(data, tables):
    quantities: defaultdict[tuple, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    openings: defaultdict[tuple, int] = defaultdict(int)
    rows = []
    blocked = False
    for entry in tables["books"]:
        when = date.fromisoformat(entry["date"])
        if not data.period_start <= when <= data.as_of or entry["kind"] == "count":
            raise ValueError("Gold books require in-period movements, not count rows")
        key = (entry["lot"], entry["location"])
        if entry["kind"] == "opening":
            if when != data.period_start:
                raise ValueError("Gold opening stock must use reporting-period start")
            openings[key] += 1
        sign = -1 if entry["kind"] in {"issue", "loss"} else 1
        gross = money(entry, "gross_grams") * sign
        quantities[key][0] += gross
        quantities[key][1] += gross * money(entry, "purity")
        if entry["ownership"] != "owned":
            rows.append({"id": "book:" + entry["id"], "state": "OWNERSHIP_UNCONFIRMED"})
            blocked = True
    counts = {}
    for entry in tables["counts"]:
        key = (entry["lot"], entry["location"])
        if key in counts:
            raise ValueError("Duplicate gold lot/location count")
        if entry["kind"] != "count" or date.fromisoformat(entry["date"]) != data.as_of:
            raise ValueError("Gold counts must be reporting-date count rows")
        counts[key] = entry
    for index, key in enumerate(sorted(quantities.keys() | counts.keys()), 1):
        count = counts.get(key)
        gross, fine = quantities[key]
        gross_delta = money(count, "gross_grams") - gross if count else None
        fine_delta = money(count, "gross_grams") * money(count, "purity") - fine if count else None
        state = (
            "OPENING_MISSING_OR_AMBIGUOUS"
            if openings[key] != 1
            else (
                "COUNT_MISSING"
                if not count
                else "OWNERSHIP_UNCONFIRMED"
                if count["ownership"] != "owned"
                else "NEGATIVE_STOCK"
                if gross < 0 or fine < 0
                else "METAL_DIFFERENCE"
                if gross_delta != 0 or fine_delta != 0
                else "MATCHED"
            )
        )
        blocked |= state in {
            "COUNT_MISSING",
            "OPENING_MISSING_OR_AMBIGUOUS",
            "OWNERSHIP_UNCONFIRMED",
            "NEGATIVE_STOCK",
        }
        rows.append(
            {
                "id": f"metal-{index}",
                "lot": key[0],
                "location": key[1],
                "book_gross_grams": str(gross),
                "book_fine_grams": str(fine),
                "gross_difference_grams": str(gross_delta) if gross_delta is not None else None,
                "fine_difference_grams": str(fine_delta) if fine_delta is not None else None,
                "state": state,
            }
        )
    return result(
        rows,
        blocked,
        [
            "All weights are grams and purity is a 0–1 fraction; count/purity authenticity requires professional verification",
            "No physical assay, refining yield model, live metal pricing or AML clearance is performed",
        ],
    )


def escrow(data, tables):
    authorisations = {a["id"]: a for a in tables["authorisations"]}
    used: defaultdict[str, Decimal] = defaultdict(Decimal)
    groups: defaultdict[tuple, defaultdict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    rows = []
    blocked = False
    for role in ("books", "bank"):
        for entry in tables[role]:
            if date.fromisoformat(entry["date"]) > data.as_of:
                raise ValueError("Escrow entry is after the reporting date")
            groups[(entry["project"], entry["account"], entry["currency"])][role].append(entry)
            if role != "books" or money(entry) >= 0:
                continue
            auth = authorisations.get(entry["authorisation_id"])
            if auth is None:
                rows.append(
                    {
                        "id": "authority:" + entry["id"],
                        "state": "AUTHORISATION_MISSING_OR_OUT_OF_SCOPE",
                    }
                )
                blocked = True
                continue
            valid = all(auth[f] == entry[f] for f in ("project", "account", "currency"))
            valid = (
                valid
                and auth["beneficiary"] == entry["counterparty"]
                and (auth["valid_from"] <= entry["date"] <= auth["valid_to"])
            )
            if not valid:
                rows.append(
                    {
                        "id": "authority:" + entry["id"],
                        "state": "AUTHORISATION_MISSING_OR_OUT_OF_SCOPE",
                    }
                )
                blocked = True
            else:
                used[auth["id"]] += abs(money(entry))
    for auth_id, amount in sorted(used.items()):
        if amount > money(authorisations[auth_id], "maximum_amount") + data.tolerance:
            rows.append(
                {
                    "id": "limit:" + auth_id,
                    "used": str(amount),
                    "state": "AUTHORISATION_LIMIT_EXCEEDED",
                }
            )
            blocked = True
    for index, (key, group) in enumerate(sorted(groups.items()), 1):

        def matching_rows(entries):
            return [
                {**r, "counterparty": hashlib.sha256(r["counterparty"].encode()).hexdigest()}
                for r in entries
            ]

        matched = reconcile_transactions(
            matching_rows(group["books"]),
            matching_rows(group["bank"]),
            data.tolerance,
            data.date_tolerance,
            3,
        )
        ambiguous = bool(matched.get("ambiguous"))
        left_ids = {i for m in matched["matches"] for i in m["left_ids"]}
        right_ids = {i for m in matched["matches"] for i in m["right_ids"]}
        unmatched = [r["id"] for r in group["books"] if r["id"] not in left_ids] + [
            r["id"] for r in group["bank"] if r["id"] not in right_ids
        ]
        rows.append(
            {
                "id": f"escrow-bank-{index}",
                "project": key[0],
                "account": key[1],
                "currency": key[2],
                "unmatched_ids": unmatched,
                "proposed_matches": matched["matches"],
                "state": "BANK_ITEMS_UNRESOLVED" if unmatched or ambiguous else "MATCHED",
            }
        )
    return result(
        rows,
        blocked,
        [
            "Project/authority eligibility and authorisation authenticity are supplied evidence, not regulator verification",
            "Cumulative authorisation caps cover the uploaded book population; completeness of prior disbursements must be assessed",
            "Matching is transaction-level; period opening/closing bank controls remain required in the separate bank BRS workflow",
        ],
    )


def billing(data, tables):
    groups: defaultdict[tuple, defaultdict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    healthcare = data.workflow == "healthcare-billing"
    kinds = {
        "services": {"service"},
        "invoices": {"invoice"},
        "settlements": {"settlement", "refund", "commission", "denial"},
    }
    for role, entries in tables.items():
        for entry in entries:
            if entry["kind"] not in kinds[role] or date.fromisoformat(entry["date"]) > data.as_of:
                raise ValueError("Billing event type/date does not match its scoped source role")
            groups[(entry["case_id"], entry["line_reference"], entry["party"], entry["currency"])][
                role
            ].append(entry)
    rows = []
    blocked = False
    for index, (key, group) in enumerate(sorted(groups.items()), 1):
        exceptions = ["MISSING_" + r.upper() for r in kinds if not group[r]]
        for service in group["services"]:
            if healthcare and service["unit_tariff"] is None:
                exceptions.append("TARIFF_NOT_TESTABLE")
                blocked = True
            elif (
                service["unit_tariff"] is not None
                and abs(money(service) - money(service, "quantity") * money(service, "unit_tariff"))
                > data.tolerance
            ):
                exceptions.append("TARIFF_DIFFERENCE")
            if not service["approved"]:
                exceptions.append("SERVICE_APPROVAL_MISSING")
        values = {
            kind: sum(
                (money(r) for role in group.values() for r in role if r["kind"] == kind), Decimal(0)
            )
            for kind in ("service", "invoice", "settlement", "refund", "commission", "denial")
        }
        if abs(values["service"] - values["invoice"]) > data.tolerance:
            exceptions.append("BILLING_COMPLETENESS_DIFFERENCE")
        expected = values["invoice"] - values["refund"] - values["commission"]
        if abs(expected - values["settlement"]) > data.tolerance:
            exceptions.append("COLLECTION_DIFFERENCE")
        if values["denial"]:
            exceptions.append("DENIED_CLAIM_REVIEW")
        if any(
            not r["approved"]
            for role in group.values()
            for r in role
            if r["kind"] in {"refund", "commission"}
        ):
            exceptions.append("ADJUSTMENT_APPROVAL_MISSING")
        rows.append(
            {
                "id": f"billing-{index}",
                "case_id": key[0],
                "line_reference": key[1],
                "party": key[2],
                "currency": key[3],
                "values": {k: str(v) for k, v in values.items()},
                "expected_net_settlement": str(expected),
                "exceptions": sorted(set(exceptions)),
                "source_ids": {role: [r["id"] for r in group[role]] for role in kinds},
                "state": "EXCEPTIONS" if exceptions else "MATCHED",
            }
        )
    return result(
        rows,
        blocked,
        [
            "Use pseudonymous encounter/folio IDs; no diagnosis, clinical appropriateness or insurance coverage is inferred",
            "Tariffs, approvals, commissions and refunds require reviewed contracts; no live PMS/POS/payer connection is implied",
            "Settlements are net bank/merchant proceeds after separately represented refunds/commissions; denials are not automatic write-offs",
        ],
    )


def construction(data, tables):
    rows = []
    for project in tables["projects"]:
        if project["reporting_date"] != data.as_of.isoformat():
            raise ValueError("Construction project reporting date must match the audit date")
        total_cost = money(project, "actual_cost") + money(project, "cost_to_complete")
        if total_cost <= 0:
            raise ValueError("Cost-to-cost construction requires a positive estimated total cost")
        price = money(project, "contract_price") + money(project, "constrained_variations")
        progress = money(project, "actual_cost") / total_cost
        computed = revenue(
            Revenue.model_validate(
                {
                    "contract_reference": project["id"],
                    "contract_assessment": project["over_time_assessment"],
                    "reporting_date": project["reporting_date"],
                    "fixed_price": project["contract_price"],
                    "constrained_variable_consideration": project["constrained_variations"],
                    "constraint_rationale": project["variation_evidence"],
                    "billed_to_date": project["billed_to_date"],
                    "obligations": [
                        {
                            "reference": project["id"],
                            "standalone_price": price,
                            "recognition": "over_time",
                            "progress": progress,
                            "over_time_justification": project["over_time_assessment"],
                        }
                    ],
                }
            )
        )
        difference = money(project, "recorded_revenue") - computed["recognised_to_date"]
        retention = money(project, "recorded_retention") - money(project, "certified_retention")
        loss = max(Decimal(0), total_cost - price)
        exceptions = []
        if abs(difference) > data.tolerance:
            exceptions.append("REVENUE_DIFFERENCE")
        if abs(retention) > data.tolerance:
            exceptions.append("RETENTION_DIFFERENCE")
        if loss:
            exceptions.append("LOSS_MAKING_CONTRACT_REVIEW")
        rows.append(
            {
                "id": project["id"],
                "currency": project["currency"],
                "progress": str(progress),
                "expected_revenue": str(computed["recognised_to_date"]),
                "revenue_difference": str(difference),
                "contract_asset": str(computed["contract_asset"]),
                "contract_liability": str(computed["contract_liability"]),
                "retention_difference": str(retention),
                "estimated_contract_loss": str(loss),
                "exceptions": exceptions,
                "state": "EXCEPTIONS" if exceptions else "MATCHED",
            }
        )
    return {
        **result(
            rows,
            limitations=[
                "Reuses IFRS 15 single-obligation cost-to-cost calculation; over-time eligibility and constrained variations require reviewed evidence",
                "No automatic modification classification, uninstalled-material adjustment, legal retention entitlement or provision posting",
            ],
        ),
        "calculation_engine": "ifrs.revenue",
    }


SECTOR_CALCULATORS = {
    "customs-reconciliation": trade,
    "trade-document-review": trade,
    "excise-reconciliation": excise,
    "gold-reconciliation": gold,
    "escrow-disbursements": escrow,
    "hospitality-revenue": billing,
    "healthcare-billing": billing,
    "construction-contracts": construction,
}
