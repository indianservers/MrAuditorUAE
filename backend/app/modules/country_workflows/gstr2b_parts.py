"""Controlled Sandbox-profile numbered responses; no provider authentication claim."""

import hashlib
import json
from copy import deepcopy
from decimal import localcontext

from app.core.json_documents import read_json_document
from app.modules.country_workflows.india_gstr2b_source import PAGINATION, SECTIONS, day, period
from app.modules.country_workflows.india_invoice_source import gstin
from app.modules.jurisdictions.packages import fingerprint

CONTRACT = "india-gstr2b-json-parts-1"


def unwrap(content, *, manifest=False):
    node = read_json_document(content)
    checksums = []
    for depth in range(5):
        if not isinstance(node, dict):
            break
        if (
            node.get("code", 200) != 200
            or str(node.get("status_cd", "1")) not in ({"1", "3"} if manifest else {"1"})
            or node.get("error")
            or node.get("errors")
        ):
            raise ValueError("GSTR-2B file is not a successful supported provider response")
        if any(
            node.get(key) not in (None, False, "", 0) for key in PAGINATION - {"fc", "file_number"}
        ):
            raise ValueError("Token/unknown pagination requires a separately qualified reader")
        if "chksum" in node:
            value = node["chksum"]
            if not isinstance(value, str) or not 1 <= len(value) <= 512:
                raise ValueError("Invalid GSTR-2B checksum metadata")
            checksums.append(value)
        if "docdata" in node or (manifest and "fc" in node):
            if "data" in node:
                raise ValueError("Competing GSTR-2B file payloads")
            return node, checksums, depth
        if node.get("fc") not in (None, 0) or node.get("file_number") not in (None, 0):
            raise ValueError("Numbered-file metadata must belong to the selected document payload")
        node = node.get("data")
    raise ValueError("Select a supported GSTR-2B manifest or document response")


def encoded(document):
    value = json.dumps(document, default=str, separators=(",", ":")).encode()
    if len(value) > 10 * 1024 * 1024:
        raise ValueError("Combined GSTR-2B document exceeds the existing 10 MiB bound")
    return value


def row_key(row):
    return tuple(
        row[key] if key != "reference" else row[key].casefold()
        for key in (
            "source_section",
            "counterparty",
            "reference",
            "date",
            "document_type",
            "component",
        )
    )


def assemble(manifest_content, contents, data):
    from app.modules.country_workflows.native_sources import parse_native

    with localcontext() as arithmetic:
        arithmetic.prec = 80
        manifest, checksums, depth = unwrap(manifest_content, manifest=True)
        if type(manifest.get("fc")) is not int or manifest["fc"] != data.gstr2b_expected_files:
            raise ValueError(
                "Original manifest file count differs from the independent file control"
            )
        if manifest.get("docdata") not in (None, {}):
            raise ValueError(
                "A pagination manifest with inline documents cannot be silently discarded"
            )
        if (
            manifest.get("version") != "1.0"
            or gstin(manifest.get("gstin")) != data.gst_registration
            or period(manifest.get("rtnprd")) != data.gst_period
        ):
            raise ValueError(
                "Manifest version, GSTIN or return period differs from the selected scope"
            )
        generated = day(manifest.get("gendt"))
        combined = {
            key: deepcopy(value) for key, value in manifest.items() if key not in PAGINATION
        }
        combined["docdata"] = {}
        provenance, metadata = {}, []
        hashes = {hashlib.sha256(manifest_content).hexdigest()}
        for part in sorted(data.gstr2b_parts, key=lambda item: item.file_number):
            content = contents[str(part.evidence_version_id)]
            digest = hashlib.sha256(content).hexdigest()
            if digest in hashes:
                raise ValueError(
                    "Duplicate original GSTR-2B response bytes cannot establish distinct files"
                )
            hashes.add(digest)
            payload, part_checksums, _ = unwrap(content)
            if (
                payload.get("version") != manifest["version"]
                or gstin(payload.get("gstin")) != data.gst_registration
                or period(payload.get("rtnprd")) != data.gst_period
            ):
                raise ValueError("Numbered response mixes GSTR-2B scope or schema versions")
            if payload.get("gendt") is not None and day(payload["gendt"]) != generated:
                raise ValueError("Numbered responses mix GSTR-2B generation dates")
            for key, wanted in (("fc", manifest["fc"]), ("file_number", part.file_number)):
                if key in payload and (type(payload[key]) is not int or payload[key] != wanted):
                    raise ValueError(
                        "Response file numbering/count differs from its declared retrieval request"
                    )
            documents = payload.get("docdata")
            if not isinstance(documents, dict) or not set(documents) <= SECTIONS:
                raise ValueError("Unsupported numbered GSTR-2B document sections")
            chunk = {
                key: deepcopy(value)
                for key, value in payload.items()
                if key not in PAGINATION | {"cpsumm", "itcsumm"}
            }
            chunk["gendt"] = manifest["gendt"]
            options = data.model_copy(
                update={
                    "gstr2b_parts": [],
                    "gstr2b_expected_files": None,
                    "gstr2b_retrieval_assessment": "",
                    "expected_documents": part.expected_documents,
                    "expected_rows": 4 * part.expected_documents,
                    "control_totals": {"INR": part.tax_total},
                    "nil_reason": part.nil_reason,
                }
            )
            parsed = parse_native(encoded(chunk), options, "IN", "controlled-original-part.json")
            for row in parsed["rows"]:
                key = row_key(row)
                if key in provenance:
                    raise ValueError("Duplicate GSTR-2B document/component across original files")
                provenance[key] = {
                    "source_part_file_number": part.file_number,
                    "source_part_evidence_version_id": str(part.evidence_version_id),
                    "source_part_sha256": digest,
                    "source_part_row_id": row["id"],
                }
            for section, records in documents.items():
                if not isinstance(records, list):
                    raise ValueError("GSTR-2B sections must be arrays")
                combined["docdata"].setdefault(section, []).extend(deepcopy(records))
            metadata.append(
                {
                    "file_number": part.file_number,
                    "evidence_version_id": str(part.evidence_version_id),
                    "sha256": digest,
                    "request_reference": part.request_reference,
                    "document_count": part.expected_documents,
                    "signed_tax_total": str(part.tax_total),
                    "generation_date_present": payload.get("gendt") is not None,
                    "checksums": part_checksums,
                    "summary_fingerprints": {
                        key: fingerprint(json.loads(json.dumps(payload[key], default=str)))
                        for key in ("cpsumm", "itcsumm")
                        if key in payload
                    },
                }
            )
        options = data.model_copy(
            update={
                "gstr2b_parts": [],
                "gstr2b_expected_files": None,
                "gstr2b_retrieval_assessment": "",
            }
        )
        result = parse_native(
            encoded(combined), options, "IN", "controlled-assembled-document.json"
        )
        for row in result["rows"]:
            row.update(provenance[row_key(row)])
        result.update(
            parser_version=CONTRACT,
            allowed_source_roles=["return"],
            population_completeness="DECLARED_COMPLETE_NUMBERED_GSTR2B_RESPONSE_SET",
        )
        result["native_metadata"]["assembly"] = {
            "profile": CONTRACT,
            "manifest_sha256": hashlib.sha256(manifest_content).hexdigest(),
            "manifest_wrapper_depth": depth,
            "manifest_checksums": checksums,
            "expected_files": manifest["fc"],
            "parts": metadata,
            "retrieval_assessment": data.gstr2b_retrieval_assessment.strip(),
            "file_number_binding": "OPERATOR_ASSESSED_ORIGINAL_REQUEST_REFERENCES",
            "generation_binding": "PART_DATES_CHECKED_WHEN_PRESENT_OTHERWISE_MANIFEST_AND_BATCH_REVIEW",
            "part_summary_handling": "RETAINED_IN_ORIGINAL_FILES_NOT_ADDED_TO_WHOLE_MANIFEST",
        }
        result["limitations"].extend(
            [
                "File numbers are declared from original retrieval requests; provider responses do not always echo the requested index",
                "Part generation dates are checked when present; missing dates rely on explicit batch assessment and independent source review",
                "Original checksums are retained but not cryptographically verified; authenticated retrieval and ITC entitlement are not established",
            ]
        )
        return result
