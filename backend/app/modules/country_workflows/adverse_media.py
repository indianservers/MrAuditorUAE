"""Retained search coverage and human identity adjudication; never media clearance."""

from collections import defaultdict
from datetime import date
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.modules.country_workflows.audit_calculations import result
from app.modules.country_workflows.grant_utilisation import ID, Day, Exact, Hash
from app.modules.jurisdictions.profiles import Strict


class MediaSubject(Exact):
    id: ID
    name: str = Field(min_length=1, max_length=200)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    identifiers: str = Field(min_length=10, max_length=2000)
    source_evidence_version_id: UUID
    source_sha256: Hash
    assessment: str = Field(min_length=10, max_length=2000)


class MediaSearch(Exact):
    id: ID
    subject_id: ID
    provider: ID
    query: str = Field(min_length=1, max_length=2000)
    aliases_and_identifiers: str = Field(min_length=10, max_length=2000)
    queried_on: Day
    coverage_from: Day
    coverage_through: Day
    status: Literal["completed", "partial", "unavailable"]
    expected_mentions: int = Field(ge=0, le=5000, strict=True)
    licence_reference: ID
    source_evidence_version_id: UUID
    source_sha256: Hash
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("expected_mentions", mode="before")
    @classmethod
    def exact_count(cls, value):
        import re

        return (
            int(value)
            if isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]*", value)
            else value
        )

    @model_validator(mode="after")
    def ordered(self):
        if not self.coverage_from <= self.coverage_through <= self.queried_on:
            raise ValueError("Media coverage dates must be ordered and end by the query date")
        return self


class MediaMention(Exact):
    id: ID
    search_id: ID
    article_id: ID
    publisher: ID
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=2000)
    published_on: Day | None = None
    retrieved_on: Day
    identity_status: Literal["unassessed", "unresolved", "same-subject", "different-subject"]
    identity_rationale: str = Field(min_length=10, max_length=2000)
    identity_evidence_version_id: UUID | None = None
    identity_source_sha256: Hash | None = None
    reported_stage: Literal["unknown", "allegation", "charge", "conviction", "retracted"]
    risk: Literal["not-assessed", "low", "medium", "high"]
    risk_rationale: str = Field(min_length=10, max_length=2000)
    disposition: Literal["pending", "monitor", "escalate", "no-action"]
    reviewed_on: Day
    followup_on: Day | None = None
    source_evidence_version_id: UUID
    source_sha256: Hash

    @model_validator(mode="after")
    def support(self):
        parsed = urlsplit(self.url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Media references require an explicit HTTP(S) URL without credentials")
        if self.published_on and self.published_on > self.retrieved_on:
            raise ValueError("Article publication cannot follow retrieval")
        if any(character.isspace() for character in self.url):
            raise ValueError("Media URLs cannot contain whitespace")
        if self.followup_on and self.followup_on < self.reviewed_on:
            raise ValueError("Media follow-up cannot precede the recorded review")
        if self.reviewed_on < self.retrieved_on:
            raise ValueError("Identity review cannot precede article retrieval")
        if bool(self.identity_evidence_version_id) != bool(self.identity_source_sha256):
            raise ValueError("Identity evidence requires both file-version ID and hash")
        if (
            self.identity_status in {"same-subject", "different-subject"}
            and not self.identity_evidence_version_id
        ):
            raise ValueError("Concluded identity assessments require retained supporting evidence")
        return self


class MediaPolicy(Exact):
    id: ID
    country: str = Field(pattern=r"^[A-Z]{2}$")
    effective_from: Day
    effective_to: Day
    coverage_from: Day
    coverage_through: Day
    maximum_query_age_days: int = Field(ge=0, le=3650)
    expected_subjects: int = Field(ge=1, le=5000)
    source_evidence_version_id: UUID
    source_sha256: Hash
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("maximum_query_age_days", "expected_subjects", mode="before")
    @classmethod
    def explicit_integer(cls, value):
        converted = MediaSearch.exact_count(value)
        if type(converted) is not int:
            raise ValueError("Media policy controls require explicit integers")
        return converted

    @model_validator(mode="after")
    def ordered(self):
        if self.effective_to < self.effective_from or self.coverage_through < self.coverage_from:
            raise ValueError("Media policy validity and coverage windows must be ordered")
        return self


ROW_TYPES: dict[str, type[Strict]] = {
    "media-subjects": MediaSubject,
    "media-searches": MediaSearch,
    "media-mentions": MediaMention,
    "media-policies": MediaPolicy,
}
ROLES = dict(
    subjects="media-subjects",
    searches="media-searches",
    mentions="media-mentions",
    policy="media-policies",
)


def documents(rows):
    bindings = []
    for row in rows:
        bindings.append({key: row[key] for key in ("source_evidence_version_id", "source_sha256")})
        if row.get("identity_evidence_version_id"):
            bindings.append(
                dict(
                    source_evidence_version_id=row["identity_evidence_version_id"],
                    source_sha256=row["identity_source_sha256"],
                )
            )
    return bindings


def compare(data, tables, country):
    for role in ROLES:
        rows = tables[role]
        if len(rows) > 5000 or len({row["id"] for row in rows}) != len(rows):
            raise ValueError("Media source rows require unique IDs within the 5,000-row bound")
    if len(tables["policy"]) != 1:
        raise ValueError("Exactly one independently reviewed media policy is required")
    policy = tables["policy"][0]
    as_of = data.as_of.isoformat()
    if (
        policy["country"] != country
        or not policy["effective_from"] <= as_of <= policy["effective_to"]
    ):
        raise ValueError("Media policy must apply to the selected country and review date")
    if policy["coverage_through"] > as_of:
        raise ValueError("Media policy coverage cannot extend beyond review date")
    subjects = {row["id"]: row for row in tables["subjects"]}
    searches = {row["id"]: row for row in tables["searches"]}
    rows = []
    blocked = len(subjects) != policy["expected_subjects"]
    rows.append(
        dict(
            id="population",
            kind="population-control",
            observed_subjects=len(subjects),
            expected_subjects=policy["expected_subjects"],
            state="MATCHED" if not blocked else "SUBJECT_POPULATION_GAP",
        )
    )
    by_search = defaultdict(list)
    by_subject = defaultdict(list)
    seen = set()
    seen_urls = set()
    for mention in tables["mentions"]:
        identity = (mention["search_id"], mention["article_id"])
        url_identity = (mention["search_id"], mention["url"])
        if identity in seen or url_identity in seen_urls:
            raise ValueError("An article can appear only once within a declared media search")
        seen.add(identity)
        seen_urls.add(url_identity)
        by_search[mention["search_id"]].append(mention)
        search = searches.get(mention["search_id"])
        reasons = []
        if search is None:
            reasons.append("UNKNOWN_SEARCH")
        else:
            if mention["published_on"] is None:
                reasons.append("PUBLICATION_DATE_UNKNOWN")
            elif (
                not search["coverage_from"] <= mention["published_on"] <= search["coverage_through"]
            ):
                reasons.append("ARTICLE_OUTSIDE_DECLARED_COVERAGE")
            if mention["retrieved_on"] > search["queried_on"]:
                reasons.append("ARTICLE_RETRIEVED_AFTER_SEARCH")
        if mention["reviewed_on"] > as_of:
            reasons.append("REVIEW_AFTER_AS_OF")
        if mention["identity_status"] in {"unassessed", "unresolved"}:
            reasons.append("IDENTITY_UNRESOLVED")
        if mention["risk"] == "not-assessed":
            reasons.append("RISK_ASSESSMENT_MISSING")
        if mention["disposition"] == "pending":
            reasons.append("DISPOSITION_PENDING")
        if (
            mention["identity_status"] == "different-subject"
            and mention["disposition"] != "no-action"
        ):
            reasons.append("IDENTITY_DISPOSITION_CONFLICT")
        if mention["disposition"] in {"monitor", "escalate"} and not mention["followup_on"]:
            reasons.append("FOLLOWUP_DATE_MISSING")
        if mention["followup_on"] and mention["followup_on"] < as_of:
            reasons.append("FOLLOWUP_OVERDUE")
        blocked |= bool(reasons)
        observation = mention["identity_status"] == "same-subject"
        rows.append(
            dict(
                **{key: value for key, value in mention.items() if key != "id"},
                id="mention:" + mention["id"],
                kind="media-mention",
                subject_id=search["subject_id"] if search else None,
                reasons=reasons,
                state="MEDIA_EVIDENCE_GAP"
                if reasons
                else "ADVERSE_MENTION_REVIEW"
                if observation
                else "MATCHED",
            )
        )
    query_keys = set()
    for search in searches.values():
        query_identity = (
            search["subject_id"],
            search["provider"],
            search["query"],
            search["queried_on"],
        )
        if query_identity in query_keys:
            raise ValueError("Duplicate declared media search")
        query_keys.add(query_identity)
        reasons = []
        if search["subject_id"] not in subjects:
            reasons.append("UNKNOWN_SUBJECT")
        by_subject[search["subject_id"]].append(search)
        if search["status"] != "completed":
            reasons.append("SEARCH_" + search["status"].upper())
        if (
            not 0
            <= (data.as_of - date.fromisoformat(search["queried_on"])).days
            <= policy["maximum_query_age_days"]
        ):
            reasons.append("SEARCH_STALE_OR_FUTURE")
        if any(search[key] != policy[key] for key in ("coverage_from", "coverage_through")):
            reasons.append("SEARCH_COVERAGE_GAP")
        observed = len(by_search[search["id"]])
        if observed != search["expected_mentions"]:
            reasons.append("MENTION_COUNT_GAP")
        blocked |= bool(reasons)
        rows.append(
            dict(
                **{key: value for key, value in search.items() if key != "id"},
                id="search:" + search["id"],
                kind="search-control",
                observed_mentions=observed,
                reasons=reasons,
                state="SEARCH_EVIDENCE_GAP" if reasons else "MATCHED",
                outcome="MENTIONS_REPORTED" if observed else "NO_MENTIONS_REPORTED_NOT_CLEARANCE",
            )
        )
    for subject in subjects.values():
        found = by_subject[subject["id"]]
        blocked |= not found
        rows.append(
            dict(
                **{key: value for key, value in subject.items() if key != "id"},
                id="subject:" + subject["id"],
                kind="subject-coverage",
                search_ids=[search["id"] for search in found],
                state="MATCHED" if found else "SEARCH_MISSING",
            )
        )
    return {
        **result(
            rows,
            blocked,
            [
                "Uploaded provider/query receipts and declared search scope only; no live search, registry verification or complete internet coverage is established",
                "Name similarity never resolves identity; retained human identity and risk rationales require independent review",
                "Reported allegations, charges, convictions and retractions are source descriptions, not authenticated legal facts or guilt determinations",
                "No mentions is not clearance; unavailable, partial, stale or incomplete searches block approval",
                "Review does not authorize onboarding, rejection, attestation or regulatory reporting; follow-up is recorded but not automatically scheduled",
            ],
        ),
        "media_review_contract": "retained-adverse-media/1",
        "media_document_binding": "NOT_VERIFIED_BY_PURE_CALCULATOR",
        "media_scope": {
            key: policy[key]
            for key in (
                "country",
                "coverage_from",
                "coverage_through",
                "maximum_query_age_days",
                "expected_subjects",
                "assessment",
            )
        },
        "identity_authenticity_established": False,
        "media_clearance_issued": False,
        "automatic_rejection": False,
    }
