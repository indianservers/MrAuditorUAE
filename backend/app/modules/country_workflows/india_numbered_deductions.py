"""Explicit dated Form140/144 policies for the shared original-byte reader."""

import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from functools import lru_cache, partial
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.modules.country_workflows.india_numbered_withholding import NumberedPolicy, parse_numbered
from app.modules.country_workflows.india_withholding_native import Money, NativeWithholdingGroup
from app.modules.jurisdictions.profiles import Strict

SPECS = {
    "140": "ec5d8a1138ac84fd5ed59f62aabb5b097479007d501cca98a27ba9c400a05f40",
    "144": "5e78534c065133936a4bb594f310c10a44e25a0825fe9f7ff023b342730fd5da",
}
COMMON_FIELDS = {
    "recorded_deposited_flag": 18,
    "recorded_cash_withdrawal_general": 22,
    "recorded_cash_withdrawal_cooperative": 23,
    "recorded_unique_form_reference": 31,
}
PARTY_FIELDS = {
    "140": COMMON_FIELDS,
    "144": {
        **COMMON_FIELDS,
        "recorded_nonresident_status": 12,
        "recorded_202_opt_out": 14,
        "recorded_remittance_code": 16,
        "recorded_destination_country": 17,
        "recorded_gross_up_flag": 21,
        "recorded_numbered_rate_basis": 30,
        "recorded_residence_address": 37,
        "recorded_residence_email": 38,
        "recorded_residence_contact": 39,
        "recorded_foreign_tax_identifier": 41,
    },
}


class NumberedDeductionControls(Strict):
    tax_year: Literal["202627"]
    tan: str = Field(pattern=r"^[A-Z]{4}[0-9]{5}[A-Z]$")
    quarter: Literal["Q1", "Q2", "Q3", "Q4"]
    observed_on: date
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
    cash_withdrawal_general: Money
    cash_withdrawal_cooperative: Money
    record_status: Literal["current", "superseded", "cancelled"]
    crosswalk_document_version_id: UUID
    assessment: str = Field(min_length=10, max_length=2000)
    groups: list[NativeWithholdingGroup] = Field(min_length=1, max_length=5000)

    @model_validator(mode="before")
    @classmethod
    def exact_batch(cls, value):
        if isinstance(value, dict) and type(value.get("batch_count")) is not int:
            raise ValueError("Dated numbered deductions require one explicit integer batch")
        return value

    @model_validator(mode="after")
    def complete_population(self):
        keys = [key for group in self.groups for key in group.party_records]
        if len(keys) != self.party_count or len(set(keys)) != len(keys):
            raise ValueError("Cover every numbered deduction party exactly once in the crosswalk")
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess the dated source conflicts and independent controls")
        return self


@lru_cache(maxsize=2)
def layout(form):
    raw = Path(__file__).with_name(f"india_form{form}_layout.json").read_bytes()
    result = json.loads(raw)
    if (
        result["source_sha256"] != SPECS[form]
        or result["profile"] != f"india-form{form}-regular-20260722-v1.1"
    ):
        raise ValueError("Numbered deduction layout differs from its pinned original")
    return result, hashlib.sha256(raw).hexdigest()


def validate_party(form, f, amount, calendar):
    if not f[8].strip() or not re.fullmatch(r"[0-9]{4}", f[14]) or f[17] not in {"Y", "N"}:
        raise ValueError(f"Form {form} requires its name, four-digit code and deposited flag")
    for code, index in (("1065", 21), ("1064", 22)):
        if f[14] == code:
            amount(f[index], "recorded cash withdrawal")
        elif f[index]:
            raise ValueError("Recorded cash withdrawal field contradicts the selected source code")
    if f[30] and len(f[30]) != 26:
        raise ValueError("Recorded numbered form reference requires exactly 26 source characters")
    if f[31] == "A" and not re.fullmatch(r"[A-Za-z0-9]{10}|[A-Za-z0-9]{15}", f[32]):
        raise ValueError(
            "Recorded reason A requires its original 10/15-character certificate reference"
        )
    zero_codes = {"1059", "1034", "1038", "1061"} if form == "140" else {"1059", "1061"}
    if f[14] in zero_codes and (amount(f[23]) or amount(f[24]) or f[27] != "0.0000"):
        raise ValueError("The selected numbered code requires recorded zero tax, deposit and rate")
    if form == "144":
        if (
            not re.fullmatch(r"[0-9]{1,2}", f[11])
            or f[13] not in {"Y", "N"}
            or not re.fullmatch(r"[0-9]{1,3}", f[16])
            or f[20] not in {"Y", "N"}
            or f[29] not in {"A", "B"}
        ):
            raise ValueError(
                "Form144 requires explicit status, regime, destination, gross-up and rate-basis codes"
            )
        if f[15] and not re.fullmatch(r"[0-9]{1,2}", f[15]):
            raise ValueError("Recorded remittance code requires its bounded original digits")
        if any(f[33:36]):
            raise ValueError(
                "Unpopulated numbered144 filler fields remain unsupported and must be blank"
            )
        if f[38] and not re.fullmatch(r"[0-9]{1,15}", f[38]):
            raise ValueError("Recorded residence contact requires bounded source digits")
        if f[37] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", f[37]):
            raise ValueError("Recorded residence email lacks the specified source structure")
        missing_pan = f[7] in {"PANNOTAVBL", "PANAPPLIED", "PANINVALID"}
        if (
            missing_pan
            and f[31] == "C"
            and re.fullmatch(r"[0-9]{1,3}\.[0-9]{4}", f[27])
            and Decimal(f[27]) < 20
        ):
            if any(not f[i].strip() for i in (36, 37, 38, 40)):
                raise ValueError(
                    "Missing-PAN recorded low-rate reason C requires all four residence fields"
                )


def parse_deductions(content, data):
    formats = {f"india-form{form}-regular-20260722-v1.1": form for form in ("140", "144")}
    if data.file_format not in formats:
        raise ValueError("Unsupported dated numbered deduction format")
    form = formats[data.file_format]
    policy = NumberedPolicy(
        form=form,
        profile=f"india-form{form}-regular-20260722-v1.1",
        spec_sha256=SPECS[form],
        file_type="NS1",
        role="deductor",
        scheme="TDS",
        tax_name="tax_deducted",
        charge_name="penalty",
        layout_loader=partial(layout, form),
        party_fields=PARTY_FIELDS[form],
        context_fields=(27, 30, 31, 32)
        if form == "140"
        else (11, 13, 15, 16, 20, 27, 29, 30, 31, 32, 36, 37, 38, 40),
        validate_party=partial(validate_party, form),
        require_equal_deposit=False,
        additional_controls={"cash_withdrawal_general": 21, "cash_withdrawal_cooperative": 22},
        limitations=(
            "Dated numbered workbook v1.1 differs from current page v1.2; original incomplete public sample is not silently repaired",
            "Reported rate, destination, residence fields, status, gross-up and references do not establish tax law, treaty or certificate eligibility",
            "The Form144 reference label mentions Form15CA while its remark mentions Form121; no acknowledgment or filing authenticity is inferred",
            "No complete conditional code/annexure, FVU/CSI, portal-currentness, bank-payment or tax-credit qualification",
            "Tax deducted and allocated deposits remain separate prepared-statement observations; a non-deposited flag requires zero allocation",
        ),
    )
    return parse_numbered(content, data, data.numbered_deduction_controls, policy)
