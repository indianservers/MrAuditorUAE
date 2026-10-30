"""Shared original-byte numbered withholding reader with explicit form policies."""

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from app.modules.country_workflows.india_withholding_native import CONTRACT, SOURCE

WIDTHS = {"FH": 18, "BH": 72, "CD": 30, "DD": 45}


@dataclass(frozen=True)
class NumberedPolicy:
    form: str
    profile: str
    spec_sha256: str
    file_type: str
    role: Literal["collector", "deductor"]
    scheme: Literal["TCS", "TDS"]
    tax_name: str
    charge_name: str
    layout_loader: Callable[[], tuple[Any, str]]
    party_fields: dict[str, int]
    context_fields: tuple[int, ...]
    validate_party: Callable[[list[str], Any, Any], None]
    limitations: tuple[str, ...]
    require_equal_deposit: bool = True
    additional_controls: dict[str, int] = field(default_factory=dict)


def parse_numbered(content, data, controls, policy: NumberedPolicy):
    from app.modules.country_workflows.withholding_schemas import WithholdingRecord

    form = policy.form
    if controls is None:
        raise ValueError(f"Form {form} requires independent controls and a retained crosswalk")
    selected, layout_sha256 = policy.layout_loader()
    if not content.endswith(b"\r\n") or len(content) > 10 * 1024 * 1024:
        raise ValueError(f"Form {form} requires bounded original ASCII records ending in CRLF")
    try:
        lines = content[:-2].decode("ascii").split("\r\n")
    except UnicodeDecodeError:
        raise ValueError(f"The dated Form {form} profile requires ASCII without a BOM") from None
    if len(lines) > 16000 or any(
        not line or len(line) > 8192 or any(ord(c) < 32 for c in line) for line in lines
    ):
        raise ValueError(f"Unsupported blank, oversized or control-character Form {form} record")

    def integer(value):
        if not re.fullmatch(r"[0-9]{1,9}", value):
            raise ValueError(f"Form {form} record numbers and counts require bounded integers")
        return int(value)

    def amount(value, label="amount", whole=False):
        if not re.fullmatch(r"[0-9]{1,12}\.[0-9]{2}", value):
            raise ValueError(
                f"Form {form} {label} requires an explicit nonnegative two-decimal amount"
            )
        result = Decimal(value)
        if whole and result % 1:
            raise ValueError(f"Form {form} {label} requires a whole-rupee amount written with .00")
        return result

    def calendar(value):
        if not re.fullmatch(r"[0-9]{8}", value):
            raise ValueError(f"Form {form} dates require explicit ddmmyyyy values")
        try:
            parsed = datetime.strptime(value, "%d%m%Y").date()
        except ValueError:
            raise ValueError(f"Invalid Form {form} calendar date") from None
        if parsed > controls.observed_on:
            raise ValueError(f"Form {form} source date exceeds its declared observation cutoff")
        return parsed

    records = []
    for ordinal, line in enumerate(lines, 1):
        fields = line.split("^")
        tag = fields[1] if len(fields) > 1 else ""
        if tag not in WIDTHS or len(fields) != WIDTHS[tag] or integer(fields[0]) != ordinal:
            raise ValueError(f"Form {form} exact record width, type or line sequence differs")
        if any(
            limit is not None and len(value) > limit
            for value, limit in zip(fields, selected["field_lengths"][tag], strict=True)
        ):
            raise ValueError(f"Form {form} field exceeds the adopted numbered layout width")
        records.append(fields)
    first = records[0]
    if (
        first[1] != "FH"
        or first[2] != policy.file_type
        or first[3] != "R"
        or first[7] != controls.tan
    ):
        raise ValueError(
            f"Select the matching Form {form} regular {policy.role} TAN; corrections are separate"
        )
    calendar(first[4])
    quarters = {"Q1": (4, 5, 6), "Q2": (7, 8, 9), "Q3": (10, 11, 12), "Q4": (1, 2, 3)}

    def in_quarter(day):
        return day.month in quarters[controls.quarter] and day.year == 2026 + (day.month < 4)

    batch = None
    current = None
    challans: dict[int, list[str]] = {}
    parties: dict[str, dict[str, Any]] = {}
    children: dict[int, list[str]] = {}
    for f in records[1:]:
        if f[1] == "BH":
            if (
                batch is not None
                or integer(f[2]) != 1
                or f[4] != form
                or f[12] != controls.tan
                or f[15] != "202728"
                or f[16] != controls.tax_year
                or f[17] != controls.quarter
            ):
                raise ValueError(
                    f"Form {form} requires its single matching batch, TAN, tax/assessment year and quarter"
                )
            batch = f
        elif f[1] == "CD":
            if batch is None or integer(f[2]) != 1:
                raise ValueError(f"Form {form} challan must belong to the declared preceding batch")
            current = integer(f[3])
            if current != len(challans) + 1 or current in challans or f[5] != "N":
                raise ValueError(
                    f"Form {form} nonempty observations require distinct complete non-nil challans"
                )
            if f[12] not in {"C", "B"}:
                raise ValueError(
                    f"Form {form} requires an explicit supported challan or book-adjustment mode"
                )
            if not re.fullmatch(r"[0-9]{7}", f[14]) or not re.fullmatch(r"[0-9]{1,5}", f[16]):
                raise ValueError(
                    f"Retain explicit Form {form} BSR/receipt and challan/DDO identifiers"
                )
            calendar(f[18])
            gross = amount(f[11], "challan gross", whole=True)
            if sum(amount(f[i], "challan component", whole=True) for i in (7, 8, 9, 10)) != gross:
                raise ValueError(
                    f"Form {form} challan gross differs from tax, interest, fee and other components"
                )
            if amount(f[23], "interest allocation", whole=True) != amount(f[8]) or amount(
                f[24], "other allocation", whole=True
            ) != amount(f[10]):
                raise ValueError(
                    f"Form {form} interest/other allocations differ from their recorded components"
                )
            challans[current] = f
            children[current] = []
        elif f[1] == "DD":
            if current is None or integer(f[2]) != 1 or integer(f[4]) != current:
                raise ValueError(f"Form {form} party has a different preceding challan reference")
            serial = integer(f[3])
            key = f"1/{current}/{serial}"
            if (
                not serial
                or key in parties
                or f[5] != "O"
                or (form != "143" and serial != len(parties) + 1)
            ):
                raise ValueError(
                    f"Duplicate Form {form} party identity or unsupported correction mode"
                )
            if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", f[7]) and f[7] not in {
                "PANNOTAVBL",
                "PANAPPLIED",
                "PANINVALID",
            }:
                raise ValueError(
                    f"Form {form} needs its explicit PAN or retained missing-PAN sentinel"
                )
            policy.validate_party(f, amount, calendar)
            received = calendar(f[18])
            collected = calendar(f[26]) if f[26] else None
            tax = amount(f[23], "party tax collected")
            deposit = amount(f[24], "party deposit")
            if (policy.require_equal_deposit and tax != deposit) or f[17] == "N" and deposit:
                raise ValueError(
                    f"Form {form} party collected/deposited amounts contradict each other or their deposited flag"
                )
            if not amount(f[19], "receipt/payment base") or tax and collected is None:
                raise ValueError(
                    f"Form {form} needs a positive receipt base and a collection date for positive tax"
                )
            quarter_start = {
                "Q1": date(2026, 4, 1),
                "Q2": date(2026, 7, 1),
                "Q3": date(2026, 10, 1),
                "Q4": date(2027, 1, 1),
            }[controls.quarter]
            if not in_quarter(received) or collected is not None and collected < quarter_start:
                raise ValueError(
                    f"Form {form} receipt/collection dates lie outside the declared tax quarter"
                )
            if collected is not None and collected > date(2027, 3, 31):
                raise ValueError(
                    "A tax date after the adopted tax year requires a separate assessed year mapping"
                )
            if not re.fullmatch(r"[0-9]{1,3}\.[0-9]{4}", f[27]) or not tax and f[27] != "0.0000":
                raise ValueError(
                    f"Form {form} recorded rate requires four decimals and zero rate for zero tax"
                )
            parties[key] = {"fields": f, "period": (collected or received).strftime("%Y-%m")}
            children[current].append(key)
        else:
            raise ValueError(
                f"Only initial FH then complete Form {form} BH/CD/DD populations are supported"
            )
    if (
        batch is None
        or integer(first[8]) != 1
        or len(challans) != controls.challan_count
        or len(parties) != controls.party_count
        or integer(batch[3]) != len(challans)
    ):
        raise ValueError(
            f"Form {form} header/challan/party counts differ from independent controls"
        )
    if amount(batch[46], "batch gross", whole=True) != sum(
        amount(f[11]) for f in challans.values()
    ):
        raise ValueError(f"Form {form} batch gross differs from its complete challan population")
    for number, f in challans.items():
        members = [parties[k]["fields"] for k in children[number]]
        if (
            not members
            or len(members) != integer(f[4])
            or amount(f[20]) != sum(amount(v[24]) for v in members)
            or amount(f[21]) != sum(amount(v[23]) for v in members)
        ):
            raise ValueError(f"Form {form} challan counts or party tax/deposit allocations differ")
        minimum = (
            amount(f[20]) + amount(f[23]) + amount(f[24]) + (amount(f[9]) if f[12] == "C" else 0)
        )
        if amount(f[11]) < minimum:
            raise ValueError(
                f"Form {form} gross cannot fund the claimed party allocation and applicable recorded charges"
            )
    totals = {
        policy.tax_name: sum(amount(v["fields"][23]) for v in parties.values()),
        "allocated_deposit": sum(amount(v["fields"][24]) for v in parties.values()),
        "payment_base": sum(amount(v["fields"][19]) for v in parties.values()),
        "challan_deposit": sum(amount(f[11]) for f in challans.values()),
        **{
            name: sum(amount(f[index]) for f in challans.values())
            for name, index in {
                "challan_tax": 7,
                "challan_interest": 8,
                "challan_fee": 9,
                ("challan_" + policy.charge_name): 10,
                "allocated_interest": 23,
                ("allocated_" + policy.charge_name): 24,
            }.items()
        },
    }
    totals.update(
        {
            name: sum(
                amount(v["fields"][index]) if v["fields"][index] else Decimal(0)
                for v in parties.values()
            )
            for name, index in policy.additional_controls.items()
        }
    )
    if any(getattr(controls, name) != value for name, value in totals.items()):
        raise ValueError(
            f"Form {form} independent tax, receipt, component or allocation totals differ"
        )
    if {k for group in controls.groups for k in group.party_records} != set(parties):
        raise ValueError(
            f"Retained Form {form} crosswalk omits or changes original party identities"
        )
    digest = hashlib.sha256(content).hexdigest()
    rows, links = [], []
    for ordinal, group in enumerate(controls.groups, 1):
        members = [parties[k] for k in group.party_records]
        if (
            len(
                {
                    (
                        v["fields"][7],
                        v["fields"][14],
                        v["period"],
                        *(v["fields"][i] for i in policy.context_fields),
                    )
                    for v in members
                }
            )
            != 1
            or group.period != members[0]["period"]
        ):
            raise ValueError(
                f"Form {form} crosswalk cannot merge distinct PAN, code, month or recorded tax contexts"
            )
        if len(members) > 1 and members[0]["fields"][7] in {
            "PANNOTAVBL",
            "PANAPPLIED",
            "PANINVALID",
        }:
            raise ValueError(f"Missing-PAN Form {form} parties require separate crosswalk groups")
        row = WithholdingRecord(
            id=f"{form}:group:{ordinal}",
            registration=controls.tan,
            counterparty=members[0]["fields"][7],
            legal_role=policy.role,
            tax_kind=policy.scheme,
            rule_reference=group.rule_reference,
            tax_year_start=date(2026, 4, 1),
            tax_year_end=date(2027, 3, 31),
            period=group.period,
            transaction_reference=group.transaction_reference,
            transaction_date=group.transaction_date,
            currency="INR",
            amount=sum(amount(v["fields"][23]) for v in members),
            record_status=controls.record_status,
            source_reference=f"PROTEAN:{form}:group:{ordinal}",
            source_version="uploaded-sha256:" + digest,
        ).model_dump(mode="json")
        rows.append(
            {
                **row,
                "native_party_count": len(members),
                "native_section_code": members[0]["fields"][14],
            }
        )
        for key in group.party_records:
            v = parties[key]
            f = v["fields"]
            links.append(
                {
                    "group_id": row["id"],
                    "party_key": key,
                    "source_line": integer(f[0]),
                    "name": f[8],
                    "pan": f[7],
                    "native_section_code": f[14],
                    "native_payment_date": calendar(f[18]).isoformat(),
                    "native_tax_date": calendar(f[26]).isoformat() if f[26] else None,
                    "total_tax": str(amount(f[23])),
                    "allocated_deposit": str(amount(f[24])),
                    "payment_base": str(amount(f[19])),
                    "recorded_rate": f[27],
                    "reason_flag": f[31],
                    "certificate_reference": f[32],
                    **{name: f[position - 1] for name, position in policy.party_fields.items()},
                    **({"numbered_form": form} if form != "143" else {}),
                }
            )
    if len(rows) != data.expected_rows:
        raise ValueError(f"Independent Form {form} mapped observation count differs")
    return rows, {
        "contract": CONTRACT,
        "parser_contract": f"dated-form{form}-numbered-layout/1",
        "form": form,
        "source": SOURCE,
        "source_sha256": digest,
        "layout_limits_sha256": layout_sha256,
        "layout_specification_sha256": policy.spec_sha256,
        "adopted_layout": policy.profile,
        "workbook_version": "1.1",
        "page_version_at_assessment": "1.2",
        "layout_conflict": "Page version 1.2 differs from retained numbered workbook 1.1; not qualified as the complete current issuer layout",
        "tax_year": controls.tax_year,
        "assessment_year": "202728",
        "quarter": controls.quarter,
        "tan": controls.tan,
        "batch_count": 1,
        "challan_count": len(challans),
        "party_count": len(parties),
        "mapped_observations": len(rows),
        "controls": controls.model_dump(mode="json"),
        "component_controls": {k: str(v) for k, v in totals.items()},
        "party_links": links,
        "challan_controls": [
            {
                "batch": 1,
                "challan": number,
                "source_line": integer(f[0]),
                "challan_number": f[16] if f[12] == "C" else "",
                "ddo_serial": f[16] if f[12] == "B" else "",
                "bsr_or_form24g_reference": f[14],
                "challan_date": calendar(f[18]).isoformat(),
                "nil_flag": f[5],
                "recorded_payment_mode": f[12],
                "recorded_tax": str(amount(f[7])),
                "gross_deposit": str(amount(f[11])),
                "allocated_deposit": str(amount(f[20])),
                "recorded_interest": str(amount(f[8])),
                ("recorded_" + policy.charge_name): str(amount(f[10])),
                "fee": str(amount(f[9])),
                "allocated_interest": str(amount(f[23])),
                ("allocated_" + policy.charge_name): str(amount(f[24])),
            }
            for number, f in challans.items()
        ],
        "filing_or_acknowledgment": "NOT_EVIDENCED",
        "bank_payment_or_tax_credit": "NOT_EVIDENCED",
        "fvu_validation": "NOT_PERFORMED",
        "all_original_fields": "RETAINED_IN_HASH_VERIFIED_ORIGINAL_FILE",
        "limitations": list(policy.limitations),
    }
