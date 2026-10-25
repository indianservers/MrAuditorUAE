"""A declared pension authority/cohort is part of the settlement identity."""

from app.modules.jurisdictions.packages import fingerprint


def scope_key(row):
    scope = row.get("pension_scope")
    return fingerprint(scope) if scope is not None else ""
