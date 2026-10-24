"""Secret-free operational state; historical success is not a live health probe."""

from datetime import UTC, datetime


def language_state(
    *, adapter, enabled, credentials_present, external_approved, last=None, now=None
):
    now = now or datetime.now(UTC)
    state = "not_configured"
    if adapter == "mock" and enabled:
        state = "diagnostic_mode"
    elif adapter == "openai-compatible" and enabled and credentials_present:
        state = "configured_unverified"
        if not external_approved:
            state = "configured_disclosure_blocked"
        elif last:
            age = (now - last.created_at).total_seconds()
            if 0 <= age <= 300 and last.status == "completed":
                state = "configured_and_reachable"
            elif last.status == "failed":
                state = "configured_but_failing"
    return {
        "state": state,
        "observation": "recent tenant execution, not a live probe",
        "observed_at": last.created_at.isoformat() if last else None,
        "error_category": last.error_category if last else None,
        "reachability_ttl_seconds": 300,
        "deterministic_engines_require_gateway": False,
        "local_ml_requires_gateway": False,
        "narrative_is_independent_verification": False,
    }
