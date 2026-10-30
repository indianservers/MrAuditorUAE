"""Dated numbered Form 143 observations; never government-file or legal qualification."""

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.modules.country_workflows.india_withholding_native import (
    CONTRACT,
    SOURCE,
    Money,
    NativeWithholdingGroup,
)
from app.modules.jurisdictions.profiles import Strict

PROFILE = "india-form143-regular-20260722-v1.1"
SPEC_SHA256 = "c487ddd78125433aefc4063ccb93ebe820156c42e1d2a58986ae110c50fc51a7"
WIDTHS = {"FH": 18, "BH": 72, "CD": 30, "DD": 45}
PARTY_FIELDS = {
    "recorded_nonresident_flag": 11,
    "recorded_collectee_code": 12,
    "recorded_pe_flag": 13,
    "recorded_section202_opt_out": 14,
    "recorded_deposited_flag": 18,
    "recorded_tds_applicability": 34,
    "recorded_tds_challan_number": 35,
    "recorded_tds_payment_date": 36,
}
CHALLAN_EXTRA_FIELDS = [
    "recorded_payment_mode",
    "recorded_tax",
    "allocated_interest",
    "allocated_other",
]


@lru_cache(maxsize=1)
def layout():
    raw = Path(__file__).with_name("india_form143_layout.json").read_bytes()
    result = json.loads(raw)
    if result["profile"] != PROFILE or result["source_sha256"] != SPEC_SHA256:
        raise ValueError("The adopted dated Form 143 layout differs from its pinned source")
    return result, hashlib.sha256(raw).hexdigest()


class Form143Controls(Strict):
    tax_year: Literal["202627"]
    tan: str = Field(pattern=r"^[A-Z]{4}[0-9]{5}[A-Z]$")
    quarter: Literal["Q1", "Q2", "Q3", "Q4"]
    observed_on: date
    batch_count: Literal[1]
    challan_count: int = Field(ge=1, le=5000, strict=True)
    party_count: int = Field(ge=1, le=5000, strict=True)
    tax_collected: Money
    allocated_deposit: Money
    challan_deposit: Money
    payment_base: Money
    challan_tax: Money
    challan_interest: Money
    challan_fee: Money
    challan_other: Money
    allocated_interest: Money
    allocated_other: Money
    record_status: Literal["current", "superseded", "cancelled"]
    crosswalk_document_version_id: UUID
    assessment: str = Field(min_length=10, max_length=2000)
    groups: list[NativeWithholdingGroup] = Field(min_length=1, max_length=5000)

    @model_validator(mode="before")
    @classmethod
    def exact_batch(cls, value):
        if isinstance(value, dict) and type(value.get("batch_count")) is not int:
            raise ValueError("The dated Form 143 profile requires one explicit integer batch")
        return value

    @model_validator(mode="after")
    def population(self):
        keys = [key for group in self.groups for key in group.party_records]
        if len(keys) != self.party_count or len(set(keys)) != len(keys):
            raise ValueError("Cover every Form 143 party once in the retained crosswalk")
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess the dated layout, source selection and independent controls")
        return self


def parse_form143(content, data):
    from app.modules.country_workflows.withholding_schemas import WithholdingRecord

    controls = data.form143_controls
    if controls is None:
        raise ValueError("Form 143 requires its own independent controls and retained crosswalk")
    selected, layout_sha256 = layout()
    if not content.endswith(b"\r\n") or len(content) > 10 * 1024 * 1024:
        raise ValueError("Form 143 requires bounded original ASCII records ending in CRLF")
    try:
        lines = content[:-2].decode("ascii").split("\r\n")
    except UnicodeDecodeError:
        raise ValueError("The dated Form 143 profile requires ASCII without a BOM") from None
    if len(lines) > 16000 or any(
        not line or len(line) > 8192 or any(ord(c) < 32 for c in line) for line in lines
    ):
        raise ValueError("Unsupported blank, oversized or control-character Form 143 record")

    def integer(value):
        if not re.fullmatch(r"[0-9]{1,9}", value):
            raise ValueError("Form 143 record numbers and counts require bounded integers")
        return int(value)

    def amount(value, label="amount", whole=False):
        if not re.fullmatch(r"[0-9]{1,12}\.[0-9]{2}", value):
            raise ValueError(
                f"Form 143 {label} requires an explicit nonnegative two-decimal amount"
            )
        result = Decimal(value)
        if whole and result % 1:
            raise ValueError(f"Form 143 {label} requires a whole-rupee amount written with .00")
        return result

    def calendar(value):
        if not re.fullmatch(r"[0-9]{8}", value):
            raise ValueError("Form 143 dates require explicit ddmmyyyy values")
        try:
            parsed = datetime.strptime(value, "%d%m%Y").date()
        except ValueError:
            raise ValueError("Invalid Form 143 calendar date") from None
        if parsed > controls.observed_on:
            raise ValueError("Form 143 source date exceeds its declared observation cutoff")
        return parsed

    records = []
    for ordinal, line in enumerate(lines, 1):
        fields = line.split("^")
        tag = fields[1] if len(fields) > 1 else ""
        if tag not in WIDTHS or len(fields) != WIDTHS[tag] or integer(fields[0]) != ordinal:
            raise ValueError("Form 143 exact record width, type or line sequence differs")
        if any(
            limit is not None and len(value) > limit
            for value, limit in zip(fields, selected["field_lengths"][tag], strict=True)
        ):
            raise ValueError("Form 143 field exceeds the adopted numbered layout width")
        records.append(fields)
    first = records[0]
    if first[1] != "FH" or first[2] != "TC1" or first[3] != "R" or first[7] != controls.tan:
        raise ValueError(
            "Select the matching Form 143 regular collector TAN; corrections are separate"
        )
    calendar(first[4])
    quarters = {"Q1": (4, 5, 6), "Q2": (7, 8, 9), "Q3": (10, 11, 12), "Q4": (1, 2, 3)}

    def in_quarter(day):
        return day.month in quarters[controls.quarter] and day.year == 2026 + (day.month < 4)

    batch = None
    current = None
    challans: dict[int, list[str]] = {}
    parties = {}
    children: dict[int, list[str]] = {}
    for f in records[1:]:
        if f[1] == "BH":
            if (
                batch is not None
                or integer(f[2]) != 1
                or f[4] != "143"
                or f[12] != controls.tan
                or f[15] != "202728"
                or f[16] != controls.tax_year
                or f[17] != controls.quarter
            ):
                raise ValueError(
                    "Form 143 requires its single matching batch, TAN, tax/assessment year and quarter"
                )
            batch = f
        elif f[1] == "CD":
            if batch is None or integer(f[2]) != 1:
                raise ValueError("Form 143 challan must belong to the declared preceding batch")
            current = integer(f[3])
            if current != len(challans) + 1 or current in challans or f[5] != "N":
                raise ValueError(
                    "Form 143 nonempty observations require distinct complete non-nil challans"
                )
            if f[12] not in {"C", "B"}:
                raise ValueError(
                    "Form 143 requires an explicit supported challan or book-adjustment mode"
                )
            if not re.fullmatch(r"[0-9]{7}", f[14]) or not re.fullmatch(r"[0-9]{1,5}", f[16]):
                raise ValueError("Retain explicit Form 143 BSR/receipt and challan/DDO identifiers")
            calendar(f[18])
            gross = amount(f[11], "challan gross", whole=True)
            if sum(amount(f[i], "challan component", whole=True) for i in (7, 8, 9, 10)) != gross:
                raise ValueError(
                    "Form 143 challan gross differs from tax, interest, fee and other components"
                )
            if amount(f[23], "interest allocation", whole=True) != amount(f[8]) or amount(
                f[24], "other allocation", whole=True
            ) != amount(f[10]):
                raise ValueError(
                    "Form 143 interest/other allocations differ from their recorded components"
                )
            challans[current] = f
            children[current] = []
        elif f[1] == "DD":
            if current is None or integer(f[2]) != 1 or integer(f[4]) != current:
                raise ValueError("Form 143 party has a different preceding challan reference")
            serial = integer(f[3])
            key = f"1/{current}/{serial}"
            if not serial or key in parties or f[5] != "O":
                raise ValueError("Duplicate Form 143 party identity or unsupported correction mode")
            if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", f[7]) and f[7] not in {
                "PANNOTAVBL",
                "PANAPPLIED",
                "PANINVALID",
            }:
                raise ValueError("Form 143 needs its explicit PAN or retained missing-PAN sentinel")
            if f[10] not in {"Y", "N"} or f[13] not in {"Y", "N"} or f[17] not in {"Y", "N"}:
                raise ValueError(
                    "Form 143 residency, section-202 opt-out and deposited flags must explicitly be Y/N"
                )
            if (f[10] == "Y" and f[12] not in {"Y", "N"}) or (f[10] == "N" and f[12]):
                raise ValueError("Form 143 PE flag must agree with its explicit residency flag")
            if not re.fullmatch(r"[0-9]{1,2}", f[11]) or not re.fullmatch(r"[0-9]{4}", f[14]):
                raise ValueError("Retain explicit Form 143 collectee and collection codes")
            received = calendar(f[18])
            collected = calendar(f[26]) if f[26] else None
            tax = amount(f[23], "party tax collected")
            deposit = amount(f[24], "party deposit")
            if tax != deposit or f[17] == "N" and deposit:
                raise ValueError(
                    "Form 143 party collected/deposited amounts contradict each other or their deposited flag"
                )
            if not amount(f[19], "receipt/payment base") or tax and collected is None:
                raise ValueError(
                    "Form 143 needs a positive receipt base and a collection date for positive tax"
                )
            if not in_quarter(received) or collected is not None and not in_quarter(collected):
                raise ValueError(
                    "Form 143 receipt/collection dates lie outside the declared tax quarter"
                )
            if not re.fullmatch(r"[0-9]{1,3}\.[0-9]{4}", f[27]) or not tax and f[27] != "0.0000":
                raise ValueError(
                    "Form 143 recorded rate requires four decimals and zero rate for zero tax"
                )
            if f[33] and f[33] not in {"Y", "N"}:
                raise ValueError(
                    "Form 143 recorded TDS applicability must be explicit Y/N if present"
                )
            if f[35]:
                calendar(f[35])
            parties[key] = {"fields": f, "period": (collected or received).strftime("%Y-%m")}
            children[current].append(key)
        else:
            raise ValueError(
                "Only initial FH then complete Form 143 BH/CD/DD populations are supported"
            )
    if (
        batch is None
        or integer(first[8]) != 1
        or len(challans) != controls.challan_count
        or len(parties) != controls.party_count
        or integer(batch[3]) != len(challans)
    ):
        raise ValueError("Form 143 header/challan/party counts differ from independent controls")
    if amount(batch[46], "batch gross", whole=True) != sum(
        amount(f[11]) for f in challans.values()
    ):
        raise ValueError("Form 143 batch gross differs from its complete challan population")
    for number, f in challans.items():
        members = [parties[k]["fields"] for k in children[number]]
        if (
            not members
            or len(members) != integer(f[4])
            or amount(f[20]) != sum(amount(v[24]) for v in members)
            or amount(f[21]) != sum(amount(v[23]) for v in members)
        ):
            raise ValueError("Form 143 challan counts or party tax/deposit allocations differ")
        minimum = (
            amount(f[20]) + amount(f[23]) + amount(f[24]) + (amount(f[9]) if f[12] == "C" else 0)
        )
        if amount(f[11]) < minimum:
            raise ValueError(
                "Form 143 gross cannot fund the claimed party allocation and applicable recorded charges"
            )
    totals = {
        "tax_collected": sum(amount(v["fields"][23]) for v in parties.values()),
        "allocated_deposit": sum(amount(v["fields"][24]) for v in parties.values()),
        "payment_base": sum(amount(v["fields"][19]) for v in parties.values()),
        "challan_deposit": sum(amount(f[11]) for f in challans.values()),
        **{
            name: sum(amount(f[index]) for f in challans.values())
            for name, index in {
                "challan_tax": 7,
                "challan_interest": 8,
                "challan_fee": 9,
                "challan_other": 10,
                "allocated_interest": 23,
                "allocated_other": 24,
            }.items()
        },
    }
    if any(getattr(controls, name) != value for name, value in totals.items()):
        raise ValueError("Form 143 independent tax, receipt, component or allocation totals differ")
    if {k for group in controls.groups for k in group.party_records} != set(parties):
        raise ValueError("Retained Form 143 crosswalk omits or changes original party identities")
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
                        *(v["fields"][i] for i in (10, 12, 13, 27, 31, 32)),
                    )
                    for v in members
                }
            )
            != 1
            or group.period != members[0]["period"]
        ):
            raise ValueError(
                "Form 143 crosswalk cannot merge distinct PAN, code, month or recorded tax contexts"
            )
        if len(members) > 1 and members[0]["fields"][7] in {
            "PANNOTAVBL",
            "PANAPPLIED",
            "PANINVALID",
        }:
            raise ValueError("Missing-PAN Form 143 parties require separate crosswalk groups")
        row = WithholdingRecord(
            id=f"143:group:{ordinal}",
            registration=controls.tan,
            counterparty=members[0]["fields"][7],
            legal_role="collector",
            tax_kind="TCS",
            rule_reference=group.rule_reference,
            tax_year_start=date(2026, 4, 1),
            tax_year_end=date(2027, 3, 31),
            period=group.period,
            transaction_reference=group.transaction_reference,
            transaction_date=group.transaction_date,
            currency="INR",
            amount=sum(amount(v["fields"][23]) for v in members),
            record_status=controls.record_status,
            source_reference=f"PROTEAN:143:group:{ordinal}",
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
                    **{name: f[position - 1] for name, position in PARTY_FIELDS.items()},
                }
            )
    if len(rows) != data.expected_rows:
        raise ValueError("Independent Form 143 mapped observation count differs")
    return rows, {
        "contract": CONTRACT,
        "parser_contract": "dated-form143-numbered-layout/1",
        "form": "143",
        "source": SOURCE,
        "source_sha256": digest,
        "layout_limits_sha256": layout_sha256,
        "layout_specification_sha256": SPEC_SHA256,
        "adopted_layout": PROFILE,
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
                "recorded_other": str(amount(f[10])),
                "fee": str(amount(f[9])),
                "allocated_interest": str(amount(f[23])),
                "allocated_other": str(amount(f[24])),
            }
            for number, f in challans.items()
        ],
        "filing_or_acknowledgment": "NOT_EVIDENCED",
        "bank_payment_or_tax_credit": "NOT_EVIDENCED",
        "fvu_validation": "NOT_PERFORMED",
        "all_original_fields": "RETAINED_IN_HASH_VERIFIED_ORIGINAL_FILE",
        "limitations": [
            "Dated numbered workbook 1.1 only; page 1.2 discrepancy and incomplete original sample remain explicit, not silently repaired",
            "Original sample missing required source fields is rejected; synthetic completions are separately labelled, never substituted for original evidence",
            "No complete FVU/CSI or conditional-code, certificate, residency, PE, legal-rate, portal-currentness or filing qualification",
            "Recorded deposited flag and allocated amount are prepared-statement claims, not bank execution or tax credit",
        ],
    }
