"""Reviewed duty and declared-plan coverage, never an ICFR effectiveness opinion."""

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.jurisdictions.profiles import Strict

Identifier = Annotated[str, Field(min_length=1, max_length=120)]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
CONTRACT = "assessed-icfr-duty-coverage/1"
BINDING = "RETAINED_DOCUMENT_BYTES_VERIFIED"
DUTIES = {"404a": "Management assessment", "404b": "Auditor attestation"}
ROLES = {"scopes": "icfr-duty-scopes", "checks": "checks"}


class ICFRScope(Strict):
    id: Identifier
    subject: Identifier
    engagement_country: Literal["AE", "IN"]
    reporting_issuer: Identifier
    relationship: Literal["issuer", "component"]
    duty: Literal["404a", "404b"]
    applicability: Literal["required", "not-required", "unresolved"]
    period_start: date
    period_end: date
    adoption_status: Literal["reviewed-for-period", "pending"]
    effective_from: date
    effective_to: date
    authority_version: Identifier
    authority_url: str = Field(pattern=r"^https://[^\s]+$", max_length=1000)
    authority_evidence_version_id: UUID
    authority_sha256: Hash
    assessment_evidence_version_id: UUID
    assessment_sha256: Hash
    assessment: str = Field(min_length=20, max_length=2000)

    @field_validator("id", "subject", "reporting_issuer", "authority_version")
    @classmethod
    def exact_identity(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Retain exact nonblank ICFR scope identifiers")
        return value

    @model_validator(mode="after")
    def ordered(self):
        if self.period_end < self.period_start or self.effective_to < self.effective_from:
            raise ValueError("ICFR review and adopted authority windows must be ordered")
        if len(self.assessment.strip()) < 20:
            raise ValueError("Retain a meaningful independent applicability and method assessment")
        if (
            self.authority_evidence_version_id == self.assessment_evidence_version_id
            or self.authority_sha256 == self.assessment_sha256
        ):
            raise ValueError("Retain authority and company/group scope assessment separately")
        return self


ROW_TYPES: dict[str, type[BaseModel]] = {"icfr-duty-scopes": ICFRScope}


def documents(rows):
    return [
        {
            "source_evidence_version_id": row[f"{role}_evidence_version_id"],
            "source_sha256": row[f"{role}_sha256"],
        }
        for row in rows
        for role in ("authority", "assessment")
    ]


def duty_for(requirement):
    duty, separator, point = requirement.partition(":")
    if duty not in DUTIES or not separator or not point.strip() or point != point.strip():
        raise ValueError("ICFR plan/check references must use 404a:<point> or 404b:<point>")
    return duty


def compare(data, tables, country):
    subjects = set(data.subjects)
    if not subjects or data.period_start is None:
        raise ValueError("Declare ICFR subjects and an exact ordered review period")
    plans: dict[str, list[str]] = {duty: [] for duty in DUTIES}
    for requirement in data.required_checks:
        plans[duty_for(requirement)].append(requirement)
    scopes: dict[tuple[str, str], dict[str, Any]] = {}
    identities: dict[str, tuple[str, str]] = {}
    checks: dict[tuple[str, str], dict[str, Any]] = {}
    for row in tables["scopes"]:
        if row["subject"] not in subjects or row["engagement_country"] != country:
            raise ValueError("ICFR scope lies outside the declared subject/country population")
        if (
            row["period_start"] != data.period_start.isoformat()
            or row["period_end"] != data.as_of.isoformat()
        ):
            raise ValueError("ICFR scope period must equal the declared review period")
        key = row["subject"], row["duty"]
        if key in scopes:
            raise ValueError("Duplicate ICFR subject/duty decisions cannot be combined")
        identity = row["reporting_issuer"], row["relationship"]
        if row["subject"] in identities and identities[row["subject"]] != identity:
            raise ValueError("Reporting issuer or component relationship conflicts between duties")
        identities[row["subject"]] = identity
        scopes[key] = row
    for row in tables["checks"]:
        duty_for(row["requirement"])
        if row["subject"] not in subjects:
            raise ValueError("ICFR check lies outside the declared subject population")
        key = row["subject"], row["requirement"]
        if key in checks:
            raise ValueError("Duplicate ICFR check observations cannot be combined")
        checks[key] = row
    rows: list[dict[str, Any]] = []
    for subject in sorted(subjects):
        for duty, title in DUTIES.items():
            scope = scopes.get((subject, duty))
            state = "SUPPORTED"
            if not scope:
                state = "MISSING_SCOPE_DECISION"
            elif scope["adoption_status"] != "reviewed-for-period":
                state = "PENDING_AUTHORITY_ADOPTION"
            elif (
                not date.fromisoformat(scope["effective_from"])
                <= data.period_start
                <= data.as_of
                <= date.fromisoformat(scope["effective_to"])
            ):
                state = "AUTHORITY_WINDOW_NOT_COVERED"
            elif scope["applicability"] == "unresolved":
                state = "PENDING_APPLICABILITY"
            elif scope["applicability"] == "not-required":
                state = "NOT-APPLICABLE"
            elif not plans[duty]:
                state = "MISSING_DUTY_PLAN"
            rows.append(
                {
                    "id": f"icfr-scope:{len(rows) + 1}",
                    "kind": "scope-decision",
                    "subject": subject,
                    "duty": duty,
                    "duty_title": title,
                    "reporting_issuer": scope["reporting_issuer"] if scope else None,
                    "relationship": scope["relationship"] if scope else None,
                    "assessed_applicability": scope["applicability"] if scope else None,
                    "scope_source_row_id": scope["id"] if scope else None,
                    "authority_version": scope["authority_version"] if scope else None,
                    "authority_url": scope["authority_url"] if scope else None,
                    "authority_evidence_version_id": scope["authority_evidence_version_id"]
                    if scope
                    else None,
                    "assessment_evidence_version_id": scope["assessment_evidence_version_id"]
                    if scope
                    else None,
                    "adoption_status": scope["adoption_status"] if scope else None,
                    "effective_from": scope["effective_from"] if scope else None,
                    "effective_to": scope["effective_to"] if scope else None,
                    "assessment": scope["assessment"] if scope else None,
                    "state": state,
                }
            )
            for requirement in plans[duty]:
                check = checks.get((subject, requirement))
                if check is None:
                    status = "NOT-APPLICABLE" if state == "NOT-APPLICABLE" else "MISSING"
                elif (
                    check.get("expires_on") and date.fromisoformat(check["expires_on"]) < data.as_of
                ):
                    status = "EXPIRED"
                elif check["state"] == "missing":
                    status = "MISSING"
                elif (
                    not check["evidence_reference"].strip() or len(check["rationale"].strip()) < 10
                ):
                    status = "EVIDENCE_OR_ASSESSMENT_MISSING"
                else:
                    status = check["state"].upper()
                rows.append(
                    {
                        "id": f"icfr-point:{len(rows) + 1}",
                        "kind": "declared-plan-point",
                        "subject": subject,
                        "duty": duty,
                        "requirement": requirement,
                        "scope_source_row_id": scope["id"] if scope else None,
                        "check_source_row_id": check["id"] if check else None,
                        "evidence_reference": check["evidence_reference"] if check else None,
                        "assessment": check["rationale"] if check else None,
                        "state": status,
                    }
                )
    for (subject, requirement), check in checks.items():
        if requirement not in data.required_checks:
            rows.append(
                {
                    "id": "unplanned:" + check["id"],
                    "kind": "unplanned-evidence",
                    "subject": subject,
                    "duty": duty_for(requirement),
                    "requirement": requirement,
                    "check_source_row_id": check["id"],
                    "retained_state": check["state"],
                    "state": "UNPLANNED_EVIDENCE",
                }
            )
    good = {"SUPPORTED", "NOT-APPLICABLE"}
    return {
        "rows": rows,
        "exception_count": sum(row["state"] not in good for row in rows),
        "blocked": any(row["state"] not in good | {"EXCEPTION"} for row in rows),
        "icfr_scope_contract": CONTRACT,
        "icfr_scope_population": "DECLARED_SUBJECTS_DUTIES_AND_PLAN_POINTS_ONLY",
        "effectiveness_conclusion": "NOT_DETERMINED",
        "limitations": [
            "404(a) management and 404(b) auditor scope are separately assessed inputs; an exemption for one does not clear the other",
            "Entity country does not determine US reporting status; issuer/component relationships and adopted windows need independent professional assessment",
            "Component coverage under group instructions does not establish a separate statutory auditor-attestation duty for that component",
            "Declared plan completeness and supported evidence references do not establish control design or operating effectiveness, a signed opinion or a complete SOX/AS2201 method",
            "Local India IFC and UAE duties remain separate workflows; this review does not replace them",
        ],
    }
