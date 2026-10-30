"""Retained regular-statement observations, not FVU validation or filing evidence."""

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.modules.jurisdictions.profiles import Strict

SOURCE = "https://tinpan.proteantech.in/downloads/e-tds/eTDS-download-regular.html"
CONTRACT = "retained-regular-withholding-observations/1"
Money = Annotated[Decimal, Field(ge=0, max_digits=28, decimal_places=2, allow_inf_nan=False)]
Text = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^\S(?:.*\S)?$")]
PartyKey = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,8}/[1-9][0-9]{0,8}/[1-9][0-9]{0,8}$")]
WIDTHS = {"FH": 18, "BH": 72, "CD": 41, "DD": 54}
FORMATS = {
    "india-26q-regular-v7.8": ("26Q", "TDS", "deductor"),
    "india-27eq-regular-v6.9": ("27EQ", "TCS", "collector"),
    "india-27q-regular-v7.5": ("27Q", "TDS", "deductor"),
}
NONRESIDENT_FIELDS = {
    "recorded_rate_basis": 35,
    "nature_of_remittance_code": 36,
    "form_15ca_reference": 37,
    "residence_country_code": 38,
    "deductee_email": 39,
    "deductee_contact": 40,
    "residence_address": 41,
    "foreign_tax_identifier": 42,
    "cash_withdrawal_194n": 43,
    "cash_withdrawal_194n_first_band": 44,
    "cash_withdrawal_194n_second_band": 45,
    "cash_withdrawal_cooperative_194n": 46,
    "cash_withdrawal_cooperative_first_band": 47,
    "cash_withdrawal_cooperative_second_band": 48,
    "recorded_115bac_opt_out": 49,
}


@lru_cache(maxsize=1)
def profile_limits():
    content = Path(__file__).with_name("india_withholding_native_limits.json").read_bytes()
    return json.loads(content), hashlib.sha256(content).hexdigest()


class NativeWithholdingGroup(Strict):
    transaction_reference: Text
    transaction_date: date
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    rule_reference: Text
    party_records: list[PartyKey] = Field(min_length=1, max_length=5000)


class NativeWithholdingControls(Strict):
    tan: str = Field(pattern=r"^[A-Z]{4}[0-9]{5}[A-Z]$")
    financial_year: str = Field(pattern=r"^20[0-9]{4}$")
    quarter: Literal["Q1", "Q2", "Q3", "Q4"]
    observed_on: date
    batch_count: int = Field(ge=1, le=100, strict=True)
    challan_count: int = Field(ge=1, le=5000, strict=True)
    party_count: int = Field(ge=1, le=5000, strict=True)
    income_tax: Money
    surcharge: Money
    cess: Money
    allocated_deposit: Money
    challan_deposit: Money
    payment_base: Money
    purchase_value: Money | None = None
    record_status: Literal["current", "superseded", "cancelled"]
    crosswalk_document_version_id: UUID
    assessment: str = Field(min_length=10, max_length=2000)
    groups: list[NativeWithholdingGroup] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def declared_population(self):
        year = int(self.financial_year[:4])
        if not 2010 <= year <= 2025 or self.financial_year[4:] != f"{(year + 1) % 100:02}":
            raise ValueError(
                "These legacy profiles cover FY 2010-11 through 2025-26; successor forms are separate"
            )
        parties = [key for group in self.groups for key in group.party_records]
        if len(parties) != self.party_count or len(set(parties)) != len(parties):
            raise ValueError(
                "Every native party record needs one explicit, non-overlapping crosswalk group"
            )
        if len(self.assessment.strip()) < 10:
            raise ValueError(
                "Assess the retained crosswalk, source selection and independent controls"
            )
        return self


def parse_regular(content, data):
    from app.modules.country_workflows.withholding_schemas import WithholdingRecord

    controls = data.native_withholding_controls
    if controls is None:
        raise ValueError("Native withholding requires independent statement and crosswalk controls")
    form, scheme, role = FORMATS[data.file_format]
    limits, limits_sha256 = profile_limits()
    if (
        form == "27EQ"
        and controls.purchase_value is None
        or form != "27EQ"
        and controls.purchase_value is not None
    ):
        raise ValueError("A purchase-value control applies to 27EQ only and is required there")
    if not content.endswith(b"\r\n") or len(content) > 10 * 1024 * 1024:
        raise ValueError(
            "The selected regular profile requires bounded original ASCII records ending in CRLF"
        )
    try:
        lines = content[:-2].decode("ascii").split("\r\n")
    except UnicodeDecodeError:
        raise ValueError("Regular statement profile requires ASCII, without a BOM") from None
    if len(lines) > 16000 or any(
        not line or len(line) > 8192 or any(ord(c) < 32 for c in line) for line in lines
    ):
        raise ValueError("Unsupported blank, oversized or control-character statement record")

    def integer(value):
        if not re.fullmatch(r"[0-9]{1,9}", value):
            raise ValueError("Native record counts and sequence numbers require bounded integers")
        return int(value)

    def money(value):
        if not re.fullmatch(r"[0-9]{1,12}\.[0-9]{2}", value):
            raise ValueError(
                "Native tax and payment amounts require nonnegative two-decimal values"
            )
        return Decimal(value)

    def calendar(value):
        if not re.fullmatch(r"[0-9]{8}", value):
            raise ValueError("Native statement dates require ddmmyyyy")
        try:
            parsed = datetime.strptime(value, "%d%m%Y").date()
        except ValueError:
            raise ValueError("Invalid native statement calendar date") from None
        if parsed > controls.observed_on:
            raise ValueError(
                "Native statement date exceeds the independently declared observation cutoff"
            )
        return parsed

    records = []
    for ordinal, line in enumerate(lines, 1):
        fields = line.split("^")
        tag = fields[1] if len(fields) > 1 else ""
        if tag not in WIDTHS or len(fields) != WIDTHS[tag] or integer(fields[0]) != ordinal:
            raise ValueError(
                "Native statement record type, exact field count or line sequence does not agree"
            )
        records.append(fields)
        if any(
            limit is not None and len(value) > limit
            for value, limit in zip(fields, limits[form]["field_lengths"][tag], strict=True)
        ):
            raise ValueError("Native record field exceeds the selected issuer layout width")
    first = records[0]
    if (
        first[1] != "FH"
        or first[2] != ("TC1" if form == "27EQ" else "NS1")
        or first[3] != "R"
        or first[7] != controls.tan
    ):
        raise ValueError(
            "Select the matching regular statement type and independently declared TAN; corrections are separate"
        )
    calendar(first[4])
    year = int(controls.financial_year[:4])
    assessment_year = str(year + 1) + f"{(year + 2) % 100:02}"
    start, end = date(year, 4, 1), date(year + 1, 3, 31)
    quarter_months = {"Q1": (4, 5, 6), "Q2": (7, 8, 9), "Q3": (10, 11, 12), "Q4": (1, 2, 3)}[
        controls.quarter
    ]
    batch, challan = None, None
    batches: dict[int, list[str]] = {}
    challans: dict[tuple[int, int], list[str]] = {}
    parties = {}
    batch_challans: dict[int, list[list[str]]] = {}
    challan_parties: dict[tuple[int, int], list[list[str]]] = {}
    original_headers = []
    for fields in records[1:]:
        tag = fields[1]
        if tag == "BH":
            batch = integer(fields[2])
            challan = None
            if (
                batch != len(batches) + 1
                or batch in batches
                or fields[4] != form
                or fields[12] != controls.tan
                or fields[15] != assessment_year
                or fields[16] != controls.financial_year
                or fields[17] != controls.quarter
            ):
                raise ValueError(
                    "Native batch identity, TAN, form, financial/assessment year or quarter differs from its controls"
                )
            batches[batch] = fields
            original_headers.append(
                {
                    "record_type": tag,
                    "line": integer(fields[0]),
                    "batch": batch,
                    "challan_count": integer(fields[3]),
                    "challan_deposit": str(money(fields[46])),
                }
            )
        elif tag == "CD":
            if batch is None or integer(fields[2]) != batch:
                raise ValueError("A challan must belong to the preceding declared batch")
            challan = (batch, integer(fields[3]))
            if (
                challan[1] != len(batch_challans.get(batch, [])) + 1
                or challan in challans
                or fields[5] not in {"Y", "N"}
            ):
                raise ValueError("Duplicate or invalid native challan identity or nil flag")
            if fields[5] == "Y":
                raise ValueError(
                    "Nil statements are separate from this nonempty party-observation profile"
                )
            if fields[36] not in {"Y", "N"}:
                raise ValueError(
                    "Native challan book-entry flag must explicitly select Y or N before deposit controls apply"
                )
            calendar(fields[17])
            if (
                sum(money(fields[i - 1]) for i in (22, 23, 24, 25, 26, 39)) != money(fields[26])
                or money(fields[26]) % 1
            ):
                raise ValueError(
                    "Native challan gross amount must equal its tax, surcharge, cess, interest, other and fee components as a whole-rupee amount"
                )
            challans[challan] = fields
            batch_challans.setdefault(batch, []).append(fields)
        elif tag == "DD":
            if challan is None or (integer(fields[2]), integer(fields[3])) != challan:
                raise ValueError("A party record must belong to its preceding native challan")
            key = f"{batch}/{challan[1]}/{integer(fields[4])}"
            if (
                integer(fields[4]) != len(challan_parties.get(challan, [])) + 1
                or key in parties
                or fields[5] != "O"
            ):
                raise ValueError("Duplicate party identity or unsupported regular-record mode")
            if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", fields[9]) and fields[9] not in {
                "PANNOTAVBL",
                "PANAPPLIED",
                "PANINVALID",
            }:
                raise ValueError(
                    "Retain an explicit native PAN or documented native missing-PAN sentinel"
                )
            calendar(fields[22])
            tax_date = calendar(fields[23]) if fields[23] else None
            if sum(money(fields[i - 1]) for i in (14, 15, 16)) != money(fields[16]):
                raise ValueError(
                    "Native party total tax differs from income tax, surcharge and cess"
                )
            money(fields[18])
            money(fields[21])
            if form == "27EQ":
                money(fields[20])
            if form == "27Q":
                if year >= 2013 and (
                    fields[34] not in {"A", "B"}
                    or not re.fullmatch(r"[0-9]{1,3}", fields[35])
                    or not re.fullmatch(r"[0-9]{1,3}", fields[37])
                ):
                    raise ValueError(
                        "Retain explicit nonresident rate-basis, remittance and residence-country codes; no treaty or residence is inferred"
                    )
                if year < 2013 and any(fields[index] for index in range(34, 38)):
                    raise ValueError(
                        "Nonresident remittance fields in this layout apply from FY 2013-14"
                    )
                for value in fields[42:48]:
                    if value:
                        money(value)
                if year >= 2023 and fields[48] not in {"Y", "N"}:
                    raise ValueError(
                        "Retain the explicit recorded nonresident 115BAC opt-out flag from FY 2023-24"
                    )
            if money(fields[16]) and tax_date is None:
                raise ValueError(
                    "A positive regular tax observation needs its retained deduction/collection date"
                )
            observed_period = (tax_date or calendar(fields[22])).strftime("%Y-%m")
            if (
                int(observed_period[:4]) != year + (int(observed_period[5:]) < 4)
                or int(observed_period[5:]) not in quarter_months
            ):
                raise ValueError(
                    "Native deduction/collection observation lies outside its declared financial quarter"
                )
            if not re.fullmatch(r"[0-9]{1,3}\.[0-9]{4}", fields[25]):
                raise ValueError(
                    "Native recorded rate requires four decimal places; no statutory rate is inferred"
                )
            code = fields[32] or challans[challan][20]
            if not re.fullmatch(r"[A-Z0-9]{1,3}", code):
                raise ValueError("An explicit native section/collection code is required")
            parties[key] = {"fields": fields, "period": observed_period, "code": code}
            challan_parties.setdefault(challan, []).append(fields)
        else:
            raise ValueError(
                "Only one initial FH followed by complete BH/CD/DD populations is supported"
            )
    if (
        integer(first[8]) != len(batches)
        or len(batches) != controls.batch_count
        or len(challans) != controls.challan_count
        or len(parties) != controls.party_count
    ):
        raise ValueError(
            "Native header, batch, challan and party populations differ from independent controls"
        )
    for identifier, fields in batches.items():
        selected = batch_challans.get(identifier, [])
        if len(selected) != integer(fields[3]) or sum(money(v[26]) for v in selected) != money(
            fields[46]
        ):
            raise ValueError("Native batch challan count or deposit control does not agree")
    for challan_key, fields in challans.items():
        selected = challan_parties.get(challan_key, [])
        if len(selected) != integer(fields[4]) or not selected:
            raise ValueError(
                "Native challan party count does not agree; no partial population is imported"
            )
        for target, source in ((29, 19), (30, 14), (31, 15), (32, 16), (33, 17)):
            if money(fields[target - 1]) != sum(money(v[source - 1]) for v in selected):
                raise ValueError(
                    "Native challan-to-party tax or allocated-deposit control does not agree"
                )
        minimum = money(fields[28])
        if fields[36] == "N":
            minimum += sum(money(fields[i - 1]) for i in (34, 35, 39))
        if money(fields[26]) < minimum:
            raise ValueError(
                "Native challan gross deposit cannot be below the claimed allocated deposit and applicable recorded charges"
            )
    calculated = {
        "income_tax": sum(money(v["fields"][13]) for v in parties.values()),
        "surcharge": sum(money(v["fields"][14]) for v in parties.values()),
        "cess": sum(money(v["fields"][15]) for v in parties.values()),
        "allocated_deposit": sum(money(v["fields"][18]) for v in parties.values()),
        "payment_base": sum(money(v["fields"][21]) for v in parties.values()),
        "challan_deposit": sum(money(v[26]) for v in challans.values()),
    }
    if form == "27EQ":
        calculated["purchase_value"] = sum(money(v["fields"][20]) for v in parties.values())
    if any(getattr(controls, key) != value for key, value in calculated.items()):
        raise ValueError(
            "Independent native component, payment-base or challan controls do not agree"
        )
    mapped = [key for group in controls.groups for key in group.party_records]
    if set(mapped) != set(parties):
        raise ValueError(
            "The retained crosswalk must cover every native party identity exactly once"
        )
    digest = hashlib.sha256(content).hexdigest()
    rows, links = [], []
    for ordinal, group in enumerate(controls.groups, 1):
        group_parties = [parties[key] for key in group.party_records]
        if (
            len({(v["fields"][9], v["code"], v["period"]) for v in group_parties}) != 1
            or group.period != group_parties[0]["period"]
        ):
            raise ValueError(
                "Each mapped observation must retain one PAN, native section code and reporting month"
            )
        if (
            form == "27Q"
            and len(
                {tuple(v["fields"][index] for index in (34, 35, 37, 41)) for v in group_parties}
            )
            != 1
        ):
            raise ValueError(
                "A nonresident crosswalk group cannot merge distinct rate bases, remittance kinds, residence countries or foreign tax identifiers"
            )
        if (
            form == "27Q"
            and len(group_parties) > 1
            and group_parties[0]["fields"][9] in {"PANNOTAVBL", "PANAPPLIED", "PANINVALID"}
            and (
                not group_parties[0]["fields"][41].strip()
                or len({v["fields"][12] for v in group_parties}) != 1
            )
        ):
            raise ValueError(
                "Missing-PAN nonresident parties cannot be grouped without the same retained name and nonempty foreign tax identifier"
            )
        row = WithholdingRecord(
            id=f"{form}:group:{ordinal}",
            registration=controls.tan,
            counterparty=group_parties[0]["fields"][9],
            legal_role=role,
            tax_kind=scheme,
            rule_reference=group.rule_reference,
            tax_year_start=start,
            tax_year_end=end,
            period=group.period,
            transaction_reference=group.transaction_reference,
            transaction_date=group.transaction_date,
            currency="INR",
            amount=sum(money(v["fields"][16]) for v in group_parties),
            record_status=controls.record_status,
            source_reference=f"PROTEAN:{form}:group:{ordinal}",
            source_version="uploaded-sha256:" + digest,
        ).model_dump(mode="json")
        rows.append(
            {
                **row,
                "native_party_count": len(group_parties),
                "native_section_code": group_parties[0]["code"],
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
                    "name": f[12],
                    "pan": f[9],
                    "native_section_code": v["code"],
                    "native_payment_date": calendar(f[22]).isoformat(),
                    "native_tax_date": calendar(f[23]).isoformat() if f[23] else None,
                    "income_tax": str(money(f[13])),
                    "surcharge": str(money(f[14])),
                    "cess": str(money(f[15])),
                    "total_tax": str(money(f[16])),
                    "allocated_deposit": str(money(f[18])),
                    "payment_base": str(money(f[21])),
                    "recorded_rate": f[25],
                    "reason_flag": f[29],
                    "certificate_reference": f[33],
                    **(
                        {name: f[position - 1] for name, position in NONRESIDENT_FIELDS.items()}
                        if form == "27Q"
                        else {}
                    ),
                }
            )
    if len(rows) != data.expected_rows:
        raise ValueError("Independent mapped withholding observation count does not agree")
    return rows, {
        "contract": CONTRACT,
        "layout_limits_sha256": limits_sha256,
        "layout_specification_sha256": limits[form]["source_sha256"],
        "form": form,
        "source": SOURCE,
        "source_sha256": digest,
        "financial_year": controls.financial_year,
        "assessment_year": assessment_year,
        "quarter": controls.quarter,
        "tan": controls.tan,
        "batch_count": len(batches),
        "challan_count": len(challans),
        "party_count": len(parties),
        "mapped_observations": len(rows),
        "controls": controls.model_dump(mode="json"),
        "component_controls": {k: str(v) for k, v in calculated.items()},
        "batch_controls": original_headers,
        "challan_controls": [
            {
                "batch": key[0],
                "challan": key[1],
                "source_line": integer(fields[0]),
                "challan_number": fields[11],
                "ddo_serial": fields[13],
                "bsr_or_form24g_reference": fields[15],
                "challan_date": calendar(fields[17]).isoformat(),
                "nil_flag": fields[5],
                "book_entry_flag": fields[36],
                "gross_deposit": str(money(fields[26])),
                "allocated_deposit": str(money(fields[28])),
                "recorded_interest": str(money(fields[33])),
                "recorded_other": str(money(fields[34])),
                "fee": str(money(fields[38])),
            }
            for key, fields in challans.items()
        ],
        "party_links": links,
        "filing_or_acknowledgment": "NOT_EVIDENCED",
        "bank_payment_or_tax_credit": "NOT_EVIDENCED",
        "fvu_validation": "NOT_PERFORMED",
        "validation_basis": "RECORD_STRUCTURE_DECLARED_CONTROLS_AND_ASSESSED_CROSSWALK_NOT_GOVERNMENT_FILE_VALIDATION",
        "all_original_fields": "RETAINED_IN_HASH_VERIFIED_ORIGINAL_FILE",
        **(
            {"nonresident_treaty_and_residence_qualification": "NOT_PERFORMED"}
            if form == "27Q"
            else {}
        ),
        "limitations": [
            "Regular uploaded statement observations only; no correction, portal-currentness, FVU, CSI or filing qualification",
            "Conditional mandatory-field, legal-code and certificate eligibility checks remain outside this observed-amount import profile",
            "Operator-assessed source selection and retained transaction/section crosswalk; no legal rate or threshold inference",
            "Allocated tax in a prepared statement is not independent bank settlement or posted tax credit",
        ],
    }
