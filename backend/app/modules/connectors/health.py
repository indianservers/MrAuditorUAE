"""Bounded health summaries omit source payloads, tokens and provider error text."""

from datetime import UTC, datetime


def summary(connection, runs, now=None):
    now = now or datetime.now(UTC)
    latest = runs[0] if runs else None
    success = next((r for r in runs if r.status == "completed"), None)
    success_at = getattr(success, "updated_at", success.created_at) if success else None
    manifest = latest.manifest if latest else {}
    return {
        "provider": connection.provider,
        "connection_type": "import_export_adapter"
        if connection.provider == "file"
        else "implemented_connection_requires_qualification",
        "last_attempt_at": latest.created_at.isoformat() if latest else None,
        "last_success_at": success_at.isoformat() if success_at else None,
        "success_lookup": "latest 100 attempts; older history may exist",
        "lag_seconds": max(0, int((now - success_at).total_seconds())) if success_at else None,
        "status": latest.status if latest else "never_attempted",
        "completeness": latest.completeness if latest else "not_verified",
        "complete": bool(
            latest and latest.status == "completed" and latest.completeness == "complete"
        ),
        "error_category": latest.error_category if latest else None,
        "counts": {
            k: v
            for k, v in manifest.get("counts", {}).items()
            if isinstance(v, int) and not isinstance(v, bool)
        },
        "count_semantics": "provider-extracted counts; committed/rejected import totals require the linked validation report",
        "committed_import_records": None,
        "rejected_import_records": None,
        "checkpoint": {
            k: v
            for k, v in manifest.get("checkpoint", {}).items()
            if k in {"replayed", "downloaded"} and isinstance(v, int)
        },
        "execution_mode": manifest.get("execution_mode", "unavailable"),
        "live_qualified": False,
        "remediation": "Inspect rejected records and controls; renew authorization for auth errors; resume retained checkpoint or use controlled file import",
    }
