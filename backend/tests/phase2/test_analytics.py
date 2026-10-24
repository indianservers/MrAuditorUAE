import uuid
from decimal import Decimal

import pytest

from app.modules.audit_analytics.engine import RULES, VERSION, AnalyticsEngine, risk_score
from app.modules.audit_analytics.schemas import AnalyticsRequest


@pytest.fixture
def engine():
    population = []
    for i in range(1200):
        population.append(
            {
                "id": str(uuid.UUID(int=i + 1)),
                "account_code": "A",
                "journal_ref": str(i + 1),
                "posting_date": "2026-12-31",
                "document_date": "2026-01-01",
                "posting_timestamp": "2026-12-31T23:00:00+00:00",
                "debit": str(100000 if i < 300 else 100000 + i if i < 1100 else i),
                "credit": "0",
                "description": "manual adjustment plug",
                "counterparty": "Concentrated",
                "user": "operator",
                "manual": "true",
                "category": "Assets",
                "source_group": "Suspense",
            }
        )
    population.extend(
        [
            {
                **population[0],
                "id": str(uuid.uuid4()),
                "journal_ref": "1300",
                "debit": "10000",
                "posting_date": "2026-12-26",
                "account_code": "RARE",
            },
            {
                **population[0],
                "id": str(uuid.uuid4()),
                "journal_ref": "1301",
                "debit": "10000",
                "posting_date": "2027-01-02",
                "reversal_ref": "1200",
                "account_code": "RARE",
            },
            {
                **population[0],
                "id": str(uuid.uuid4()),
                "journal_ref": "1302",
                "debit": "0",
                "credit": "1000000",
                "account_code": "NEG",
            },
            {
                **population[0],
                "id": str(uuid.uuid4()),
                "journal_ref": "1",
                "debit": "1000000",
                "account_code": "B",
            },
        ]
    )
    obj = AnalyticsEngine(population)
    yield obj
    obj.close()


@pytest.fixture
def configured():
    return AnalyticsRequest(
        snapshot_id=uuid.uuid4(),
        materiality=Decimal(10),
        high_value=Decimal(10),
        holidays=["2026-12-31"],
        weekend_days=[5, 6],
        calendar_rationale="Synthetic Saturday/Sunday operating calendar for this test engagement",
        year_end="2026-12-31",
        timezone="Asia/Dubai",
        business_hours=(9, 17),
        timestamps_reliable=True,
        voucher_sequential=True,
        expected_pairs=[],
        prior_activity={"A": Decimal(1)},
        last_activity={"A": "2020-01-01"},
        benford_eligible=True,
        concentration=Decimal("0.01"),
        frequency_ratio=Decimal("0.01"),
    )


@pytest.mark.parametrize("rule", [r[0] for r in RULES])
def test_each_rule_reproducible_positive(engine, configured, rule):
    result = {r["rule_id"]: r for r in engine.evaluate(configured)}[rule]
    assert result["flagged_count"] > 0, (rule, result)
    assert result["rule_version"] == VERSION and result["calculation_evidence"]


@pytest.mark.parametrize(
    "rule", ["J01", "J02", "J03", "J10", "J11", "J14", "J15", "J18", "J19", "S21"]
)
def test_missing_prerequisites(engine, rule):
    result = {r["rule_id"]: r for r in engine.evaluate(AnalyticsRequest(snapshot_id=uuid.uuid4()))}[
        rule
    ]
    assert result["status"] == "not_testable" and result["tested_population"] == 0


def test_weekend_rule_uses_the_assessed_calendar_instead_of_a_country_default(engine, configured):
    saturday = {r["rule_id"]: r for r in engine.evaluate(configured)}["J01"]
    friday = {
        r["rule_id"]: r
        for r in engine.evaluate(configured.model_copy(update={"weekend_days": [4]}))
    }["J01"]
    assert saturday["flagged_count"] == 2
    assert friday["flagged_count"] == 0 and friday["status"] == "passed"
    assert all(code != "J01" for chunk in engine.flags() for code, _, _ in chunk)
    unassessed = {
        r["rule_id"]: r for r in engine.evaluate(AnalyticsRequest(snapshot_id=uuid.uuid4()))
    }["J01"]
    assert unassessed["status"] == "not_testable" and unassessed["flagged_count"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"weekend_days": [5], "calendar_rationale": ""},
        {"weekend_days": [5, 5], "calendar_rationale": "Reviewed calendar"},
        {"weekend_days": [7], "calendar_rationale": "Reviewed calendar"},
    ],
)
def test_invalid_or_unassessed_calendar_is_rejected(changes):
    with pytest.raises(ValueError):
        AnalyticsRequest(snapshot_id=uuid.uuid4(), **changes)


def test_risk_and_boundary():
    assert risk_score(["J01", "J01", "J08"], {})["score"] == 20
    assert risk_score(["J01"], {"J01": Decimal(25)})["band"] == "Moderate"
    assert risk_score(["J01", "J02"], {"J01": Decimal(100), "J02": Decimal(100)})["score"] == 100
    with pytest.raises(ValueError):
        risk_score(["J01"], {"J01": Decimal(-1)})


def test_empty_population():
    engine = AnalyticsEngine([])
    try:
        assert all(
            r["status"] == "not_testable"
            for r in engine.evaluate(AnalyticsRequest(snapshot_id=uuid.uuid4()))
        )
    finally:
        engine.close()


def test_clean_population_and_threshold_boundaries():
    rows = [
        {
            "id": str(uuid.uuid4()),
            "account_code": "A",
            "journal_ref": str(i + 1),
            "posting_date": "2026-06-02",
            "document_date": "2026-06-02",
            "posting_timestamp": "2026-06-02T12:00:00+00:00",
            "debit": str(100 + i),
            "credit": "0",
            "description": "Ordinary payment",
            "manual": "false",
            "category": "Assets",
            "counterparty": str(i),
            "user": str(i),
        }
        for i in range(2)
    ]
    engine = AnalyticsEngine(rows)
    try:
        request = AnalyticsRequest(
            snapshot_id=uuid.uuid4(),
            holidays=[],
            timezone="Asia/Dubai",
            business_hours=(9, 17),
            timestamps_reliable=True,
            materiality=Decimal(1000),
            high_value=Decimal(1000),
            round_unit=Decimal(1000),
            rare_count=1,
            near_duplicate_ratio=Decimal(0),
            concentration=Decimal("0.75"),
            year_end="2026-12-31",
            last_activity={"A": "2026-06-01"},
            prior_activity={"A": Decimal(100)},
            expected_pairs=[],
            voucher_sequential=True,
            velocity_limit=2,
        )
        assert all(result["flagged_count"] == 0 for result in engine.evaluate(request))
    finally:
        engine.close()
    engine = AnalyticsEngine(rows[:1])
    try:
        results = {
            r["rule_id"]: r
            for r in engine.evaluate(
                AnalyticsRequest(
                    snapshot_id=uuid.uuid4(), high_value=Decimal(100), materiality=Decimal(100)
                )
            )
        }
        assert results["J08"]["flagged_count"] == 1 and results["J09"]["flagged_count"] == 0
    finally:
        engine.close()
