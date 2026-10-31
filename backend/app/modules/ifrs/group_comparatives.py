"""Prior reported group figures, without translating or restating prior amounts."""

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal


def population(data):
    members = data.get("members", [])
    if len(members) < 2 or any(not member.get("entity_id") for member in members):
        raise ValueError(
            "Regenerate the group calculation with retained member legal-entity identities"
        )
    result = {}
    for member in members:
        entity = member["entity_id"]
        if entity in result:
            raise ValueError("A legal entity cannot be counted more than once in a group")
        result[entity] = (Decimal(str(member["ownership"])), member["acquisition_type"])
    return result


def apply(current, previous):
    """Return copied lines; the caller retains source permissions and dependencies."""
    if current["currency"] != previous["currency"]:
        raise ValueError(
            "Group comparative presentation currencies must agree; no new FX is inferred"
        )
    if date.fromisoformat(previous["period_end"]) + timedelta(days=1) != date.fromisoformat(
        current["period_start"]
    ):
        raise ValueError("The comparative group period must immediately precede the current period")
    if date.fromisoformat(previous["period_start"]) > date.fromisoformat(previous["period_end"]):
        raise ValueError("The prior group reporting period is invalid")
    if population(current) != population(previous):
        raise ValueError(
            "Changed group membership, ownership or acquisition classification requires separately validated comparative treatment"
        )
    prior = {}
    for row in previous["lines"]:
        if row["line_code"] in prior:
            raise ValueError("Duplicate prior group chart line")
        prior[row["line_code"]] = row
    lines = []
    seen = set()
    for original in current["lines"]:
        code = original["line_code"]
        if code in seen:
            raise ValueError("Duplicate current group chart line")
        seen.add(code)
        row = deepcopy(original)
        source = prior.get(code)
        if source and (source["section"], source.get("category")) != (
            row["section"],
            row.get("category"),
        ):
            raise ValueError(
                "Group comparative chart classification changed; retain a validated reclassification bridge"
            )
        row["comparative"] = Decimal(str(source["current"])) if source else Decimal(0)
        row["comparative_source_accounts"] = (
            deepcopy(source.get("source_accounts", [])) if source else []
        )
        row["comparative_presence"] = (
            "REPORTED_PRIOR_LINE" if source else "ABSENT_FROM_COMPLETE_PRIOR_CHART"
        )
        lines.append(row)
    for code, source in prior.items():
        if code in seen:
            continue
        lines.append(
            {
                **deepcopy(source),
                "current": Decimal(0),
                "opening": Decimal(0),
                "comparative": Decimal(str(source["current"])),
                "source_accounts": [],
                "comparative_source_accounts": deepcopy(source.get("source_accounts", [])),
                "comparative_presence": "PRIOR_ONLY_LINE_RETAINED",
            }
        )
    return lines
