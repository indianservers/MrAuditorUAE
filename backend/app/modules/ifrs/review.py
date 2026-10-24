"""Deterministic review of structured statement runs; never infers PDF contents."""

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal, localcontext

ZERO = Decimal(0)
CREDIT_SECTIONS = {"liabilities", "equity", "income", "oci"}
SECTIONS = ("assets", "liabilities", "equity", "income", "expenses", "oci")


def presented(value, section, precision):
    with localcontext() as ctx:
        ctx.prec = 48
        amount = Decimal(str(value)) * (-1 if section in CREDIT_SECTIONS else 1)
        result = amount.quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP)
        return str(abs(result) if result == 0 else result)


def presentation_lines(data):
    """One presentation policy shared by preview, review and exports."""
    precision = data.get("precision", 2)
    suppress = data.get("presentation_settings", {}).get("suppress_zero", False)
    result = []
    source = list(data.get("lines", []))
    if "presentation_settings" in data:
        for key, sections, label in (
            ("__period_profit__", {"income", "expenses"}, "Current period profit / loss"),
            ("__period_oci__", {"oci"}, "Current period other comprehensive income"),
        ):
            values = {
                column: sum(
                    (
                        Decimal(str(line.get(column, 0)))
                        for line in data.get("lines", [])
                        if line["section"] in sections
                    ),
                    ZERO,
                )
                for column in ("current", "comparative")
            }
            source.append(
                {
                    "line_code": key,
                    "label": label,
                    "section": "equity",
                    "note": "",
                    "source_accounts": [],
                    "derived": True,
                    **values,
                }
            )
    for line in source:
        current = presented(line["current"], line["section"], precision)
        comparative = (
            presented(line.get("comparative", 0), line["section"], precision)
            if data.get("comparative")
            else None
        )
        if (
            suppress
            and Decimal(current) == 0
            and (comparative is None or Decimal(comparative) == 0)
        ):
            continue
        result.append({**line, "display_current": current, "display_comparative": comparative})
    return result


def review_statements(data, previous=None):
    with localcontext() as ctx:
        ctx.prec = 48
        return _review(data, previous)


def _review(data, previous):
    lines = data.get("lines", [])
    notes = data.get("notes", [])
    issues = []
    issue_keys = set()

    def issue(code, location, message, severity="error", **evidence):
        key = f"{code}:{location}"
        if key in issue_keys:
            return
        issue_keys.add(key)
        issues.append(
            {
                "key": key,
                "code": code,
                "location": location,
                "message": message,
                "severity": severity,
                "evidence": evidence,
            }
        )

    refs = Counter(n["reference"] for n in notes)
    codes = Counter(line["line_code"] for line in lines)
    for ref in sorted(refs):
        if refs[ref] > 1:
            issue("duplicate_note_reference", ref, "Note reference must be unique.")
    for code in sorted(codes):
        if codes[code] > 1:
            issue("duplicate_statement_line", code, "Statement line code must be unique.")
    by_code = {line["line_code"]: line for line in lines}

    def total(section, column="current"):
        return sum(
            (Decimal(str(line.get(column, 0))) for line in lines if line["section"] == section),
            ZERO,
        )

    expected = {
        "assets": total("assets"),
        "liabilities": -total("liabilities"),
        "profit": -total("income") - total("expenses"),
        "oci": -total("oci"),
    }
    expected["equity"] = -total("equity") + expected["profit"] + expected["oci"]
    expected["total_comprehensive_income"] = expected["profit"] + expected["oci"]
    for name, value in expected.items():
        if name not in data.get("totals", {}) or Decimal(str(data["totals"][name])) != value:
            issue(
                "statement_total",
                name,
                "Statement total does not agree with mapped lines.",
                calculated=str(value),
                reported=data.get("totals", {}).get(name),
            )
    if expected["assets"] != expected["liabilities"] + expected["equity"]:
        issue("accounting_equation", "current", "Assets do not equal liabilities and equity.")
    if (
        data.get("comparative")
        and sum((total(section, "comparative") for section in SECTIONS), ZERO) != 0
    ):
        issue("accounting_equation", "comparative", "Comparative statements do not balance.")
    for line in lines:
        if (Decimal(str(line["current"])) or Decimal(str(line.get("comparative", 0)))) and line.get(
            "note"
        ) not in refs:
            issue(
                "missing_note",
                line["line_code"],
                "Statement note reference has no approved note.",
                reference=line.get("note"),
            )
    for note in notes:
        linked = {line["code"]: line for line in note.get("lines", [])}
        for code, value in linked.items():
            source = by_code.get(code)
            if source is None:
                issue(
                    "unknown_note_line",
                    f"{note['reference']}/{code}",
                    "Note links to an unknown statement line.",
                )
            elif any(
                Decimal(str(value.get(col, 0))) != Decimal(str(source.get(col, 0)))
                for col in ("current", "comparative")
            ):
                issue(
                    "note_tie",
                    f"{note['reference']}/{code}",
                    "Note values do not agree with the statement.",
                )
        for line in lines:
            if (
                line.get("note") == note["reference"]
                and (Decimal(str(line["current"])) or Decimal(str(line.get("comparative", 0))))
                and line["line_code"] not in linked
            ):
                issue(
                    "missing_note_link",
                    f"{note['reference']}/{line['line_code']}",
                    "Referenced note must include this statement line.",
                )
    precision = data.get("precision", 2)
    casting = []
    casting_data = {**data}
    if "presentation_settings" in data:
        casting_data["presentation_settings"] = {
            **data["presentation_settings"],
            "suppress_zero": False,
        }
    casting_lines = presentation_lines(casting_data)
    for section in SECTIONS:
        members = [line for line in casting_lines if line["section"] == section]
        if not members:
            continue
        for column in ["current", "comparative"] if data.get("comparative") else ["current"]:
            displayed = sum(
                (Decimal(presented(line.get(column, 0), section, precision)) for line in members),
                ZERO,
            )
            exact = sum((Decimal(str(line.get(column, 0))) for line in members), ZERO)
            rounded_total = Decimal(presented(exact, section, precision))
            casting.append(
                {
                    "section": section,
                    "column": column,
                    "displayed_sum": str(displayed),
                    "rounded_exact_total": str(rounded_total),
                    "rounding_difference": str(displayed - rounded_total),
                }
            )
            if displayed != rounded_total:
                issue(
                    "rounding_difference",
                    f"{section}/{column}",
                    "Displayed lines differ from the rounded exact subtotal; review presentation rounding.",
                    "warning",
                    difference=str(displayed - rounded_total),
                )
    for check in data.get("validation", {}).get("checks", []):
        if not check["passed"]:
            issue("validation", check["code"], "Existing financial validation failed.", check=check)
    changes = []
    if previous is not None:
        for field in (
            "totals",
            "cash_flow",
            "changes_in_equity",
            "presentation_settings",
            "presentation",
            "comparative",
        ):
            if data.get(field) != previous.get(field):
                changes.append(
                    {
                        "field": field,
                        "change": "package_changed",
                        "previous": previous.get(field),
                        "current": data.get(field),
                    }
                )
        prior = {line["line_code"]: line for line in previous.get("lines", [])}
        for code in sorted(by_code.keys() | prior.keys()):
            now, old = by_code.get(code), prior.get(code)
            if now != old:
                changes.append(
                    {
                        "line_code": code,
                        "change": "added"
                        if old is None
                        else "removed"
                        if now is None
                        else "changed",
                        "previous": old,
                        "current": now,
                        "difference": str(
                            Decimal(str((now or {}).get("current", 0)))
                            - Decimal(str((old or {}).get("current", 0)))
                        ),
                    }
                )
        previous_notes = {n["reference"]: n for n in previous.get("notes", [])}
        current_notes = {n["reference"]: n for n in notes}
        for ref in sorted(previous_notes.keys() | current_notes.keys()):
            if previous_notes.get(ref) != current_notes.get(ref):
                changes.append(
                    {
                        "note_reference": ref,
                        "change": "note_changed",
                        "previous": previous_notes.get(ref),
                        "current": current_notes.get(ref),
                    }
                )
        old_keys = {i["key"] for i in review_statements(previous)["issues"]}
        for item in issues:
            item["carry_forward"] = item["key"] in old_keys
    return {
        "scope": "Structured financial statements only; external PDF/Word text is not inspected.",
        "ready": not any(i["severity"] == "error" for i in issues),
        "issues": issues,
        "casting": casting,
        "changes": changes,
        "presentation_lines": presentation_lines(data),
        "resolved_issue_keys": sorted(old_keys - {i["key"] for i in issues})
        if previous is not None
        else [],
    }
