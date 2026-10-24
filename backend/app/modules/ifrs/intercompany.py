"""Explicit presentation-currency pair checks; no difference is eliminated implicitly."""


def reconcile(data):
    members = {member.engagement_id for member in data.members}
    references = set()
    rows, issues = [], []
    for pair in data.intercompany:
        if pair.reference in references:
            raise ValueError("Duplicate intercompany pair reference")
        references.add(pair.reference)
        if (
            pair.from_engagement_id == pair.to_engagement_id
            or {pair.from_engagement_id, pair.to_engagement_id} - members
        ):
            raise ValueError("Intercompany counterparties must be distinct declared group members")
        if pair.currency != data.presentation_currency:
            raise ValueError(
                "Intercompany matching requires a reviewed presentation-currency bridge"
            )
        difference = pair.receivable - pair.payable
        matched = difference == 0 and pair.difference_type == "matched"
        rows.append(
            {
                **pair.model_dump(mode="json"),
                "difference": difference,
                "state": "MATCHED" if matched else "UNRESOLVED",
                "elimination": "PROPOSAL_REQUIRED" if matched else "BLOCKED",
            }
        )
        if not matched:
            issues.append(
                {
                    "code": "INTERCOMPANY_UNRESOLVED",
                    "reference": pair.reference,
                    "blocking": True,
                    "difference": difference,
                    "remediation": "Resolve timing/currency/missing-entry/classification/dispute and reapprove both packages",
                }
            )
    return rows, issues
