"""Retained GSTR-1 summary metrics; overlapping hierarchy levels never net."""

import calendar
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.core.json_documents import read_json_document
from app.modules.jurisdictions.profiles import Strict

REFERENCE = "https://developer.sandbox.co.in/api-reference/gst/compliance/endpoints/taxpayer/gstr-1/documents/gstr_1"
COUNTS = {"ttl_rec", "net_doc_issued", "ttl_doc_cancelled", "ttl_doc_issued"}
METRICS = COUNTS | {
    "ttl_cess",
    "ttl_cgst",
    "ttl_igst",
    "ttl_sgst",
    "ttl_tax",
    "ttl_val",
    "ttl_expt_amt",
    "ttl_ngsup_amt",
    "ttl_nilsup_amt",
    "act_cess",
    "act_cgst",
    "act_igst",
    "act_sgst",
    "act_tax",
    "act_val",
}
Value = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Code = Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,60}$")]


class GSTSummaryMetric(Strict):
    id: str = Field(min_length=1, max_length=120)
    registration: str = Field(pattern=r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]$")
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    section: Code
    sub_section: str = Field(default="", max_length=60)
    nature: str = Field(default="", max_length=40)
    counterparty: str = Field(default="", max_length=15)
    state_code: str = Field(default="", max_length=2)
    metric: str = Field(min_length=1, max_length=40)
    unit: Literal["INR", "COUNT"]
    value: Value

    @model_validator(mode="after")
    def metric_scope(self):
        datetime.strptime(self.period, "%Y-%m")
        if self.nature and not self.sub_section:
            raise ValueError("GST summary nature requires its original subsection scope")
        if self.metric not in METRICS or self.unit != ("COUNT" if self.metric in COUNTS else "INR"):
            raise ValueError("Select a documented GST summary metric and its exact unit")
        if self.metric in COUNTS and (
            self.value < 0 or self.value != self.value.to_integral_value()
        ):
            raise ValueError("GST summary record/document counts must be non-negative integers")
        if any(
            value and not re.fullmatch(r"[A-Z0-9_]{1,60}", value)
            for value in (self.sub_section, self.nature)
        ):
            raise ValueError("Invalid GST summary subsection or nature")
        if self.counterparty and not re.fullmatch(r"[A-Z0-9]{15}", self.counterparty):
            raise ValueError("Invalid GST summary counterparty identifier")
        if self.state_code and not re.fullmatch(r"\d{2}", self.state_code):
            raise ValueError("Invalid GST summary state code")
        return self


def identity(row):
    return tuple(
        row.get(field, "")
        for field in (
            "registration",
            "period",
            "section",
            "sub_section",
            "nature",
            "counterparty",
            "state_code",
            "metric",
            "unit",
        )
    )


def verify_controls(rows, controls):
    totals: dict[str, Decimal] = defaultdict(Decimal)
    seen = set()
    for row in rows:
        key = identity(row)
        if key in seen:
            raise ValueError(
                "Duplicate GST summary metric identity; observations cannot be aggregated"
            )
        seen.add(key)
        totals[row["metric"]] += Decimal(row["value"])
    if not rows or dict(totals) != controls:
        raise ValueError(
            "Declare every independent GST summary metric control; absent metrics are not zero"
        )
    return {key: str(value) for key, value in sorted(totals.items())}


def parse_summary(content, data):
    root = read_json_document(content)
    depth = 0
    while isinstance(root, dict) and "sec_sum" not in root and "data" in root and depth < 2:
        if (
            set(root) - {"data", "code", "status_cd", "timestamp", "transaction_id"}
            or ("code" in root and root["code"] != 200)
            or ("status_cd" in root and root["status_cd"] != "1")
        ):
            raise ValueError("Unsupported or unsuccessful GSTR-1 summary response wrapper")
        root = root["data"]
        depth += 1
    if not isinstance(root, dict) or set(root) - {
        "chksum",
        "gstin",
        "newSumFlag",
        "ret_period",
        "sec_sum",
        "smryTyp",
    }:
        raise ValueError(
            "Unsupported GSTR-1 summary payload; retain the complete original response"
        )
    if (
        not data.gst_registration
        or root.get("gstin") != data.gst_registration
        or not data.gst_period
    ):
        raise ValueError("GSTR-1 summary must agree to the selected GSTIN and period")
    if root.get("ret_period") != data.gst_period[5:] + data.gst_period[:4]:
        raise ValueError("GSTR-1 summary reporting period differs from the selected month")
    if "chksum" in root and (not isinstance(root["chksum"], str) or len(root["chksum"]) > 200):
        raise ValueError("Invalid root GST summary checksum")
    if "newSumFlag" in root and not isinstance(root["newSumFlag"], bool):
        raise ValueError("Invalid GSTR-1 summary generation flag")
    if "smryTyp" in root and (not isinstance(root["smryTyp"], str) or len(root["smryTyp"]) > 40):
        raise ValueError("Invalid GSTR-1 summary type")
    rows: list[dict] = []
    nodes: set[tuple] = set()
    checksums: list[dict] = []

    def walk(population, section="", sub_section="", nature="", kind="section"):
        if not isinstance(population, list) or len(population) > 1000:
            raise ValueError("GST summary hierarchy must use bounded arrays")
        for node in population:
            if not isinstance(node, dict):
                raise ValueError("Malformed GST summary node")
            allowed = METRICS | {
                "chksum",
                "sec_nm",
                "sub_sections",
                "cpty_sum",
                "typ",
                "ctin",
                "state_cd",
            }
            if set(node) - allowed:
                raise ValueError("Unknown GST summary metric or hierarchy field")
            if kind == "section":
                if "typ" in node or "ctin" in node or "state_cd" in node:
                    raise ValueError("Unsupported section-level GST summary dimensions")
                section, sub_section, nature = node.get("sec_nm"), "", ""
            elif kind == "subsection":
                if "ctin" in node or "state_cd" in node:
                    raise ValueError("Counterparty dimensions require a counterparty node")
                sub_section, nature = node.get("sec_nm"), node.get("typ", "")
            elif (
                "sec_nm" in node or "typ" in node or not (node.get("ctin") or node.get("state_cd"))
            ):
                raise ValueError("Counterparty summary requires its own CTIN or state identity")
            if (
                kind != "section"
                and "sub_sections" in node
                or kind == "counterparty"
                and "cpty_sum" in node
            ):
                raise ValueError("Unsupported GST summary hierarchy depth")
            dimensions = {
                "registration": data.gst_registration,
                "period": data.gst_period,
                "section": section,
                "sub_section": sub_section,
                "nature": nature,
                "counterparty": node.get("ctin", ""),
                "state_code": node.get("state_cd", ""),
            }
            GSTSummaryMetric(id="CHECK", **dimensions, metric="ttl_rec", unit="COUNT", value=0)
            key = tuple(dimensions.values())
            if key in nodes:
                raise ValueError("Duplicate GST summary hierarchy node")
            nodes.add(key)
            if len(nodes) > 5000:
                raise ValueError("GST summary exceeds its node bound")
            values = set(node) & METRICS
            if not values:
                raise ValueError("GST summary node contains no explicit metric values")
            for metric in sorted(values):
                value = node[metric]
                if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
                    raise ValueError("Native GST summary values must be JSON numbers")
                row = GSTSummaryMetric(
                    id=f"GST1-{len(rows) + 1}",
                    **dimensions,
                    metric=metric,
                    unit="COUNT" if metric in COUNTS else "INR",
                    value=value,
                ).model_dump(mode="json")
                rows.append(row)
                if len(rows) > 5000:
                    raise ValueError("GST summary exceeds 5,000 metric rows")
            if "chksum" in node:
                if not isinstance(node["chksum"], str) or len(node["chksum"]) > 200:
                    raise ValueError("Invalid GST summary checksum")
                checksums.append({**dimensions, "checksum": node["chksum"]})
            if "sub_sections" in node:
                walk(node["sub_sections"], section, kind="subsection")
            if "cpty_sum" in node:
                walk(node["cpty_sum"], section, sub_section, nature, "counterparty")

    walk(root.get("sec_sum"))
    controls = verify_controls(rows, data.gst_summary_metric_controls)
    return rows, {
        "currency": "INR",
        "registration": data.gst_registration,
        "return_period": data.gst_period,
        "source_checksum": root.get("chksum"),
        "generation_flag": root.get("newSumFlag"),
        "summary_type": root.get("smryTyp"),
        "transparent_wrapper_depth": depth,
        "node_checksums": checksums,
        "metric_controls": controls,
        "profile_reference": REFERENCE,
        "filing_status": "NOT_ESTABLISHED_BY_SUMMARY",
        "provider_authenticity": "NOT_VERIFIED",
        "control_basis": "ARITHMETIC_SUM_BY_METRIC_ACROSS_RETAINED_HIERARCHY_NOT_RETURN_LIABILITY",
    }


def compare_summary(data, tables):
    if data.currency != "INR":
        raise ValueError("GST summary comparison requires INR; counts remain a separate unit")
    populations = {}
    for role, rows in tables.items():
        populations[role] = {identity(row): row for row in rows}
        if len(populations[role]) != len(rows) or not rows:
            raise ValueError("GST summaries require nonempty unique explicit metric populations")
        for row in rows:
            when = datetime.strptime(row["period"], "%Y-%m").date()
            if when.replace(day=calendar.monthrange(when.year, when.month)[1]) > data.as_of:
                raise ValueError("GST summary period extends beyond the reconciliation date")
    rows = []
    for key in sorted(set(populations["books"]) | set(populations["return"])):
        left, right = (populations[role].get(key) for role in ("books", "return"))
        delta = Decimal(left["value"]) - Decimal(right["value"]) if left and right else None
        state = (
            "BOOKS_ONLY"
            if not right
            else "RETURN_ONLY"
            if not left
            else "MATCHED"
            if delta == 0
            else "VARIANCE"
        )
        sample = left or right
        assert sample is not None
        rows.append(
            {
                **{
                    field: sample[field]
                    for field in (
                        "registration",
                        "period",
                        "section",
                        "sub_section",
                        "nature",
                        "counterparty",
                        "state_code",
                        "metric",
                        "unit",
                    )
                },
                "books_id": left["id"] if left else None,
                "return_id": right["id"] if right else None,
                "books_value": left["value"] if left else None,
                "return_value": right["value"] if right else None,
                "difference": str(delta) if delta is not None else None,
                "state": state,
            }
        )
    return {
        "rows": rows,
        "exception_count": sum(row["state"] != "MATCHED" for row in rows),
        "blocked": any(row["state"] in {"BOOKS_ONLY", "RETURN_ONLY"} for row in rows),
        "totals": {},
        "limitations": [
            "Summary metrics preserve overlapping parent/subsection/counterparty levels and are never summed into tax liability",
            "Missing fields are not zero; record counts and INR values remain separate and comparison is exact",
            "Retained summary comparison does not establish filing, invoice completeness, tax eligibility or provider authenticity",
            "Invoice-level GSTR-1 matching, legal assessment and current portal qualification remain separate procedures",
        ],
    }
