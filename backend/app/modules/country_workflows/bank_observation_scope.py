"""Explicit evidence coverage across a financial cutoff; no bank authentication."""

from datetime import date
from types import SimpleNamespace

CONTRACT = "bank-account-observation-window/1"


def requires_scope(body):
    parameters = body.get("parameters")
    return "bank_observation_scope" in body or (
        isinstance(parameters, dict)
        and any(
            parameters.get(key) not in (None, "")
            for key in (
                "bank_observation_from",
                "bank_observation_through",
                "bank_observation_assessment",
            )
        )
    )


def selected_scope(data):
    start = getattr(data, "bank_observation_from", None)
    through = getattr(data, "bank_observation_through", None)
    assessment = getattr(data, "bank_observation_assessment", "")
    if start is None and through is None and not assessment:
        return None
    if (
        data.workflow != "bank-account-evidence"
        or type(start) is not date
        or type(through) is not date
        or not start <= data.as_of <= through
        or (through - start).days > 36600
        or len(assessment.strip()) < 10
    ):
        raise ValueError(
            "Account observation coverage needs both dates spanning the financial cutoff, a bounded window and a meaningful assessment"
        )
    return {
        "contract": CONTRACT,
        "from": start.isoformat(),
        "through": through.isoformat(),
        "assessment": assessment.strip(),
    }


def saved_scope(body):
    if "bank_observation_scope" not in body:
        if requires_scope(body):
            raise ValueError("Regenerate the missing declared account observation scope")
        return None
    scope = body["bank_observation_scope"]
    if not isinstance(scope, dict) or scope.get("contract") != CONTRACT:
        raise ValueError("Regenerate account observations with the current coverage contract")
    try:
        dates = [
            date.fromisoformat(value) for value in (body["as_of"], scope["from"], scope["through"])
        ]
        if any(
            value.isoformat() != raw
            for value, raw in zip(
                dates, (body["as_of"], scope["from"], scope["through"]), strict=True
            )
        ):
            raise ValueError("Use exact calendar dates for account coverage")
        result = selected_scope(
            SimpleNamespace(
                workflow=body.get("workflow"),
                as_of=dates[0],
                bank_observation_from=dates[1],
                bank_observation_through=dates[2],
                bank_observation_assessment=scope["assessment"],
            )
        )
        parameters = body.get("parameters")
        if isinstance(parameters, dict) and any(
            parameters.get(key) is not None and parameters[key] != scope[field]
            for key, field in (
                ("bank_observation_from", "from"),
                ("bank_observation_through", "through"),
            )
        ):
            raise ValueError("Saved account coverage differs from its declared parameters")
        rows = body["rows"]
        if len(rows) != 3 or {r["source_role"] for r in rows} != {"register", "ledger", "bank"}:
            raise ValueError("Retain all three account observation roles")
        return result
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Retain complete account observation coverage and assessment") from exc
