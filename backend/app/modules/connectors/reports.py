"""Provider-independent full financial report sets with source identity retained."""

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

from pydantic import Field

from app.modules.accounting.schemas import ImportOptions, Input, ScopeInput, SourceSystem
from app.modules.ingestion.parser import ImportProblem, map_headers, normalize, rows

REPORT_COLUMNS = {
    "gl": [
        "account_code",
        "account_name",
        "journal_ref",
        "posting_date",
        "debit",
        "credit",
        "currency",
        "exchange_rate",
        "base_debit",
        "base_credit",
        "source_id",
        "opening",
        "description",
        "counterparty",
        "tax_code",
        "cost_center",
        "department",
        "project",
    ],
    "tb": [
        "account_code",
        "account_name",
        "opening_balance",
        "debit",
        "credit",
        "closing_balance",
        "currency",
        "source_id",
    ],
    "coa": ["account_code", "account_name", "source_group", "parent_code", "source_id"],
}


class ReportControl(Input):
    reference: str = Field(min_length=1, max_length=500)
    expected_rows: int = Field(ge=0)
    expected_debit: Decimal = Field(ge=0, allow_inf_nan=False)
    expected_credit: Decimal = Field(ge=0, allow_inf_nan=False)


class ReportPackageOptions(ScopeInput):
    source_system: SourceSystem
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    mappings: dict[str, dict[str, str]] = Field(default_factory=dict, max_length=3)
    controls: dict[str, ReportControl] = Field(default_factory=dict, max_length=3)
    supersedes_ids: dict[str, uuid.UUID] = Field(default_factory=dict, max_length=3)
    delimiter: str = Field(default=",", pattern=r"^[,;\t]$")
    encoding: str = Field(default="utf-8-sig", pattern=r"^(utf-8-sig|cp1252|utf-16)$")
    date_format: str = Field(default="%Y-%m-%d", max_length=40)

    def import_options(self, kind: str) -> ImportOptions:
        control = self.controls.get(kind)
        return ImportOptions.model_validate(
            {
                **self.model_dump(
                    include={
                        "client_id",
                        "entity_id",
                        "period_id",
                        "source_system",
                        "currency",
                        "delimiter",
                        "encoding",
                        "date_format",
                    }
                ),
                "kind": kind,
                "mapping": self.mappings.get(kind, {}),
                "expected_rows": control.expected_rows if control else None,
                "expected_debit": control.expected_debit if control else None,
                "expected_credit": control.expected_credit if control else None,
                "source_complete": False,
                "supersedes_id": self.supersedes_ids.get(kind),
            }
        )


def inspect_report_set(
    files: dict[str, tuple[Path, str]],
    options: ReportPackageOptions,
    start: date,
    end: date,
    functional_currency: str,
) -> dict:
    """Preflight all three reports before creating any import batches.

    Requires a flat transaction-level export (no subtotal rows). Grouped source
    reports must be flattened with reviewed mappings first. Source rows remain
    untouched in the private originals.
    """
    if set(files) != set(REPORT_COLUMNS):
        raise ImportProblem("A report set requires GL, trial balance and chart of accounts")
    if any(
        set(values) - set(REPORT_COLUMNS)
        for values in (options.mappings, options.controls, options.supersedes_ids)
    ):
        raise ImportProblem("Unknown report kind in mappings or controls")
    counts, totals = {}, {}
    accounts, balances = set(), {}
    movement: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0), Decimal(0)])
    opening_accounts = set()
    journals: dict[str, Decimal] = defaultdict(Decimal)
    journal_dates: dict[str, str] = {}
    with localcontext() as context:
        context.prec = 48
        for kind in ("coa", "tb", "gl"):
            path, filename = files[kind]
            if path.stat().st_size > 64 * 1024 * 1024:
                raise ImportProblem("Each report must be at most 64 MiB")
            if Path(filename).suffix.lower() not in {".csv", ".xlsx"}:
                raise ImportProblem("Report sets accept CSV or XLSX files")
            counts[kind] = 0
            import_options = options.import_options(kind)
            debit_total = credit_total = Decimal(0)
            seen = set()
            for index, raw in rows(path, filename, import_options):
                row, _ = normalize(raw, import_options, start, end, functional_currency, index)
                identity = row["source_id"] if kind == "gl" else row["account_code"]
                if identity in seen:
                    raise ImportProblem(f"Duplicate {kind} source/account identifier")
                seen.add(identity)
                counts[kind] += 1
                code = row["account_code"]
                if kind == "coa":
                    accounts.add(code)
                    continue
                if code not in accounts:
                    raise ImportProblem("Report account is missing from chart of accounts")
                debit, credit = Decimal(row["base_debit"]), Decimal(row["base_credit"])
                debit_total += debit
                credit_total += credit
                if kind == "tb":
                    # Never use the generic normalizer's calculated balance fallback.
                    mapped = map_headers(list(raw), import_options.mapping)
                    if not all(
                        raw.get(mapped.get(key, ""), "").strip()
                        for key in ("opening_balance", "closing_balance")
                    ):
                        raise ImportProblem(
                            "TB requires explicit source opening and closing balances"
                        )
                    if row["currency"] != functional_currency:
                        raise ImportProblem("Trial balance must be in entity functional currency")
                    balances[code] = (
                        Decimal(row["opening_balance"]),
                        debit,
                        credit,
                        Decimal(row["closing_balance"]),
                    )
                else:
                    ref = row["journal_ref"]
                    if journal_dates.setdefault(ref, row["posting_date"]) != row["posting_date"]:
                        raise ImportProblem("Journal reference spans multiple dates")
                    journals[ref] += debit - credit
                    if row.get("opening"):
                        opening_accounts.add(code)
                        movement[code][2] += debit - credit
                    else:
                        movement[code][0] += debit
                        movement[code][1] += credit
            totals[kind] = {"debit": str(debit_total), "credit": str(credit_total)}
            if not counts[kind]:
                raise ImportProblem("Empty " + kind + " report")
            control = options.controls.get(kind)
            if control and (counts[kind], debit_total, credit_total) != (
                control.expected_rows,
                control.expected_debit,
                control.expected_credit,
            ):
                raise ImportProblem("Independent source controls do not match " + kind)
        if any(journals.values()):
            raise ImportProblem("General ledger contains an unbalanced journal")
        if set(movement) - balances.keys():
            raise ImportProblem("General ledger account is missing from trial balance")
        for code, (opening, debit, credit, closing) in balances.items():
            observed_debit, observed_credit, observed_opening = movement[code]
            if (observed_debit, observed_credit) != (debit, credit):
                raise ImportProblem("GL movements do not match trial balance for account " + code)
            if code in opening_accounts and observed_opening != opening:
                raise ImportProblem("GL opening does not match trial balance for account " + code)
            if opening + observed_debit - observed_credit != closing:
                raise ImportProblem("Closing balance does not reconcile for account " + code)
        if sum(v[0] for v in balances.values()) or sum(v[3] for v in balances.values()):
            raise ImportProblem("Trial balance opening/closing totals do not balance")
    hashes = {}
    for kind, (path, _) in files.items():
        with path.open("rb") as source:
            hashes[kind] = hashlib.file_digest(source, "sha256").hexdigest()
    identity = json.dumps(
        {"files": hashes, "options": options.model_dump(mode="json")}, sort_keys=True
    )
    return {
        "package_id": str(uuid.uuid5(uuid.NAMESPACE_URL, identity)),
        "status": "reports_reconciled",
        "counts": counts,
        "totals": totals,
        "accounts_reconciled": len(balances),
        "source_control_references": {kind: c.reference for kind, c in options.controls.items()},
        "completeness": "independent_source_review_required",
        "activation": "Validate and explicitly review each batch before activation",
    }
