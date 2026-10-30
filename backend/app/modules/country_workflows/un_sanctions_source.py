"""Controlled retained UN XML names; no identity decision or live-list authenticity claim."""

import hashlib
import re
from datetime import UTC, datetime

from defusedxml import ElementTree
from pydantic import AwareDatetime, Field, model_validator

from app.modules.jurisdictions.profiles import Strict

REFERENCE = "https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list"
CONTRACT = "un-consolidated-retained-names/1"
COUNTS = (
    "individuals",
    "entities",
    "original_script_names",
    "individual_alias_names",
    "entity_alias_names",
    "empty_alias_records",
)


class UNSanctionsControls(Strict):
    generated_at: AwareDatetime
    individuals: int = Field(ge=0, le=5000, strict=True)
    entities: int = Field(ge=0, le=5000, strict=True)
    original_script_names: int = Field(ge=0, le=5000, strict=True)
    individual_alias_names: int = Field(ge=0, le=5000, strict=True)
    entity_alias_names: int = Field(ge=0, le=5000, strict=True)
    empty_alias_records: int = Field(ge=0, le=5000, strict=True)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def population(self):
        if self.individuals + self.entities < 1 or self.name_rows > 5000:
            raise ValueError(
                "UN snapshot requires nonempty subjects and at most 5,000 retained names"
            )
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess the exact UN snapshot and independent name/subject controls")
        return self

    @property
    def name_rows(self):
        return (
            self.individuals
            + self.entities
            + self.original_script_names
            + self.individual_alias_names
            + self.entity_alias_names
        )


COMMON_FIELDS = {
    "DATAID",
    "VERSIONNUM",
    "FIRST_NAME",
    "UN_LIST_TYPE",
    "REFERENCE_NUMBER",
    "LISTED_ON",
    "NAME_ORIGINAL_SCRIPT",
    "COMMENTS1",
    "LAST_DAY_UPDATED",
    "SORT_KEY",
    "SORT_KEY_LAST_MOD",
    "LIST_TYPE",
    "HAS_INTERPOL_LINK",
    "INTERPOL_LINK",
    "LAST_REVIEWED_ON",
}
INDIVIDUAL_FIELDS = COMMON_FIELDS | {
    "SECOND_NAME",
    "THIRD_NAME",
    "FOURTH_NAME",
    "GENDER",
    "TITLE",
    "DESIGNATION",
    "NATIONALITY",
    "INDIVIDUAL_ALIAS",
    "INDIVIDUAL_ADDRESS",
    "INDIVIDUAL_DATE_OF_BIRTH",
    "INDIVIDUAL_PLACE_OF_BIRTH",
    "INDIVIDUAL_DOCUMENT",
}
ENTITY_FIELDS = COMMON_FIELDS | {"ENTITY_ALIAS", "ENTITY_ADDRESS"}
ALIAS_FIELDS = {
    "QUALITY",
    "ALIAS_NAME",
    "DATE_OF_BIRTH",
    "CITY_OF_BIRTH",
    "COUNTRY_OF_BIRTH",
    "NOTE",
}


def value(node, tag, required=False):
    children = node.findall(tag)
    if len(children) > 1 or any(len(child) for child in children):
        raise ValueError("UN named fields must be single text elements")
    text = " ".join((children[0].text or "").split()) if children else ""
    if required and not text:
        raise ValueError("UN snapshot is missing a required subject identifier or name field")
    return text


def identifying(text):
    # The issuer documents literal 'na' as not available. Never use it as an alias.
    return bool(text and text.casefold() != "na")


def parse_un_sanctions(content, data):
    from app.modules.country_workflows.diligence_schemas import SanctionsEntry
    from app.modules.country_workflows.sources import MAX_BYTES

    controls = data.un_sanctions_controls
    if controls is None or len(content) > MAX_BYTES:
        raise ValueError("UN XML requires bounded original bytes and independent snapshot controls")
    try:
        root = ElementTree.fromstring(
            content, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except Exception as exc:
        raise ValueError(
            "UN snapshot must be safe, well-formed XML without DTDs or entities"
        ) from exc
    if root.tag != "CONSOLIDATED_LIST" or set(root.attrib) - {
        "dateGenerated",
        "{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation",
    }:
        raise ValueError("Unsupported UN consolidated XML root or attributes")
    sections = {section.tag: section for section in root}
    if len(root) != 2 or set(sections) != {"INDIVIDUALS", "ENTITIES"}:
        raise ValueError("Retain exactly one individuals section and one entities section")
    generated_text = root.attrib.get("dateGenerated", "")
    try:
        generated = datetime.fromisoformat(generated_text)
        if generated.tzinfo is None or generated.utcoffset() is None:
            raise ValueError("Timezone missing")
        generated = generated.astimezone(UTC)
    except ValueError:
        raise ValueError("UN dateGenerated needs a complete timestamp with timezone") from None
    if generated != controls.generated_at:
        raise ValueError("UN snapshot timestamp differs from the independent control")
    version = "UN-SC:" + hashlib.sha256(content).hexdigest()
    counts = dict.fromkeys(COUNTS, 0)
    seen_ids, seen_references, rows = set(), set(), []
    for group, subject_tag, kind, allowed in (
        ("INDIVIDUALS", "INDIVIDUAL", "individual", INDIVIDUAL_FIELDS),
        ("ENTITIES", "ENTITY", "entity", ENTITY_FIELDS),
    ):
        for subject in sections[group]:
            if (
                subject.tag != subject_tag
                or subject.attrib
                or {child.tag for child in subject} - allowed
            ):
                raise ValueError("UN subject fields differ from the retained XML profile")
            identifier = value(subject, "DATAID", True)
            reference = value(subject, "REFERENCE_NUMBER", True)
            if not re.fullmatch(r"[1-9][0-9]{0,29}", identifier) or not re.fullmatch(
                r"[A-Z]{2}[ie]\.[0-9]{3}", reference
            ):
                raise ValueError(
                    "UN DATAID and permanent reference require the explicit profile syntax"
                )
            if identifier in seen_ids or reference in seen_references:
                raise ValueError("Duplicate UN subject DATAID or permanent reference")
            seen_ids.add(identifier)
            seen_references.add(reference)
            counts["individuals" if kind == "individual" else "entities"] += 1
            regime = value(subject, "UN_LIST_TYPE", True)

            def add(name, origin, suffix, quality=None):
                core = SanctionsEntry.model_validate(
                    {
                        "id": f"UN:{identifier}:{suffix}",
                        "list_subject_id": f"UN:{identifier}",
                        "name": name,
                        "list_version": version,
                        "published_on": generated.date(),
                        "evidence_reference": f"UN:{reference}:DATAID:{identifier}",
                    }
                ).model_dump(mode="json")
                rows.append(
                    {
                        **core,
                        "native_subject_kind": kind,
                        "native_reference_number": reference,
                        "native_regime": regime,
                        "native_name_origin": origin,
                        "native_alias_quality": quality,
                    }
                )
                if len(rows) > 5000:
                    raise ValueError(
                        "UN snapshot exceeds 5,000 retained names; no partial list is imported"
                    )

            fields = (
                ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")
                if kind == "individual"
                else ("FIRST_NAME",)
            )
            parts = [value(subject, field) for field in fields]
            primary = " ".join(part for part in parts if identifying(part))
            if not primary:
                raise ValueError(
                    "UN subject has no identifying primary name; no partial list is imported"
                )
            add(primary, "primary", "primary")
            original = value(subject, "NAME_ORIGINAL_SCRIPT")
            if identifying(original):
                add(original, "original-script", "original")
                counts["original_script_names"] += 1
            alias_tag = "INDIVIDUAL_ALIAS" if kind == "individual" else "ENTITY_ALIAS"
            for ordinal, alias in enumerate(subject.findall(alias_tag), 1):
                if alias.attrib or {child.tag for child in alias} - ALIAS_FIELDS:
                    raise ValueError("Unsupported UN alias fields")
                name = value(alias, "ALIAS_NAME")
                if not identifying(name):
                    counts["empty_alias_records"] += 1
                    continue
                quality = value(alias, "QUALITY")
                if quality not in (
                    {"", "Good", "Low"} if kind == "individual" else {"", "a.k.a.", "f.k.a."}
                ):
                    raise ValueError(
                        "Unsupported UN alias quality; retain the original for assessment"
                    )
                add(name, kind + "-alias", f"alias:{ordinal}", quality or None)
                counts[
                    "individual_alias_names" if kind == "individual" else "entity_alias_names"
                ] += 1
    if (
        any(counts[key] != getattr(controls, key) for key in COUNTS)
        or len(rows) != data.expected_rows
    ):
        raise ValueError(
            "Independent UN subject, script, alias and non-identifying-record controls do not agree"
        )
    return rows, {
        "contract": CONTRACT,
        "issuer": "UN Security Council",
        "source": REFERENCE,
        "generated_at": generated_text,
        "list_version": version,
        "counts": counts,
        "controls": controls.model_dump(mode="json"),
        "freshness_date_basis": "XML_GENERATED_UTC_DATE_NOT_DESIGNATION_DATE",
        "authenticity": "UPLOADED_SNAPSHOT_NOT_AUTHENTICATED",
        "identity_or_legal_clearance": "NOT_DETERMINED",
        "limitations": [
            "All nonempty identifying names are retained, including duplicate spellings and low-quality aliases; blank/literal na alias records are counted separately",
            "Alias quality and original script remain source observations, not identity conclusions; low-quality aliases alone are insufficient for positive identification",
            "Birth, document and address evidence remains in the original XML; this profile does not compare those identifiers",
            "A generated timestamp does not establish current issuer completeness, authenticity, domestic implementation, PEP status or registry verification",
        ],
    }
