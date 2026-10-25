"""Explicit bank-published EVP detail profile; EDR salary is counted only once."""

import csv
import io
import re
from decimal import Decimal
from typing import Any

from app.modules.country_workflows.schemas import WPS_VARIABLE_FIELDS

GUIDE_URL = "https://www.emiratesislamic.ae/-/media/ei/pdfs/business-online/salary-and-utility-payments/ei_businessonline_salary_wps_file_creation_user_guide.pdf"


def parse_wps_variable_pay(content, data, filename):
    from app.modules.country_workflows.native_sources import number, wps

    try:
        records = list(
            csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        )
    except (UnicodeDecodeError, csv.Error):
        raise ValueError("Invalid WPS EVP encoding or CSV records") from None
    if not 1 <= len(records) <= 10001 or any(
        len(row) != 10 or any(len(value) > 4000 or "\n" in value or "\r" in value for value in row)
        for row in records
    ):
        raise ValueError(
            "The EVP profile requires ten fields per record and at most 5,000 EDR/EVP pairs"
        )
    records = [[value.strip() for value in row] for row in records]
    if records[-1][0] != "SCR" or any(row[0] == "SCR" for row in records[:-1]):
        raise ValueError("The EVP profile requires exactly one final SCR trailer")
    if any(row[0] not in {"EDR", "EVP"} for row in records[:-1]):
        raise ValueError("WPS orphan or unknown records are unsupported")
    if not re.fullmatch(r"[0-9]{13}", records[-1][1]):
        raise ValueError("The EVP profile requires a 13-digit padded employer identifier")
    edrs, provenance = [], []
    totals = {name: Decimal(0) for name in WPS_VARIABLE_FIELDS}
    index, count = 0, 0
    while index < len(records) - 1:
        edr = records[index]
        if edr[0] != "EDR":
            raise ValueError(
                "Each EVP must immediately follow its own EDR; orphan or unknown records are unsupported"
            )
        edrs.append(edr)
        source: dict[str, Any] = {"source_row": index + 1}
        index += 1
        if index < len(records) - 1 and records[index][0] == "EVP":
            evp = records[index]
            if evp[1:3] != edr[1:3]:
                raise ValueError(
                    "EVP employee and agent routing must agree with the immediately preceding EDR"
                )
            if any(len(value) > 15 for value in evp[3:]):
                raise ValueError(
                    "EVP component exceeds the bank profile's 15-character amount bound"
                )
            components = {
                name: number(value, places=2)
                for name, value in zip(WPS_VARIABLE_FIELDS, evp[3:], strict=True)
            }
            if sum(components.values(), Decimal(0)) != number(edr[8], places=2):
                raise ValueError("EVP component sum does not agree with its EDR variable income")
            source.update(
                source_variable_pay_row=index + 1,
                variable_pay_components={name: str(value) for name, value in components.items()},
            )
            for name, value in components.items():
                totals[name] += value
            count += 1
            index += 1
        elif number(edr[8], places=2) != 0:
            raise ValueError(
                "A nonzero EDR variable amount requires its corresponding EVP record in this profile"
            )
        provenance.append(source)
        if len(edrs) > 5000:
            raise ValueError("The EVP profile exceeds 5,000 employees")
    if count != data.wps_variable_pay_count or totals != data.wps_variable_pay_totals:
        raise ValueError("Independent EVP count or component-total controls do not agree")
    # Reuse the existing EDR/SCR identity, IBAN, date, salary, employee and filename
    # controls. Only EDRs contribute obligations; EVP details are never new dues.
    normalized = io.StringIO(newline="")
    csv.writer(normalized, lineterminator="\n").writerows([*edrs, records[-1]])
    rows, metadata = wps(normalized.getvalue().encode(), data, filename)
    for row, original in zip(rows, provenance, strict=True):
        row.update(original)
    return rows, {
        **metadata,
        "profile": "emirates-islamic-edr-evp-scr/1",
        "profile_source": GUIDE_URL,
        "physical_record_count": len(records),
        "variable_pay_record_count": count,
        "variable_pay_component_totals": {name: str(value) for name, value in totals.items()},
        "variable_pay_basis": "EVP_DETAILS_ALREADY_INCLUDED_IN_EDR_VARIABLE_INCOME_NOT_ADDITIONAL_SALARY",
        "agent_routing_ownership": "NOT_VERIFIED_AGAINST_BANK_MASTER",
    }
