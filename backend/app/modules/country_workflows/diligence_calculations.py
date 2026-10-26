import unicodedata
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

from app.modules.country_workflows.adverse_media import compare as media_review
from app.modules.country_workflows.audit_calculations import result


def kyc(data, tables, country):
    rows = []
    blocked = False
    for subject in tables["subjects"]:
        if date.fromisoformat(subject["reviewed_on"]) > data.as_of:
            raise ValueError("KYC evidence review is after the audit date")
        exceptions = []
        if not subject["identity_verified"]:
            exceptions.append("IDENTITY_NOT_VERIFIED")
        if date.fromisoformat(subject["identity_expires"]) < data.as_of:
            exceptions.append("IDENTITY_EXPIRED")
        if date.fromisoformat(subject["review_due"]) < data.as_of:
            exceptions.append("PERIODIC_REVIEW_OVERDUE")
        enhanced = subject["risk"] == "high" or subject["pep"]
        if enhanced:
            for field in (
                "source_of_funds_evidence",
                "source_of_wealth_evidence",
                "senior_approval_evidence",
            ):
                if not subject[field]:
                    exceptions.append("MISSING_" + field.upper())
        blocked |= bool(exceptions)
        rows.append(
            {
                "id": subject["id"],
                "risk": subject["risk"],
                "enhanced_diligence_required": enhanced,
                "exceptions": exceptions,
                "state": "EVIDENCE_GAPS" if exceptions else "MATCHED",
            }
        )
    return result(
        rows,
        blocked,
        [
            "Risk/PEP classifications and identity verification are supplied professional evidence, not model or registry determinations",
            "This checks evidence readiness; it does not approve onboarding, identity authenticity or AML compliance",
        ],
    )


def ownership(data, tables, country):
    from app.modules.country_workflows.ownership_paths import compare

    return compare(data, tables, country)


def normalized_name(value):
    return " ".join(
        "".join(
            c if c.isalnum() else " " for c in unicodedata.normalize("NFKC", value).casefold()
        ).split()
    )


def sanctions(data, tables, country):
    if len(tables["policy"]) != 1:
        return result([{"id": "policy", "state": "SCREENING_POLICY_MISSING_OR_AMBIGUOUS"}], True)
    policy = tables["policy"][0]
    if not tables["list"]:
        return result([{"id": "list", "state": "SCREENING_LIST_UNAVAILABLE"}], True)
    if len(tables["subjects"]) * len(tables["list"]) > 100000:
        raise ValueError(
            "Name-screening comparison bound exceeded; partition the declared population"
        )
    for entry in tables["list"]:
        age = (data.as_of - date.fromisoformat(entry["published_on"])).days
        if (
            entry["list_version"] != policy["list_version"]
            or not 0 <= age <= policy["maximum_list_age_days"]
        ):
            return result([{"id": "list", "state": "SCREENING_LIST_STALE_OR_WRONG_VERSION"}], True)
        if not normalized_name(entry["name"]):
            raise ValueError("Sanctions entry has no usable name characters")
    rows = []
    for subject in tables["subjects"]:
        name = normalized_name(subject["name"])
        if not name:
            raise ValueError("Screening subject has no usable name characters")
        hits = []
        for entry in tables["list"]:
            score = SequenceMatcher(
                None, name, normalized_name(entry["name"]), autojunk=False
            ).ratio()
            if Decimal(str(score)) >= Decimal(policy["minimum_similarity"]):
                hits.append(
                    {
                        "source_id": entry["id"],
                        "list_subject_id": entry["list_subject_id"],
                        "list_name": entry["name"],
                        "list_version": entry["list_version"],
                        "published_on": entry["published_on"],
                        "evidence_reference": entry["evidence_reference"],
                        "name_similarity": score,
                    }
                )
        hits.sort(key=lambda h: (-h["name_similarity"], h["source_id"]))
        rows.append(
            {
                "id": subject["id"],
                "subject_name": subject["name"],
                "subject_evidence_reference": subject["evidence_reference"],
                "execution_mode": "rules_baseline",
                "list_version": policy["list_version"],
                "candidate_count": len(hits),
                "candidates": hits,
                "candidate_preview_truncated": False,
                "state": "POTENTIAL_NAME_MATCH" if hits else "NO_NAME_MATCH_REQUIRES_REVIEW",
                "reviewer_disposition": "UNREVIEWED",
            }
        )
    return {
        **result(
            rows,
            limitations=[
                "Explicit Unicode name-similarity baseline, not a trained model, licensed live screening service, probability or sanctions clearance",
                "List completeness/authenticity, transliteration, aliases, identifiers and threshold quality need independent qualification",
                "Every result requires adjudication; no customer is automatically cleared or rejected",
            ],
        ),
        "screening_execution_mode": "rules_baseline",
        "candidate_retention_contract": "complete-screening-candidates/1",
        "feature_version": "unicode-name-ratio/1",
    }


DILIGENCE_CALCULATORS = {
    "adverse-media-review": media_review,
    "kyc-edd-review": kyc,
    "ownership-lookthrough": ownership,
    "sanctions-name-review": sanctions,
}
