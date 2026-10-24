"""Independent source controls, immutable revision summaries and qualification checks."""

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, localcontext

from pydantic import Field

from app.modules.accounting.schemas import Input
from app.modules.connectors.runtime import digest
from app.modules.connectors.zoho import ConnectorError
from app.modules.ingestion.parser import money


class SourceControl(Input):
    reference: str = Field(min_length=1, max_length=500)
    rows: int = Field(ge=0)
    debit: Decimal = Field(ge=0, allow_inf_nan=False)
    credit: Decimal = Field(ge=0, allow_inf_nan=False)


def compare_control(count, debit, credit, control: SourceControl):
    return {
        "matched": (count, debit, credit) == (control.rows, control.debit, control.credit),
        "reference": control.reference,
        "observed_rows": count,
        "observed_debit": str(debit),
        "observed_credit": str(credit),
    }


def reconcile_balances(gl, opening, closing):
    """Three independent source populations; no closing/opening values are manufactured."""
    balances = {}
    with localcontext() as context:
        context.prec = 48
        moves: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
        for row in gl:
            if not row.get("opening"):
                moves[row["account_code"]][0] += money(str(row["base_debit"]))
                moves[row["account_code"]][1] += money(str(row["base_credit"]))

        def index(rows):
            result = {}
            for row in rows:
                code = str(row["account_code"])
                if code in result:
                    raise ConnectorError("Duplicate balance-control account")
                result[code] = money(str(row["balance"]))
            return result

        first, last = index(opening), index(closing)
        if not first or not last or sum(first.values()) or sum(last.values()):
            raise ConnectorError(
                "Independent opening/closing controls must be supplied and balanced"
            )
        for code in first.keys() | last.keys() | moves.keys():
            if code not in first or code not in last:
                raise ConnectorError("Independent balance-control account coverage differs")
            debit, credit = moves[code]
            difference = first[code] + debit - credit - last[code]
            balances[code] = {
                "opening": str(first[code]),
                "debit": str(debit),
                "credit": str(credit),
                "closing": str(last[code]),
                "difference": str(difference),
            }
    return {
        "matched": all(
            v["difference"] in {"0", "0.0", "0.00"} or Decimal(v["difference"]) == 0
            for v in balances.values()
        ),
        "accounts": balances,
    }


def revision_summary(previous: dict, current: dict, full_population: bool):
    added = current.keys() - previous.keys()
    changed = {key for key in current.keys() & previous.keys() if current[key] != previous[key]}
    removed = previous.keys() - current.keys() if full_population else set()
    return {
        "added": sorted(added),
        "changed": sorted(changed),
        "removed": sorted(removed),
        "deletions_testable": full_population,
        "activation": "explicit_reviewer_replacement_required",
    }


def qualify(run: dict, control: SourceControl, scenario: str):
    manifest = run.get("manifest", {})
    totals = manifest.get("functional_totals", {})
    result = compare_control(
        manifest.get("counts", {}).get("gl", 0),
        money(str(totals.get("debit", "0"))),
        money(str(totals.get("credit", "0"))),
        control,
    )
    live = manifest.get("execution_mode") == "live"
    return {
        **result,
        "scenario": scenario,
        "live_evidence": live,
        "status": "passed"
        if result["matched"] and live and run.get("status") == "completed"
        else "needs_live_evidence"
        if not live
        else "failed",
        "source_digest": digest(manifest),
        "qualified_on": datetime.now(UTC).isoformat(),
    }
