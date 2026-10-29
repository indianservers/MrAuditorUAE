"""Source-bound account identity comparison; syntax is not bank authentication."""

import re
import unicodedata
from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from app.modules.jurisdictions.profiles import Strict

PROFILE_VERSION = "bank-account-evidence/1"
REFERENCES = {
    "AE": "https://centralbank.ae/en/our-operations/payments-and-settlements/regulations-and-standards/iban/",
    "IN": "https://www.rbi.org.in/Scripts/FAQView.aspx?Id=60",
}
ROLES = ("register", "ledger", "bank")


def owner_name(value):
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def identifier(value):
    # Formatting spaces and ASCII case only; leading zeros and punctuation stay.
    return value.replace(" ", "").translate(
        str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    )


class BankAccountEvidence(Strict):
    id: str = Field(min_length=1, max_length=120)
    account: str = Field(min_length=1, max_length=120)
    bank_country: str = Field(pattern=r"^[A-Z]{2}$")
    account_scheme: Literal["IBAN", "LOCAL"]
    account_number: str = Field(min_length=1, max_length=120)
    routing_code: str = Field(default="", max_length=35)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    owner_country: str = Field(pattern=r"^[A-Z]{2}$")
    owner_name: str = Field(default="", max_length=200)
    owner_identifier_scheme: str = Field(default="", max_length=80)
    owner_identifier: str = Field(default="", max_length=120)
    valid_from: date
    valid_through: date
    assertion_status: Literal["confirmed", "unconfirmed", "closed"] = "unconfirmed"
    evidence_reference: str = Field(min_length=1, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def ordered(self):
        if self.valid_from > self.valid_through:
            raise ValueError("Account evidence validity dates must be ordered")
        if len(self.assessment.strip()) < 10 or not self.evidence_reference.strip():
            raise ValueError("Retain an account evidence reference and meaningful assessment")
        return self


def syntax(row):
    account, routing = identifier(row["account_number"]), identifier(row["routing_code"])
    if row["bank_country"] == "AE":
        if row["account_scheme"] != "IBAN" or not re.fullmatch(r"AE[0-9]{21}", account):
            return "UAE_IBAN_FORMAT_UNRESOLVED"
        # AE letters move to the end as 10,14. No arbitrary-size input conversion.
        rearranged = account[4:] + "1014" + account[2:4]
        if not 2 <= int(account[2:4]) <= 98 or int(rearranged) % 97 != 1:
            return "UAE_IBAN_CHECK_DIGITS_INVALID"
        if routing and routing != account[4:7]:
            return "UAE_BANK_CODE_DIFFERS_FROM_IBAN"
    elif row["bank_country"] == "IN":
        if row["account_scheme"] != "LOCAL":
            return "INDIA_LOCAL_ACCOUNT_SCHEME_REQUIRED"
        # No invented universal Indian account-number length or zero stripping.
        if not re.fullmatch(r"[A-Z0-9]{1,120}", account):
            return "INDIA_ACCOUNT_REPRESENTATION_UNRESOLVED"
        if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", routing):
            return "INDIA_IFSC_FORMAT_UNRESOLVED"
    else:
        return "BANK_COUNTRY_PROFILE_NOT_SUPPORTED"
    return None


def compare(data, tables, country):
    from app.modules.country_workflows.audit_calculations import result
    from app.modules.country_workflows.bank_observation_scope import selected_scope

    observations = selected_scope(data)
    start = date.fromisoformat(observations["from"]) if observations else data.as_of
    end = date.fromisoformat(observations["through"]) if observations else data.as_of

    selected = {}
    for role in ROLES:
        if len(tables[role]) != 1:
            raise ValueError("Retain exactly one account assertion per independent source role")
        selected[role] = tables[role][0]
        if selected[role]["account"] != data.account:
            raise ValueError("Account evidence scope differs from the selected ledger account")
    master = selected["register"]
    rows = []
    for role in ROLES:
        row = selected[role]
        issues = []
        problem = syntax(row)
        if problem:
            issues.append(problem)
        if row["currency"] != data.currency:
            issues.append("ACCOUNT_CURRENCY_DIFFERS_FROM_SCOPE")
        if row["owner_country"] != country:
            issues.append("OWNER_COUNTRY_DIFFERS_FROM_ENGAGEMENT")
        if not row["owner_name"].strip() or owner_name(row["owner_name"]) != owner_name(
            data.bank_owner_name
        ):
            issues.append("OWNER_NAME_UNRESOLVED")
        for field in ("owner_identifier_scheme", "owner_identifier"):
            if not row[field].strip() or identifier(row[field]) != identifier(
                getattr(data, "bank_" + field)
            ):
                issues.append(field.upper() + "_UNRESOLVED")
        if row["assertion_status"] != "confirmed":
            issues.append("ACCOUNT_ASSERTION_NOT_CONFIRMED")
        if (
            not date.fromisoformat(row["valid_from"])
            <= start
            <= end
            <= date.fromisoformat(row["valid_through"])
        ):
            issues.append("ACCOUNT_EVIDENCE_OUTSIDE_VALIDITY")
        for field in ("bank_country", "account_scheme", "account_number", "routing_code"):
            if identifier(row[field]) != identifier(master[field]):
                issues.append(field.upper() + "_DIFFERS_FROM_REGISTER")
        rows.append(
            {
                "id": "account-" + role,
                "source_role": role,
                "source_row_id": row["id"],
                **{
                    field: row[field]
                    for field in (
                        "account",
                        "bank_country",
                        "account_scheme",
                        "account_number",
                        "routing_code",
                        "currency",
                        "owner_country",
                        "owner_name",
                        "owner_identifier_scheme",
                        "owner_identifier",
                        "valid_from",
                        "valid_through",
                        "assertion_status",
                        "evidence_reference",
                        "assessment",
                    )
                },
                "exceptions": issues,
                "state": "EXCEPTIONS" if issues else "MATCHED",
            }
        )
    return {
        **result(
            rows,
            any(row["exceptions"] for row in rows),
            [
                "Declared register, ledger setup and retained bank evidence agreement only; no live bank or registry request is made",
                "IBAN/IFSC checks establish syntax only, not bank existence, account ownership, authority, funds or payment execution",
                "Owner identifier scheme and value require independently assessed retained evidence; owner name scope is bound to the engagement entity by the API",
                "Exact identifier comparison preserves leading zeros; only ASCII case/spaces are normalized; names do not use fuzzy legal-name substitution",
                "Only UAE IBAN and India local-account/IFSC syntax profiles are supported; foreign bank countries need separate profiles",
            ],
        ),
        "bank_account_contract": PROFILE_VERSION,
        **({"bank_observation_scope": observations} if observations else {}),
        "bank_account_scope": {
            "account": data.account,
            "currency": data.currency,
            "owner_name": data.bank_owner_name,
            "owner_identifier_scheme": data.bank_owner_identifier_scheme,
            "owner_identifier": data.bank_owner_identifier,
            "owner_country": country,
        },
        "bank_profile_references": {
            code: REFERENCES.get(code) for code in sorted({row["bank_country"] for row in rows})
        },
        "bank_authentication_status": "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON",
    }
