"""Declaration-level comparison of assessed import VAT, without a legal rate engine."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, TypedDict

from app.modules.country_workflows.audit_calculations import result

ROLES = ("customs", "portal", "books")


class PopulationTotal(TypedDict):
    net: Decimal
    tax: Decimal
    count: int


def import_vat(data, tables):
    if data.currency != "AED":
        raise ValueError("UAE import VAT comparison requires AED")
    groups: defaultdict[tuple[str, ...], defaultdict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    scopes = set()
    for role in ROLES:
        for row in tables[role]:
            scope = (row["registration"], row["period_start"], row["period_end"])
            scopes.add(scope)
            if date.fromisoformat(row["date"]) > data.as_of:
                raise ValueError("Import detail date is after the reconciliation date")
            if date.fromisoformat(row["period_end"]) > data.as_of:
                raise ValueError("Import VAT period closes after the reconciliation date")
            key = scope + tuple(
                row[field]
                for field in (
                    "customs_registration",
                    "authority",
                    "declaration",
                    "line_reference",
                    "entry_kind",
                    "adjustment_reference",
                )
            )
            groups[key][role].append(row)
    if len(scopes) != 1:
        raise ValueError("Select one VAT registration and assessed return period per import review")
    rows, blocked = [], False
    totals: dict[str, dict[str, PopulationTotal]] = {
        role: {
            kind: {"net": Decimal(0), "tax": Decimal(0), "count": 0}
            for kind in ("declaration", "adjustment")
        }
        for role in ROLES
    }
    complete = {role: True for role in ROLES}
    for index, (key, population) in enumerate(sorted(groups.items()), 1):
        selected, issues, versions = {}, [], {}
        for role in ROLES:
            observed = population[role]
            versions[role] = [
                {
                    field: row[field]
                    for field in (
                        "id",
                        "record_version",
                        "version_status",
                        "net",
                        "tax",
                        "date",
                        "evidence_reference",
                        "assessment",
                    )
                }
                for row in observed
            ]
            current = [row for row in observed if row["version_status"] == "current"]
            if not observed:
                issues.append(f"MISSING_{role.upper()}")
                complete[role] = False
            elif len(current) != 1:
                issues.append(f"{role.upper()}_CURRENT_VERSION_UNRESOLVED")
                complete[role] = False
                blocked = True
            else:
                selected[role] = current[0]
                if not current[0]["period_start"] <= current[0]["date"] <= current[0]["period_end"]:
                    issues.append(f"{role.upper()}_DATE_OUTSIDE_ASSESSED_PERIOD")
                total = totals[role][key[7]]
                total["count"] += 1
                for field in ("net", "tax"):
                    total[field] += Decimal(current[0][field])
        differences = {}
        for role in ("portal", "books"):
            if (
                role in selected
                and "customs" in selected
                and selected[role]["date"] != selected["customs"]["date"]
            ):
                issues.append(f"{role.upper()}_DATE_DIFFERENCE")
            differences[role] = {
                field: str(Decimal(selected[role][field]) - Decimal(selected["customs"][field]))
                if role in selected and "customs" in selected
                else None
                for field in ("net", "tax")
            }
            if any(
                value is not None and abs(Decimal(value)) > data.tolerance
                for value in differences[role].values()
            ):
                issues.append(f"{role.upper()}_VALUE_DIFFERENCE")
        rows.append(
            {
                "id": f"import-vat-{index}",
                "registration": key[0],
                "period_start": key[1],
                "period_end": key[2],
                "customs_registration": key[3],
                "authority": key[4],
                "declaration": key[5],
                "line_reference": key[6],
                "entry_kind": key[7],
                "adjustment_reference": key[8],
                "currency": "AED",
                "vat201_box": "6" if key[7] == "declaration" else "7",
                "selected_source_ids": {
                    role: selected[role]["id"] if role in selected else None for role in ROLES
                },
                "amounts": {
                    role: {field: selected[role][field] for field in ("net", "tax")}
                    if role in selected
                    else None
                    for role in ROLES
                },
                "source_versions": versions,
                "differences": differences,
                "exceptions": issues,
                "state": "EXCEPTIONS" if issues else "MATCHED",
            }
        )
    return {
        **result(
            rows,
            blocked,
            [
                "Assessed customs, portal and book values are compared; rates, customs valuation and legal VAT treatment are not calculated",
                "Box 6 declarations and Box 7 corrections remain separate; adjustments are not automatically proposed, filed or posted",
                "TRN/customs registration linkage, agent responsibility, recoverability and source authenticity require separate professional evidence",
                "Superseded and cancelled observations remain visible and never silently become zero or add to current balances",
            ],
        ),
        "import_comparison_contract": "uae-import-vat/1",
        "vat201_scope": "ASSESSED_IMPORT_DETAIL_ONLY_NOT_RETURN_OR_RECOVERY_APPROVAL",
        "role_totals": {
            role: {
                kind: {
                    "net": str(total["net"]) if total["count"] and complete[role] else None,
                    "tax": str(total["tax"]) if total["count"] and complete[role] else None,
                    "selected_rows": total["count"],
                    "complete_for_selected_population": complete[role],
                }
                for kind, total in kinds.items()
            }
            for role, kinds in totals.items()
        },
    }
