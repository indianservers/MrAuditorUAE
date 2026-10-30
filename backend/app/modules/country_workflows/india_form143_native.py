"""Dated numbered Form 143 observations; never government-file or legal qualification."""

import hashlib
import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.modules.country_workflows.india_withholding_native import (
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


def _validate_party143(f, amount, calendar):
    if f[10] not in {"Y", "N"} or f[13] not in {"Y", "N"} or f[17] not in {"Y", "N"}:
        raise ValueError(
            "Form 143 residency, section-202 opt-out and deposited flags must explicitly be Y/N"
        )
    if (f[10] == "Y" and f[12] not in {"Y", "N"}) or (f[10] == "N" and f[12]):
        raise ValueError("Form 143 PE flag must agree with its explicit residency flag")
    if not re.fullmatch(r"[0-9]{1,2}", f[11]) or not re.fullmatch(r"[0-9]{4}", f[14]):
        raise ValueError("Retain explicit Form 143 collectee and collection codes")
    if f[33] and f[33] not in {"Y", "N"}:
        raise ValueError("Form 143 recorded TDS applicability must be explicit Y/N if present")
    if f[35]:
        calendar(f[35])


def parse_form143(content, data):
    from app.modules.country_workflows.india_numbered_withholding import (
        NumberedPolicy,
        parse_numbered,
    )

    policy = NumberedPolicy(
        form="143",
        profile=PROFILE,
        spec_sha256=SPEC_SHA256,
        file_type="TC1",
        role="collector",
        scheme="TCS",
        tax_name="tax_collected",
        charge_name="other",
        layout_loader=layout,
        party_fields=PARTY_FIELDS,
        context_fields=(10, 12, 13, 27, 31, 32),
        validate_party=_validate_party143,
        limitations=tuple(
            [
                "Dated numbered workbook 1.1 only; page 1.2 discrepancy and incomplete original sample remain explicit, not silently repaired",
                "Original sample missing required source fields is rejected; synthetic completions are separately labelled, never substituted for original evidence",
                "No complete FVU/CSI or conditional-code, certificate, residency, PE, legal-rate, portal-currentness or filing qualification",
                "Recorded deposited flag and allocated amount are prepared-statement claims, not bank execution or tax credit",
            ]
        ),
    )
    return parse_numbered(content, data, data.form143_controls, policy)
