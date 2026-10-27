"""Explicit six-column ESIC member/wage XLS evidence, never filing proof."""

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.modules.country_workflows.esic_population import REFERENCE, ESICMember, verify_controls
from app.modules.ingestion.legacy_xls import text_table

HEADER_PREFIXES = (
    "ipnumber",
    "ipname",
    "noofdays",
    "totalmonthlywages",
    "reasoncodeforzero",
    "lastworkingday",
)


def parse_esic_xls(content, data, filename):
    if Path(filename).suffix.casefold() != ".xls":
        raise ValueError("The ESIC BIFF8 profile requires an original .xls filename")
    records, metadata = text_table(content, width=6, max_rows=5001)
    normalized = [re.sub(r"[^a-z0-9]", "", value.casefold()) for value in records[0]]
    if any(
        not header.startswith(prefix)
        for header, prefix in zip(normalized, HEADER_PREFIXES, strict=True)
    ):
        raise ValueError("ESIC XLS must retain the illustrated six-column header order in row 1")
    rows, seen, trailing_blanks = [], set(), 0
    for number, values in enumerate(records[1:], 2):
        if not any(values):
            trailing_blanks += 1
            continue
        if trailing_blanks:
            raise ValueError("Blank gaps within the ESIC member population are unsupported")
        if any(value != value.strip() for value in values):
            raise ValueError("Retain exact ESIC XLS text without surrounding whitespace")
        subject, name, days_text, wages_text, reason, date_text = values
        if subject in seen:
            raise ValueError("Duplicate ESIC IP number within the native employer/month file")
        seen.add(subject)
        if not re.fullmatch(r"[0-9]{1,2}", days_text) or not re.fullmatch(
            r"[0-9]{1,26}(?:\.[0-9]{1,2})?", wages_text
        ):
            raise ValueError("ESIC days and wages require whole-day and plain unsigned wage text")
        if reason and not re.fullmatch(r"[0-9]{1,3}", reason):
            raise ValueError(
                "Retain the numeric ESIC reason code; do not replace it with an inferred description"
            )
        days, wages = int(days_text), Decimal(wages_text)
        if (not days or not wages) and not reason:
            raise ValueError(
                "Zero-day or zero-wage ESIC records require an explicit retained reason code"
            )
        last = None
        if date_text:
            if not re.fullmatch(r"[0-9]{2}([/-])[0-9]{2}\1[0-9]{4}", date_text):
                raise ValueError(
                    "ESIC last working day must retain padded DD/MM/YYYY or DD-MM-YYYY text"
                )
            last = datetime.strptime(
                date_text, "%d/%m/%Y" if "/" in date_text else "%d-%m-%Y"
            ).date()
        item = ESICMember(
            id=f"ESIC-XLS-{number}",
            registration=data.employer_registration,
            period=data.obligation_period,
            subject=subject,
            member_name=name,
            paid_days=days,
            amount=wages,
            zero_wage_reason=reason if not wages else "",
            zero_day_reason="" if reason == "0" and days else reason,
            last_working_day=last,
            evidence_reference=f"{metadata['sheet']}!A{number}:F{number}",
            assessment=data.esic_scope_assessment,
        ).model_dump(mode="json")
        rows.append(
            {
                **item,
                "source_sheet": metadata["sheet"],
                "source_row": number,
                "source_text_cells": {
                    f"{chr(65 + col)}{number}": value for col, value in enumerate(values)
                },
                "source_zero_day_reason": reason,
                "source_last_working_day": date_text,
            }
        )
    controls = verify_controls(
        rows, data.esic_paid_days_control, data.esic_zero_wage_members_control
    )
    return rows, {
        **metadata,
        "currency": "INR",
        "profile": "esic-six-column-text-biff8/1",
        "profile_reference": REFERENCE,
        "original_headers": records[0],
        "trailing_blank_rows": trailing_blanks,
        "registration": data.employer_registration,
        "wage_month": data.obligation_period,
        "return_kind": data.esic_return_kind,
        "scope_assessment": data.esic_scope_assessment,
        "context_evidence_version_id": str(data.esic_context_evidence_version_id),
        "population_controls": controls,
        "reason_mapping": "LITERAL_CODES_NO_LEGAL_APPLICABILITY_MAPPING",
        "supplementary_composition": "NOT_PERFORMED",
        "filing_status": "NOT_VERIFIED_BY_WORKBOOK",
        "payment_status": "NOT_VERIFIED_BY_WORKBOOK",
    }
