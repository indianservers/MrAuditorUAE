"""Declared tax, pension and employment scopes are part of settlement identity."""

from app.modules.jurisdictions.packages import fingerprint


def scope_key(row):
    if row.get("benefit_scope") is not None:
        return "benefit:" + fingerprint(row["benefit_scope"])
    if row.get("withholding_scope") is not None:
        return "withholding:" + fingerprint(row["withholding_scope"])
    scope = row.get("pension_scope")
    return fingerprint(scope) if scope is not None else ""
