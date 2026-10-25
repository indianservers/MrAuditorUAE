"""Exact document-series counts; no inference of invoice continuity or filing."""

import calendar
import re
from datetime import date

from pydantic import Field, field_validator, model_validator

from app.core.json_documents import read_json_document
from app.modules.country_workflows.audit_calculations import result
from app.modules.jurisdictions.profiles import Strict

FORMAT = "india-gstr1-document-series-json"
REFERENCE = "https://whitebooks.in/developer/gst-api/put-gstr1-retsave"
FIELDS = ("issued", "cancelled", "net_issued")


def integer(value):
    if isinstance(value, bool) or not (
        isinstance(value, int) or isinstance(value, str) and re.fullmatch(r"[0-9]{1,18}", value)
    ):
        raise ValueError("Document counts and category/row numbers require explicit integers")
    return int(value)


class SeriesCounts(Strict):
    issued: int = Field(ge=0, le=10**12)
    cancelled: int = Field(ge=0, le=10**12)
    net_issued: int = Field(ge=0, le=10**12)

    @field_validator(*FIELDS, mode="before")
    @classmethod
    def whole(cls, value):
        return integer(value)

    @model_validator(mode="after")
    def arithmetic(self):
        if self.issued - self.cancelled != self.net_issued:
            raise ValueError("Issued less cancelled must equal net issued")
        return self


class DocumentSeries(SeriesCounts):
    id: str = Field(min_length=1, max_length=120)
    registration: str = Field(pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$")
    period: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    doc_num: int = Field(ge=1, le=999)
    serial_from: str = Field(max_length=120)
    serial_to: str = Field(max_length=120)

    @field_validator("doc_num", mode="before")
    @classmethod
    def category(cls, value):
        return integer(value)

    @field_validator("serial_from", "serial_to")
    @classmethod
    def literal_serial(cls, value):
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError(
                "Retain literal serial identifiers without surrounding whitespace or controls"
            )
        return value

    @model_validator(mode="after")
    def scope(self):
        date.fromisoformat(self.period + "-01")
        if bool(self.serial_from) != bool(self.serial_to) or self.issued and not self.serial_from:
            raise ValueError("Issued documents require both retained serial endpoints")
        return self


def identity(row):
    return tuple(
        row[field] for field in ("registration", "period", "doc_num", "serial_from", "serial_to")
    )


def verify_controls(rows, controls):
    if controls is None or not rows:
        raise ValueError("Document series require explicit rows and independent count controls")
    if len({identity(row) for row in rows}) != len(rows):
        raise ValueError("Duplicate document-series scope; counts cannot be added")
    totals = {field: sum(row[field] for row in rows) for field in FIELDS}
    if totals != controls.model_dump():
        raise ValueError("Independent issued, cancelled and net-issued controls do not agree")
    return totals


def parse_series(content, data):
    root = read_json_document(content)
    depth = 0
    while isinstance(root, dict) and "doc_issue" not in root and "data" in root and depth < 2:
        if (
            set(root) - {"data", "code", "status_cd", "timestamp", "transaction_id"}
            or ("code" in root and root["code"] != 200)
            or ("status_cd" in root and root["status_cd"] != "1")
        ):
            raise ValueError("Unsupported or unsuccessful document-series response wrapper")
        root = root["data"]
        depth += 1
    if not isinstance(root, dict) or set(root) - {"gstin", "fp", "ret_period", "doc_issue"}:
        raise ValueError("Retain the complete supported document-series section response")
    expected_period = data.gst_period[5:] + data.gst_period[:4]
    if ("gstin" in root and root["gstin"] != data.gst_registration) or any(
        name in root and root[name] != expected_period for name in ("fp", "ret_period")
    ):
        raise ValueError("Document-series payload differs from the assessed GSTIN/period")
    section = root.get("doc_issue")
    if not isinstance(section, dict) or set(section) - {"flag", "chksum", "doc_det"}:
        raise ValueError("Unsupported document-issue section fields")
    if section.get("flag", "N") != "N":
        raise ValueError("Changed or deleted document-issue sections require separate resolution")
    checksum = section.get("chksum")
    if checksum is not None and (not isinstance(checksum, str) or len(checksum) > 200):
        raise ValueError("Invalid document-issue checksum")
    groups = section.get("doc_det")
    if not isinstance(groups, list) or not 1 <= len(groups) <= 999:
        raise ValueError("Retain explicit document categories; absence is not zero")
    rows, categories = [], set()
    for group in groups:
        if not isinstance(group, dict) or set(group) != {"doc_num", "docs"}:
            raise ValueError("Unsupported document category fields")
        category = integer(group["doc_num"])
        if category in categories:
            raise ValueError("Duplicate document category")
        categories.add(category)
        documents = group["docs"]
        if not isinstance(documents, list) or not 1 <= len(documents) <= 5000:
            raise ValueError("Each reported category requires explicit bounded serial rows")
        numbers = set()
        for document in documents:
            if not isinstance(document, dict) or set(document) != {
                "num",
                "from",
                "to",
                "totnum",
                "cancel",
                "net_issue",
            }:
                raise ValueError("Unsupported document-series fields")
            number = integer(document["num"])
            if not 1 <= number <= 5000 or number in numbers:
                raise ValueError("Duplicate or invalid document-series row number")
            numbers.add(number)
            row = DocumentSeries(
                id=f"DOCISS-{category}-{number}",
                registration=data.gst_registration,
                period=data.gst_period,
                doc_num=category,
                serial_from=document["from"],
                serial_to=document["to"],
                issued=document["totnum"],
                cancelled=document["cancel"],
                net_issued=document["net_issue"],
            ).model_dump(mode="json")
            rows.append({**row, "source_sequence_number": number})
            if len(rows) > 5000:
                raise ValueError("Document series exceed 5,000 retained ranges")
    totals = verify_controls(rows, data.document_series_controls)
    return rows, {
        "registration": data.gst_registration,
        "return_period": data.gst_period,
        "count_controls": totals,
        "source_checksum": checksum,
        "transparent_wrapper_depth": depth,
        "context_evidence_version_id": str(data.gstr1_context_evidence_version_id),
        "retrieval_scope_assessment": data.gstr1_retrieval_assessment,
        "profile_reference": REFERENCE,
        "filing_status": "NOT_ESTABLISHED_BY_DOCUMENT_SERIES",
        "provider_authenticity": "NOT_VERIFIED",
        "serial_continuity": "NOT_INFERRED_FROM_ENDPOINTS",
    }


def compare(data, tables):
    if data.currency != "INR":
        raise ValueError("India document-series review requires INR scope; counts have no currency")
    populations, scopes = {}, set()
    for role, rows in tables.items():
        populations[role] = {identity(row): row for row in rows}
        if len(populations[role]) != len(rows) or not rows:
            raise ValueError("Retain unique explicit document-series rows for each role")
        for row in rows:
            scopes.add((row["registration"], row["period"]))
            year, month = map(int, row["period"].split("-"))
            if date(year, month, calendar.monthrange(year, month)[1]) > data.as_of:
                raise ValueError("Document-series period closes after the reconciliation date")
    if len(scopes) != 1:
        raise ValueError("Select one GSTIN and reporting period per document-series review")
    rows = []
    for index, key in enumerate(
        sorted(populations["books"].keys() | populations["reported"].keys()), 1
    ):
        book, reported = (populations[role].get(key) for role in ("books", "reported"))
        differences = {
            field: reported[field] - book[field] if book and reported else None for field in FIELDS
        }
        issues = (["MISSING_BOOKS"] if not book else []) + (
            ["MISSING_REPORTED"] if not reported else []
        )
        issues.extend(
            field.upper() + "_COUNT_DIFFERENCE"
            for field, value in differences.items()
            if value not in (None, 0)
        )
        rows.append(
            {
                "id": f"series-{index}",
                **dict(
                    zip(
                        ("registration", "period", "doc_num", "serial_from", "serial_to"),
                        key,
                        strict=True,
                    )
                ),
                "books_source_id": book["id"] if book else None,
                "reported_source_id": reported["id"] if reported else None,
                "books_counts": {field: book[field] for field in FIELDS} if book else None,
                "reported_counts": {field: reported[field] for field in FIELDS}
                if reported
                else None,
                "differences": differences,
                "exceptions": issues,
                "state": "EXCEPTIONS" if issues else "MATCHED",
            }
        )
    return {
        **result(
            rows,
            any(any(issue.startswith("MISSING_") for issue in row["exceptions"]) for row in rows),
            [
                "Exact retained ranges and counts are compared; serial continuity, overlapping ranges and invoice-level completeness require separate assessment",
                "Category numbers are retained without a legal nature mapping; source authenticity, filing status and whole-return completeness are not established",
                "Cancelled documents remain explicit; monetary tolerances never excuse count differences",
            ],
        ),
        "document_series_scope": dict(
            zip(("registration", "period"), next(iter(scopes)), strict=True)
        ),
        "document_series_totals": {
            role: {field: sum(row[field] for row in values.values()) for field in FIELDS}
            for role, values in populations.items()
        },
        "document_series_contract": "india-document-series/1",
        "count_unit": "DOCUMENTS",
    }
