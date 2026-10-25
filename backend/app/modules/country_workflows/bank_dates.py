"""Separate booked and value dates; value-date fallback is not cutoff evidence."""

import re


def date_details(row):
    basis = row.get("bank_date_basis")
    # Retained v2 MT940 rows predate the explicit basis field. Do not let a
    # historical value-date fallback become booking evidence merely by replay.
    entry = row.get("source_mt940_entry", "")
    legacy_fallback = not basis and bool(re.match(r"^\d{6}(?:RC|RD|C|D)", entry))
    uncertain = basis == "VALUE_DATE_FALLBACK" or legacy_fallback
    return {
        "transaction_date": row["date"],
        "bank_booking_date": row.get("bank_booking_date"),
        "bank_value_date": row.get("bank_value_date"),
        "bank_date_basis": "VALUE_DATE_FALLBACK"
        if legacy_fallback
        else basis
        or ("BOOKING_DATE" if row.get("bank_booking_date") else "DECLARED_TRANSACTION_DATE"),
        "booking_date_review_required": uncertain,
    }
