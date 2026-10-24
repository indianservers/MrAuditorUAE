import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

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
            for field in ("source_of_funds_evidence", "source_of_wealth_evidence", "senior_approval_evidence"):
                if not subject[field]:
                    exceptions.append("MISSING_" + field.upper())
        blocked |= bool(exceptions)
        rows.append({"id": subject["id"], "risk": subject["risk"], "enhanced_diligence_required": enhanced,
                     "exceptions": exceptions, "state": "EVIDENCE_GAPS" if exceptions else "MATCHED"})
    return result(rows, blocked, [
        "Risk/PEP classifications and identity verification are supplied professional evidence, not model or registry determinations",
        "This checks evidence readiness; it does not approve onboarding, identity authenticity or AML compliance",
    ])


def ownership(data, tables, country):
    policies = [p for p in tables["policy"] if p["country"] == country and
                date.fromisoformat(p["effective_from"]) <= data.as_of <= date.fromisoformat(p["effective_to"])]
    if len(policies) != 1:
        return result([{"id": "policy", "state": "OWNERSHIP_POLICY_MISSING_OR_AMBIGUOUS"}], True)
    policy = policies[0]
    graph = defaultdict(list)
    identities: dict[str, str] = {}
    for edge in tables["ownership"]:
        if date.fromisoformat(edge["effective_from"]) > data.as_of or (
            edge.get("effective_to") and date.fromisoformat(edge["effective_to"]) < data.as_of
        ):
            continue
        if edge["owner"] in identities and identities[edge["owner"]] != edge["owner_kind"]:
            raise ValueError("Conflicting company/person owner identity")
        identities[edge["owner"]] = edge["owner_kind"]
        graph[edge["company"]].append(edge)
    if any(identities.get(company) == "person" for company in graph):
        raise ValueError("A natural-person identity cannot also be an owned company")
    rows = []
    blocked = False
    for company in data.subjects:
        totals: defaultdict[str, Decimal] = defaultdict(Decimal)
        paths = 0
        failures = set()

        def walk(node, fraction, visited):
            nonlocal paths
            paths += 1
            if paths > 10000 or len(visited) > 20:
                raise ValueError("Ownership complexity bound exceeded; select a reviewed bounded graph")
            if node in visited:
                failures.add("OWNERSHIP_CYCLE_REQUIRES_ASSESSMENT")
                return
            edges = graph.get(node, [])
            if not edges:
                failures.add("CORPORATE_OWNER_EVIDENCE_MISSING")
                return
            total = sum((Decimal(e["fraction"]) for e in edges), Decimal(0))
            if total != 1:
                failures.add("OWNERSHIP_POPULATION_NOT_COMPLETE")
            owners = set()
            for edge in edges:
                if edge["owner"] in owners:
                    failures.add("DUPLICATE_CURRENT_OWNERSHIP_EDGE")
                    continue
                owners.add(edge["owner"])
                weight = fraction * Decimal(edge["fraction"])
                if edge["owner_kind"] == "person":
                    totals[edge["owner"]] += weight
                else:
                    walk(edge["owner"], weight, {*visited, node})

        walk(company, Decimal(1), set())
        if failures:
            blocked = True
            rows.append({"id": "company:" + company, "company": company,
                         "exceptions": sorted(failures), "state": "OWNERSHIP_EVIDENCE_GAPS"})
        for person, fraction in sorted(totals.items()):
            threshold = Decimal(policy["threshold"])
            candidate = fraction > threshold if policy["comparison"] == "greater-than" else fraction >= threshold
            rows.append({"id": company + ":" + person, "company": company, "person_id": person,
                         "economic_fraction": str(fraction), "threshold_candidate": candidate,
                         "policy_source_id": policy["id"], "state": "REQUIRES_UBO_REVIEW" if candidate else "MATCHED"})
    return result(rows, blocked, [
        "Economic ownership is multiplied along paths; voting rights, control, nominee/trust arrangements and legal UBO conclusions require separate review",
        "Threshold and comparison operator come from reviewed policy evidence; no registry verification is implied",
        "Cyclic, incomplete or ambiguous ownership blocks approval; partial paths are never a complete UBO conclusion",
    ])


def normalized_name(value):
    return " ".join("".join(c if c.isalnum() else " " for c in
                            unicodedata.normalize("NFKC", value).casefold()).split())


def sanctions(data, tables, country):
    if len(tables["policy"]) != 1:
        return result([{"id": "policy", "state": "SCREENING_POLICY_MISSING_OR_AMBIGUOUS"}], True)
    policy = tables["policy"][0]
    if not tables["list"]:
        return result([{"id": "list", "state": "SCREENING_LIST_UNAVAILABLE"}], True)
    if len(tables["subjects"]) * len(tables["list"]) > 100000:
        raise ValueError("Name-screening comparison bound exceeded; partition the declared population")
    for entry in tables["list"]:
        age = (data.as_of - date.fromisoformat(entry["published_on"])).days
        if entry["list_version"] != policy["list_version"] or not 0 <= age <= policy["maximum_list_age_days"]:
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
            score = SequenceMatcher(None, name, normalized_name(entry["name"]), autojunk=False).ratio()
            if Decimal(str(score)) >= Decimal(policy["minimum_similarity"]):
                hits.append({"source_id": entry["id"], "list_subject_id": entry["list_subject_id"],
                             "name_similarity": score})
        hits.sort(key=lambda h: (-h["name_similarity"], h["source_id"]))
        rows.append({"id": subject["id"], "execution_mode": "rules_baseline",
                     "list_version": policy["list_version"], "candidate_count": len(hits),
                     "candidates": hits[:20], "candidate_preview_truncated": len(hits) > 20,
                     "state": "POTENTIAL_NAME_MATCH" if hits else "NO_NAME_MATCH_REQUIRES_REVIEW",
                     "reviewer_disposition": "UNREVIEWED"})
    return {**result(rows, limitations=[
        "Explicit Unicode name-similarity baseline, not a trained model, licensed live screening service, probability or sanctions clearance",
        "List completeness/authenticity, transliteration, aliases, identifiers and threshold quality need independent qualification",
        "Every result requires adjudication; no customer is automatically cleared or rejected",
    ]), "screening_execution_mode": "rules_baseline", "feature_version": "unicode-name-ratio/1"}


DILIGENCE_CALCULATORS = {"kyc-edd-review": kyc, "ownership-lookthrough": ownership,
                        "sanctions-name-review": sanctions}
