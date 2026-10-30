"""Dated salary observations, with retained source conflicts; never FVU validation."""

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
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

PROFILE = "india-form138-regular-20260722-v1.1"
SPEC_SHA256 = "d58fd86b69932c6a7a4f518990c17d2112f55c65042d9c3bf2799ed201cbaf6c"
WIDTHS = {"FH": 18, "BH": 72, "CD": 30, "DD": 45}


class Form138Controls(Strict):
    tax_year: Literal["202627"]
    tan: str = Field(pattern=r"^[A-Z]{4}[0-9]{5}[A-Z]$")
    quarter: Literal["Q1", "Q2", "Q3"]
    observed_on: date
    date_width_assessment: Literal["DD29_EIGHT_DIGIT_DATE_PER_NUMBERED_REMARKS"]
    batch_count: Literal[1]
    challan_count: int = Field(ge=1, le=5000, strict=True)
    party_count: int = Field(ge=1, le=5000, strict=True)
    tax_deducted: Money
    allocated_deposit: Money
    challan_deposit: Money
    payment_base: Money
    challan_tax: Money
    challan_interest: Money
    challan_fee: Money
    challan_penalty: Money
    allocated_interest: Money
    allocated_penalty: Money
    record_status: Literal["current", "superseded", "cancelled"]
    crosswalk_document_version_id: UUID
    assessment: str = Field(min_length=10, max_length=2000)
    groups: list[NativeWithholdingGroup] = Field(min_length=1, max_length=5000)

    @model_validator(mode="before")
    @classmethod
    def exact_batch(cls, value):
        if isinstance(value, dict) and type(value.get("batch_count")) is not int:
            raise ValueError("Form 138 requires one explicit integer batch")
        return value

    @model_validator(mode="after")
    def population(self):
        keys = [key for group in self.groups for key in group.party_records]
        if len(keys) != self.party_count or len(set(keys)) != len(keys):
            raise ValueError("Cover every Form 138 employee record once in the crosswalk")
        if type(self.batch_count) is not int or len(self.assessment.strip()) < 10:
            raise ValueError("Assess the single Form 138 batch and dated source conflicts")
        return self


def parse_form138(content, data):
    from app.modules.country_workflows.withholding_schemas import WithholdingRecord

    controls = data.form138_controls
    if controls is None:
        raise ValueError("Form 138 requires its own independent controls and crosswalk")
    raw = Path(__file__).with_name("india_form138_layout.json").read_bytes()
    layout = json.loads(raw)
    if layout["profile"] != PROFILE or layout["source_sha256"] != SPEC_SHA256:
        raise ValueError("Form 138 adopted layout differs from its pinned source")
    if not content.endswith(b"\r\n") or len(content) > 10 * 1024 * 1024:
        raise ValueError("Form 138 requires bounded original ASCII records ending in CRLF")
    try:
        lines = content[:-2].decode("ascii").split("\r\n")
    except UnicodeDecodeError:
        raise ValueError("Form 138 requires ASCII without a BOM") from None
    if len(lines) > 16000 or any(
        not line or len(line) > 8192 or any(ord(c) < 32 for c in line) for line in lines
    ):
        raise ValueError("Unsupported blank, oversized or control-character Form 138 record")

    def integer(value):
        if not re.fullmatch(r"[0-9]{1,9}", value):
            raise ValueError("Form 138 record numbers and counts require bounded integers")
        return int(value)

    def amount(value, whole=False):
        if not re.fullmatch(r"[0-9]{1,12}\.[0-9]{2}", value):
            raise ValueError("Form 138 requires explicit nonnegative two-decimal amounts")
        result = Decimal(value)
        if whole and result % 1:
            raise ValueError("Form 138 challan components require whole rupees written with .00")
        return result

    def calendar(value):
        if not re.fullmatch(r"[0-9]{8}", value):
            raise ValueError("Form 138 dates require explicit ddmmyyyy values")
        try:
            result = datetime.strptime(value, "%d%m%Y").date()
        except ValueError:
            raise ValueError("Invalid Form 138 calendar date") from None
        if result > controls.observed_on:
            raise ValueError("Form 138 date exceeds the observation cutoff")
        return result

    def in_quarter(day):
        return (
            day.year == 2026
            and day.month
            in {"Q1": (4, 5, 6), "Q2": (7, 8, 9), "Q3": (10, 11, 12)}[controls.quarter]
        )

    records = []
    for ordinal, line in enumerate(lines, 1):
        fields = line.split("^")
        tag = fields[1] if len(fields) > 1 else ""
        if tag not in WIDTHS or len(fields) != WIDTHS[tag] or integer(fields[0]) != ordinal:
            raise ValueError("Form 138 exact width, type or line sequence differs")
        limits = list(layout["field_lengths"][tag])
        if tag == "DD":
            limits[28] = 8  # Explicitly assessed notes/size conflict; original remains unchanged.
        if any(
            limit is not None and len(v) > limit for v, limit in zip(fields, limits, strict=True)
        ):
            raise ValueError("Form 138 field exceeds the adopted dated layout width")
        records.append(fields)
    first = records[0]
    if first[1:4] != ["FH", "SL1", "R"] or first[6] != "D" or first[7] != controls.tan:
        raise ValueError("Select the matching regular Form 138 salary deductor TAN")
    calendar(first[4])
    batch = current = None
    challans: dict[int, list[str]] = {}
    parties = {}
    children: dict[int, list[str]] = {}
    for f in records[1:]:
        if f[1] == "BH":
            if (
                batch is not None
                or integer(f[2]) != 1
                or f[4] != "138"
                or f[12] != controls.tan
                or f[15] != "202728"
                or f[16] != controls.tax_year
                or f[17] != controls.quarter
            ):
                raise ValueError(
                    "Form 138 requires one matching TAN, tax/assessment year and quarter batch"
                )
            batch = f
        elif f[1] == "CD":
            if batch is None or integer(f[2]) != 1:
                raise ValueError("Form 138 challan requires its preceding batch")
            current = integer(f[3])
            if current != len(challans) + 1 or f[5] != "N" or f[12] not in {"C", "B"}:
                raise ValueError(
                    "Form 138 requires distinct complete non-nil challans and payment modes"
                )
            if not re.fullmatch(r"[0-9]{7}", f[14]) or not re.fullmatch(r"[0-9]{1,5}", f[16]):
                raise ValueError("Retain explicit Form 138 BSR/receipt and challan/DDO identifiers")
            day = calendar(f[18])
            if day < date(2025, 4, 1) or f[22] not in {"", "100", "200", "400"}:
                raise ValueError(
                    "Form 138 challan date or recorded minor head is outside this profile"
                )
            if f[22] == "100" and not in_quarter(day):
                raise ValueError("Form 138 advance-tax challan must be in the selected quarter")
            if sum(amount(f[i], True) for i in (7, 8, 9, 10)) != amount(f[11], True):
                raise ValueError(
                    "Form 138 challan gross differs from tax, interest, fee and penalty"
                )
            if amount(f[23], True) != amount(f[8]) or amount(f[24], True) != amount(f[10]):
                raise ValueError(
                    "Form 138 interest/penalty allocations differ from recorded components"
                )
            challans[current], children[current] = f, []
        elif f[1] == "DD":
            if current is None or integer(f[2]) != 1 or integer(f[4]) != current:
                raise ValueError("Form 138 employee has a different preceding challan reference")
            serial = integer(f[3])
            key = f"1/{current}/{serial}"
            if not serial or key in parties or f[5] != "O":
                raise ValueError(
                    "Duplicate Form 138 employee identity or unsupported correction mode"
                )
            if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", f[7]) and f[7] not in {
                "PANNOTAVBL",
                "PANAPPLIED",
                "PANINVALID",
            }:
                raise ValueError("Form 138 requires explicit PAN or missing-PAN sentinel")
            if f[14] not in {"1001", "1002", "1003", "1032"} or f[17] not in {"Y", "N"}:
                raise ValueError(
                    "Form 138 requires a recorded salary code and explicit deposited flag"
                )
            paid = calendar(f[18])
            tax = amount(f[23])
            deposit = amount(f[24])
            deducted = calendar(f[26]) if f[26] else None
            deposited = calendar(f[28]) if f[28] else None
            if not in_quarter(paid) or deducted is not None and not in_quarter(deducted):
                raise ValueError(
                    "Form 138 payment/deduction dates lie outside the selected tax quarter"
                )
            if not amount(f[19]) or tax != deposit or f[17] == "N" and deposit:
                raise ValueError(
                    "Form 138 payment base, tax/deposit or deposited flag contradicts observations"
                )
            if bool(tax) != bool(deducted) or bool(deposit) != bool(deposited):
                raise ValueError("Form 138 deduction/deposit dates must agree with nonzero amounts")
            if deposited is not None and deducted is not None and deposited < deducted:
                raise ValueError("Form 138 recorded deposit precedes deduction")
            if f[31] not in {"", "A", "C"} or (
                f[31] == "A" and not re.fullmatch(r"[A-Za-z0-9]{10}|[A-Za-z0-9]{15}", f[32])
            ):
                raise ValueError(
                    "Form 138 recorded reason/certificate is outside the adopted dated syntax"
                )
            parties[key] = {"fields": f, "period": (deducted or paid).strftime("%Y-%m")}
            children[current].append(key)
        else:
            raise ValueError(
                "Only initial FH then complete Form 138 BH/CD/DD records are supported"
            )
    if (
        batch is None
        or integer(first[8]) != 1
        or len(challans) != controls.challan_count
        or len(parties) != controls.party_count
        or integer(batch[3]) != len(challans)
    ):
        raise ValueError("Form 138 counts differ from independent controls")
    if amount(batch[46], True) != sum(amount(f[11]) for f in challans.values()):
        raise ValueError("Form 138 batch gross differs from the complete challan population")
    for number, f in challans.items():
        members = [parties[k]["fields"] for k in children[number]]
        if (
            not members
            or len(members) != integer(f[4])
            or amount(f[20]) != sum(amount(v[24]) for v in members)
            or amount(f[21]) != sum(amount(v[23]) for v in members)
        ):
            raise ValueError("Form 138 challan counts or employee allocations differ")
        minimum = (
            amount(f[20]) + amount(f[23]) + amount(f[24]) + (amount(f[9]) if f[12] == "C" else 0)
        )
        if amount(f[11]) < minimum:
            raise ValueError(
                "Form 138 gross cannot fund the claimed employee allocations and charges"
            )
    totals = {
        "tax_deducted": sum(amount(v["fields"][23]) for v in parties.values()),
        "allocated_deposit": sum(amount(v["fields"][24]) for v in parties.values()),
        "payment_base": sum(amount(v["fields"][19]) for v in parties.values()),
        **{
            name: sum(amount(f[index]) for f in challans.values())
            for name, index in {
                "challan_deposit": 11,
                "challan_tax": 7,
                "challan_interest": 8,
                "challan_fee": 9,
                "challan_penalty": 10,
                "allocated_interest": 23,
                "allocated_penalty": 24,
            }.items()
        },
    }
    if any(getattr(controls, name) != value for name, value in totals.items()):
        raise ValueError("Form 138 independent component, payment or allocation totals differ")
    if {k for g in controls.groups for k in g.party_records} != set(parties):
        raise ValueError("Form 138 crosswalk omits or changes original employee identities")
    digest = hashlib.sha256(content).hexdigest()
    rows, links = [], []
    for ordinal, group in enumerate(controls.groups, 1):
        members = [parties[k] for k in group.party_records]
        first_party = members[0]["fields"]
        contexts = {
            (v["fields"][7], v["fields"][14], v["period"], v["fields"][31], v["fields"][32])
            for v in members
        }
        if len(contexts) != 1 or group.period != members[0]["period"]:
            raise ValueError(
                "Form 138 crosswalk cannot merge distinct PAN, code, month or tax contexts"
            )
        if len(members) > 1 and first_party[7] in {"PANNOTAVBL", "PANAPPLIED", "PANINVALID"}:
            raise ValueError("Missing-PAN Form 138 employees require separate crosswalk groups")
        row = WithholdingRecord(
            id=f"138:group:{ordinal}",
            registration=controls.tan,
            counterparty=first_party[7],
            legal_role="deductor",
            tax_kind="TDS",
            rule_reference=group.rule_reference,
            tax_year_start=date(2026, 4, 1),
            tax_year_end=date(2027, 3, 31),
            period=group.period,
            transaction_reference=group.transaction_reference,
            transaction_date=group.transaction_date,
            currency="INR",
            amount=sum(amount(v["fields"][23]) for v in members),
            record_status=controls.record_status,
            source_reference=f"PROTEAN:138:group:{ordinal}",
            source_version="uploaded-sha256:" + digest,
        ).model_dump(mode="json")
        rows.append(
            {**row, "native_party_count": len(members), "native_section_code": first_party[14]}
        )
        for key in group.party_records:
            f = parties[key]["fields"]
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
                    "recorded_deposit_date": calendar(f[28]).isoformat() if f[28] else None,
                    "recorded_deposited_flag": f[17],
                    "total_tax": str(amount(f[23])),
                    "allocated_deposit": str(amount(f[24])),
                    "payment_base": str(amount(f[19])),
                    "reason_flag": f[31],
                    "certificate_reference": f[32],
                }
            )
    if len(rows) != data.expected_rows:
        raise ValueError("Independent Form 138 mapped observation count differs")
    return rows, {
        "contract": CONTRACT,
        "parser_contract": "dated-form138-salary-observations/1",
        "form": "138",
        "source": SOURCE,
        "source_sha256": digest,
        "layout_limits_sha256": hashlib.sha256(raw).hexdigest(),
        "layout_specification_sha256": SPEC_SHA256,
        "adopted_layout": PROFILE,
        "workbook_version": "1.1",
        "page_version_at_assessment": "1.2",
        "date_width_conflict": layout["date_width_conflict"],
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
                "challan": n,
                "source_line": integer(f[0]),
                "recorded_payment_mode": f[12],
                "challan_number": f[16] if f[12] == "C" else "",
                "ddo_serial": f[16] if f[12] == "B" else "",
                "bsr_or_form24g_reference": f[14],
                "challan_date": calendar(f[18]).isoformat(),
                "gross_deposit": str(amount(f[11])),
                "allocated_deposit": str(amount(f[20])),
                "recorded_tax": str(amount(f[7])),
                "recorded_interest": str(amount(f[8])),
                "fee": str(amount(f[9])),
                "recorded_penalty": str(amount(f[10])),
                "allocated_interest": str(amount(f[23])),
                "allocated_penalty": str(amount(f[24])),
            }
            for n, f in challans.items()
        ],
        "filing_or_acknowledgment": "NOT_EVIDENCED",
        "bank_payment_or_tax_credit": "NOT_EVIDENCED",
        "fvu_validation": "NOT_PERFORMED",
        "all_original_fields": "RETAINED_IN_HASH_VERIFIED_ORIGINAL_FILE",
        "limitations": [
            "Dated workbook v1.1 differs from page v1.2; original sample has historical years, missing fields and a conflicting date width",
            "DD29 uses eight-digit dates only under the explicit assessed numbered-remarks interpretation; not issuer/FVU qualification",
            "No Q4 annual salary annexure, historical 24Q, correction, complete payroll/tax calculation, certificate entitlement, FVU/CSI or portal qualification",
            "Recorded deductions and deposits are prepared-statement observations, not proof of payment or tax credit",
        ],
    }
