from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest
from pydantic import ValidationError

from app.modules.grc import calculations as c
from app.modules.grc.schemas import Scoring


def test_review_metadata_removal_preserves_business_review_dates():
    from app.modules.grc.service import clean

    assert clean(
        {
            "review_stage": 1,
            "review_cycle": 2,
            "review_approvers": ["x"],
            "review_date": "2026-12-31",
            "review_notes": "Business text",
        }
    ) == {"review_date": "2026-12-31", "review_notes": "Business text"}


def model(**extra):
    return Scoring(
        version_number=1, appetite="9", criteria_weights={"risk": "0.7", "age": "0.3"}, **extra
    )


def test_risk_uses_approved_matrix_and_appetite():
    assessment = NS(
        inherent_likelihood=5, inherent_impact=4, residual_likelihood=3, residual_impact=3
    )
    result = c.risk_score(model(), assessment)
    assert result["inherent"] == 20
    assert result["residual"] == 9
    assert result["appetite_breach"] is False
    assessment.residual_impact = 4
    assert c.risk_score(model(), assessment)["appetite_breach"] is True
    with pytest.raises(ValueError):
        c.risk_score(model(matrix_size=3), assessment)


def test_lookup_requires_complete_matrix_and_uses_cell():
    with pytest.raises(ValidationError):
        model(method="lookup", cells=[[1]])
    scoring = model(matrix_size=3, method="lookup", cells=[[1, 2, 3], [2, 4, 8], [3, 8, 12]])
    result = c.risk_score(
        scoring,
        NS(inherent_likelihood=3, inherent_impact=3, residual_likelihood=2, residual_impact=3),
    )
    assert result["residual"] == Decimal(8)


def test_resource_capacity_excludes_documented_deferrals():
    def item(identifier, hours, deferred=False):
        return NS(
            universe_id=identifier,
            auditor_id="a",
            criteria={"risk": Decimal(5), "age": Decimal(2)},
            budget_hours=Decimal(hours),
            actual_hours=Decimal(0),
            deferred=deferred,
        )

    plan = NS(
        items=[item("u1", "30"), item("u2", "20"), item("u3", "100", True)],
        capacity_hours={"a": Decimal(40)},
    )
    result = c.plan_score(plan, model())
    assert result["budgeted_hours"] == 50
    assert result["overbooked"] is True
    assert result["items"][0]["priority"] == Decimal("4.1")
    plan.items[0].criteria["risk"] = Decimal(6)
    with pytest.raises(ValueError):
        c.plan_score(plan, model())


def test_sod_never_combines_scopes_or_expired_permissions():
    from datetime import date

    today = date(2026, 10, 18)

    def assignment(permission, scope, until=None):
        return NS(
            principal="user",
            permission=permission,
            scope=scope,
            valid_from=date(2025, 1, 1),
            valid_to=until,
        )

    rule = NS(pairs=[NS(first="create", second="approve", rationale="Independent authorization")])
    access = NS(
        system="ERP",
        as_of=today,
        assignments=[
            assignment("create", "A"),
            assignment("approve", "B"),
            assignment("approve", "A", date(2026, 1, 1)),
        ],
    )
    assert c.sod(rule, access)["count"] == 0
    access.assignments.append(assignment("approve", "A"))
    result = c.sod(rule, access)
    assert result["count"] == 1
    assert result["conflicts"][0]["compensating_control_verified"] is False


@pytest.mark.parametrize(
    "frequency,expected",
    [
        ("daily", (2026, 2, 1)),
        ("weekly", (2026, 2, 7)),
        ("monthly", (2026, 2, 28)),
        ("quarterly", (2026, 4, 30)),
    ],
)
def test_calendar_schedules_preserve_timezone(frequency, expected):
    result = c.next_due(datetime(2026, 1, 31, 9, tzinfo=UTC), frequency)
    assert (result.year, result.month, result.day) == expected
    assert result.hour == 9 and result.tzinfo == UTC


def test_erp_csv_preserves_system_permissions_and_rejects_bad_populations():
    from app.modules.grc.sod_import import parse

    header = b"principal,permission,scope,valid_from,valid_to\n"
    row = b"ERP-user,AP-create,AE-entity,2026-01-01,\n"
    assert parse(header + row)[0]["permission"] == "AP-create"
    for content in [
        header,
        header + row + row,
        b"principal,role\nu,admin\n",
        header + b"u,p,A,2026-12-31,2026-01-01\n",
    ]:
        with pytest.raises(ValueError):
            parse(content)


def test_large_population_keeps_exact_complete_journal_signatures():
    from app.modules.audit_analytics.engine import AnalyticsEngine

    def rows():
        for i in range(12501):
            for suffix, account, debit, credit in [
                ("d", "100", "123.45", "0"),
                ("c", "300", "0", "123.45"),
            ]:
                yield {
                    "id": f"{i}-{suffix}",
                    "journal_ref": f"J-{i}",
                    "account_code": account,
                    "posting_date": "2026-01-01",
                    "debit": debit,
                    "credit": credit,
                }

    engine = AnalyticsEngine(rows())
    try:
        assert engine.count == 25002
        assert engine.db.execute("SELECT count(*) FROM signatures").fetchone()[0] == 12501
        assert engine.db.execute("SELECT count(DISTINCT sig) FROM signatures").fetchone()[0] == 1
        account_set, amount = engine.db.execute(
            "SELECT accounts,debit FROM signatures WHERE journal_ref='J-12500'"
        ).fetchone()
        assert account_set == "100|300" and amount == Decimal("123.45")
    finally:
        engine.close()
