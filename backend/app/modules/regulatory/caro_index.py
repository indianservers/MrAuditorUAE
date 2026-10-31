"""CARO numbered-matter evidence inventory; no legal/opinion qualification."""

from datetime import date

from fastapi import HTTPException

from app.db.models.platform import FinancialPeriod
from app.modules.country_workflows.india_company_scope import BINDING, CONTRACT
from app.modules.jurisdictions.packages import fingerprint

PREFIX = "india-caro-index:"
# References preserve every separately numbered leaf in paragraphs 3(i)-(xx).
LEAVES = [
    ("3.i.a.A", "PPE records"),
    ("3.i.a.B", "Intangible records"),
    ("3.i.b", "Asset verification"),
    ("3.i.c", "Property ownership"),
    ("3.i.d", "Revaluation"),
    ("3.i.e", "Benami proceedings"),
    ("3.ii.a", "Inventory verification"),
    ("3.ii.b", "Lender returns"),
    ("3.iii.a.A", "Group financing"),
    ("3.iii.a.B", "Other financing"),
    ("3.iii.b", "Financing terms"),
    ("3.iii.c", "Repayment schedules"),
    ("3.iii.d", "Overdue recovery"),
    ("3.iii.e", "Renewed financing"),
    ("3.iii.f", "Demand advances"),
    ("3.iv", "Sections 185/186"),
    ("3.v", "Deposit compliance"),
    ("3.vi", "Cost records"),
    ("3.vii.a", "Undisputed dues"),
    ("3.vii.b", "Disputed dues"),
    ("3.viii", "Unrecorded income"),
    ("3.ix.a", "Borrowing defaults"),
    ("3.ix.b", "Wilful default"),
    ("3.ix.c", "Term-loan use"),
    ("3.ix.d", "Funding maturity"),
    ("3.ix.e", "Group obligations"),
    ("3.ix.f", "Pledged investments"),
    ("3.x.a", "Public fundraising"),
    ("3.x.b", "Private fundraising"),
    ("3.xi.a", "Fraud matters"),
    ("3.xi.b", "ADT-4 reporting"),
    ("3.xi.c", "Whistleblower complaints"),
    ("3.xii.a", "Nidhi funding"),
    ("3.xii.b", "Nidhi deposits"),
    ("3.xii.c", "Nidhi defaults"),
    ("3.xiii", "Related parties"),
    ("3.xiv.a", "Internal audit"),
    ("3.xiv.b", "Internal-auditor reports"),
    ("3.xv", "Director noncash transactions"),
    ("3.xvi.a", "RBI registration"),
    ("3.xvi.b", "Financial-activity licensing"),
    ("3.xvi.c", "CIC criteria"),
    ("3.xvi.d", "Group CIC population"),
    ("3.xvii", "Cash losses"),
    ("3.xviii", "Auditor resignation"),
    ("3.xix", "Liability uncertainty"),
    ("3.xx.a", "Other-project CSR"),
    ("3.xx.b", "Ongoing-project CSR"),
]


def manifest(identifier):
    if identifier not in {PREFIX + s + "/1" for s in ("standalone", "consolidated")}:
        raise ValueError("Unknown CARO evidence inventory")
    scope = identifier[len(PREFIX) : -2]
    leaves = LEAVES if scope == "standalone" else [("3.xxi", "Constituent CARO qualifications")]
    items = [*leaves, ("4.1", "Adverse-answer reasons"), ("4.2", "Unable-to-opine reasons")]
    body = {
        "id": identifier,
        "country": "IN",
        "category": "caro",
        "kind": "caro-index",
        "statement_scope": scope,
        "title": "CARO 2020 clause evidence inventory — " + scope,
        "allow_not_applicable": False,
        "not_applicable_keys": [],
        "source_url": "https://resource.cdn.icai.org/60117aasb48979-a.pdf",
        "source_version": "ICAI 2020 guidance Appendix I, PDF pages 234-243; order reproduction, not Gazette-original qualification; commencement separately adopted",
        "source_sha256": "eed5ceefde2e91b51478b14521a88ecd2aea01c1a22df43b6c3d23f166f7d1c2",
        "requirements": [
            {
                "key": "caro." + ref,
                "title": ref + " — " + title,
                "disposition": "UNASSESSED",
                "source_required": True,
                "basis": "Assess this numbered matter, applicability, actual procedures, result and any required reasons in a separately reviewed linked workpaper; no activity is not missing evidence",
            }
            for ref, title in items
        ],
        "statutory_completeness_qualified": False,
        "limitations": [
            "Numbered-matter inventory only; each matter can contain multiple required facts, tables, measurements and professional judgments",
            "All items require explicit workpaper assessment, including nil/not-applicable conclusions and paragraph 4 reasons; the inventory cannot substitute for the work performed",
            "Current reviewed company-scope evidence must establish CARO duty for this exact period and standalone/consolidated scope",
            "The retained ICAI reproduction is not a qualified Gazette-original legal chain; later law changes and engagement adoption remain independently assessed",
            "No audit opinion, statutory issuance, signature or filing is authorized by this draft inventory",
        ],
    }
    return {**body, "sha256": fingerprint(body)}


async def scope_receipt(db, ctx, eng, config, contributors=None):
    if not config.requirements_pack or not config.requirements_pack.startswith(PREFIX):
        return []
    from app.modules.intelligence import service
    from app.modules.regulatory.report_requirements import preparers

    pack = manifest(config.requirements_pack)
    source = await service.event(db, ctx, eng.id, config.company_reporting_scope_id, True)
    body = source.body
    rows = body.get("rows", [])
    period = await db.get(FinancialPeriod, eng.period_id)
    duty = (
        "caro_full_standalone_matters"
        if pack["statement_scope"] == "standalone"
        else "caro_consolidated_paragraph3_xxi"
    )
    if (
        source.kind != "country-workflow"
        or body.get("workflow") != "india-company-reporting-scope"
        or body.get("review_status") != "REVIEWED"
        or body.get("contract") != CONTRACT
        or body.get("company_scope_document_binding") != BINDING
        or body.get("blocked") is not False
        or len(rows) != 1
        or rows[0].get(duty) is not True
        or rows[0].get("statement_scope") != pack["statement_scope"]
        or not period
        or (rows[0].get("period_start"), rows[0].get("period_end"))
        != (period.start_date.isoformat(), period.end_date.isoformat())
        or period.start_date < date(2021, 4, 1)
    ):
        raise HTTPException(
            409,
            "Retain one current independently reviewed company-scope result establishing CARO duty for this exact period and statement scope",
        )
    if contributors is not None:
        contributors.update(preparers(source))
    return [service.event_receipt(source)]
