import uuid
from decimal import Decimal as D

import pytest

from app.modules.dmtt.calculations import calculate, deferred, scope
from app.modules.dmtt.schemas import Deferred, Election, Entity, Group

U = str(uuid.uuid4())


def group(year=2025, **kw):
    return Group.model_validate(
        {
            "fiscal_start": f"{year}-01-01",
            "fiscal_end": f"{year}-12-31",
            "upe_name": "Synthetic parent",
            "upe_jurisdiction": "GB",
            "multinational": True,
            "constituent_entity_ids": [U],
            "preceding_revenues": [
                {"year": y, "eur": "800000000", "evidence_id": U} for y in range(year - 4, year)
            ],
            "rule_version": "UAE-CD142-MD96/v2",
            "technical_evidence_id": U,
            **kw,
        }
    )


def entity(**kw):
    return Entity.model_validate(
        {
            "group_id": U,
            "entity_id": U,
            "source_engagement_id": U,
            "financial_run_id": U,
            "jurisdiction": "AE",
            "classification": "ordinary",
            "classification_evidence_id": U,
            "fx_to_calculation": "1",
            "fx_evidence_id": U,
            "current_tax": "900000",
            "covered_tax_evidence_id": U,
            "eligible_payroll": "1000000",
            "eligible_tangible_assets": "2000000",
            "substance_evidence_id": U,
            **kw,
        }
    )


def test_scope_threshold_and_short_period():
    g = group()
    assert scope(g)["in_scope"]
    g.preceding_revenues[0].eur = D(749999999)
    g.preceding_revenues[1].eur = D(0)
    g.preceding_revenues[2].eur = D(0)
    assert not scope(g)["in_scope"]
    g.preceding_revenues[1].months = 6
    g.preceding_revenues[1].eur = D(375000000)
    assert scope(g)["in_scope"]


def test_independent_uae_2025_golden():
    # Profit 10m, covered tax .9m: ETR 9%; SBIE 96k+152k=248k; .06*9.752m=585120.
    r = calculate(group(), [(entity(), D(10000000))])
    assert r["etr"] == D(".09")
    assert r["sbie"] == D(248000)
    assert r["uae_dmtt"] == D("585120.00")
    assert sum(x["tax"] for x in r["allocation"]) == r["uae_dmtt"]
    assert r["currency"] == "AED"


def test_jurisdictional_blending_not_entity_tax():
    r = calculate(
        group(2026), [(entity(), D(10000000)), (entity(current_tax="2100000"), D(10000000))]
    )
    assert r["etr"] == D(".15")
    assert r["uae_dmtt"] == 0
    assert r["sbie"] == D(484000)


@pytest.mark.parametrize("rate,expected", [(".09", "90"), (".2", "75")])
def test_deferred_never_universally_uplifts(rate, expected):
    r = Deferred(
        amount="90" if rate == ".09" else "100",
        recorded_rate=rate,
        treatment="ordinary",
        evidence_id=U,
    )
    assert deferred(r, 2025)["adjusted_deferred"] == D(expected)


def test_loss_specific_recast_requires_attribution():
    d = Deferred(amount="-90", recorded_rate=".09", treatment="globe_loss_recast", evidence_id=U)
    with pytest.raises(ValueError):
        deferred(d, 2025)
    d.loss_attributable = True
    assert deferred(d, 2025)["adjusted_deferred"] == D(-150)


def test_recapture_blocks_without_prior_year_calculation():
    d = Deferred(
        amount="50",
        recorded_rate=".15",
        treatment="ordinary",
        evidence_id=U,
        origin_year=2020,
        remaining_dtl=50,
    )
    with pytest.raises(ValueError, match="recapture"):
        calculate(group(), [(entity(deferred=[d.model_dump()]), D(10000000))])


def test_loss_is_technical_review_not_zero_tax_claim():
    r = calculate(group(), [(entity(), D(-1000000))])
    assert r["uae_dmtt"] is None
    assert r["loss_dta_candidate"] == D(150000)


def test_excluded_and_foreign_entities_not_blended():
    r = calculate(
        group(),
        [
            (entity(), D(10000000)),
            (entity(classification="excluded", current_tax="99999999"), D(100000000)),
            (entity(jurisdiction="GB"), D(99999999)),
        ],
    )
    assert r["net_globe_income"] == D(10000000)


def test_special_blending_not_silently_applied():
    with pytest.raises(ValueError):
        calculate(group(), [(entity(classification="jv"), D(10000000))])


def test_safe_harbour_period_and_independent_threshold():
    e = Election(
        group_id=U,
        type="transitional_cbcr",
        evidence_id=U,
        qualified_sources=True,
        all_conditions_reviewed=True,
        once_out_history_clear=True,
        cbcr_revenue_eur=20000000,
        cbcr_profit_eur=10000000,
        simplified_taxes_eur=1600000,
    )
    assert calculate(group(), [(entity(), D(10000000))], [e])["uae_dmtt"] == 0
    assert calculate(group(2026), [(entity(), D(10000000))], [e])["uae_dmtt"] > 0
    with pytest.raises(ValueError):
        calculate(group(2027), [(entity(), D(10000000))], [e])


def test_transition_needs_assessment():
    d = Deferred(amount="90", recorded_rate=".09", treatment="transition", evidence_id=U)
    with pytest.raises(ValueError):
        deferred(d, 2025)
    d.transition_exclusions_checked = True
    assert deferred(d, 2025)["adjusted_deferred"] == 90
