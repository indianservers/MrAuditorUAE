from app.modules.audit_execution.catalogue import APPROVE, PERMISSIONS, PREPARE

ROLE_PERMISSIONS = {
    "Platform Administrator": ["platform.manage"],
    "Firm Administrator": [
        "clients.read",
        "clients.write",
        "entities.read",
        "entities.write",
        "engagements.read",
        "engagements.write",
        "ai.execute",
        "ai.read",
        "jobs.execute",
        "jobs.read",
        "members.manage",
    ],
    "Audit Partner": [
        "clients.read",
        "entities.read",
        "engagements.read",
        "engagements.write",
        "ai.read",
        "ai.execute",
        "jobs.read",
    ],
    "Audit Manager": [
        "clients.read",
        "entities.read",
        "engagements.read",
        "engagements.write",
        "ai.read",
        "ai.execute",
    ],
    "Senior Auditor": [
        "clients.read",
        "entities.read",
        "engagements.read",
        "ai.read",
        "ai.execute",
    ],
    "Auditor": ["clients.read", "entities.read", "engagements.read"],
    "Tax Manager": [
        "clients.read",
        "entities.read",
        "engagements.read",
        "engagements.write",
        "ai.read",
        "ai.execute",
    ],
    "Tax Consultant": ["clients.read", "entities.read", "engagements.read"],
    "Client Viewer": ["clients.read", "entities.read", "engagements.read"],
}

PHASE2_PERMISSIONS = [
    "accounting.read",
    "accounting.import",
    "accounting.map",
    "connectors.manage",
    "analytics.run",
    "analytics.read",
    "sampling.run",
    "financial_ai.execute",
    "financial_ai.approve",
]
ROLE_PERMISSIONS["Firm Administrator"].extend(PHASE2_PERMISSIONS)

# Role defaults are installed in the database. Tenant policies may replace these grants.

STAFF_AUDIT = sorted(set(PREPARE.values()) - {"engagement.finalize", "workingpaper.review"})
for name in ["Auditor", "Senior Auditor", "Audit Manager", "Audit Partner"]:
    ROLE_PERMISSIONS[name] = sorted(set(ROLE_PERMISSIONS[name]) | {"audit.read"} | set(STAFF_AUDIT))
ROLE_PERMISSIONS["Audit Manager"] = sorted(
    set(ROLE_PERMISSIONS["Audit Manager"])
    | {
        "workingpaper.review",
        "workingpaper.approve",
        "audit.program.review",
        "audit.finding.resolve",
        "engagement.assign",
        "audit.evidence.review",
    }
)
ROLE_PERMISSIONS["Audit Partner"] = sorted(
    set(ROLE_PERMISSIONS["Audit Partner"])
    | set(APPROVE.values())
    | {"engagement.assign", "engagement.archive", "audit.export"}
)
ROLE_PERMISSIONS["Firm Administrator"] = sorted(
    set(ROLE_PERMISSIONS["Firm Administrator"])
    | set(PERMISSIONS) - {"portal.read", "portal.respond"}
)
ROLE_PERMISSIONS["Managing Partner"] = list(ROLE_PERMISSIONS["Audit Partner"])
ROLE_PERMISSIONS["Audit Partner / Chartered Accountant"] = list(ROLE_PERMISSIONS["Audit Partner"])
ROLE_PERMISSIONS["Audit Trainee"] = [
    "audit.read",
    "workingpaper.create",
    "audit.testing.execute",
    "audit.evidence.upload",
    "independence.declare",
    "engagements.read",
]
ROLE_PERMISSIONS["Quality Reviewer"] = [
    "audit.read",
    "engagements.read",
    "engagement.quality_review",
    "independence.declare",
    "workingpaper.review",
]
ROLE_PERMISSIONS["Read-only Reviewer"] = ["audit.read", "engagements.read"]
ROLE_PERMISSIONS["Firm Operations User"] = ["users.invite", "audit.read", "engagements.read"]
ROLE_PERMISSIONS["Platform Super Admin"] = ["platform.manage"]
ROLE_PERMISSIONS["Platform Support Administrator"] = ["platform.support"]
for name in [
    "Client Administrator",
    "Client Finance Manager",
    "Client Accountant",
    "Client Document Contributor",
    "Client Viewer",
]:
    ROLE_PERMISSIONS[name] = ["portal.read"] + (
        [] if name == "Client Viewer" else ["portal.respond"]
    )

from app.modules.ifrs.catalogue import KINDS as IFRS_KINDS  # noqa: E402
from app.modules.ifrs.catalogue import PERMISSIONS as IFRS_PERMISSIONS  # noqa: E402

IFRS_PREPARE = {v[0] for v in IFRS_KINDS.values()} | {"ifrs.read"}
for name in [
    "Firm Administrator",
    "Audit Manager",
    "Audit Partner",
    "Managing Partner",
    "Audit Partner / Chartered Accountant",
]:
    ROLE_PERMISSIONS[name] = sorted(set(ROLE_PERMISSIONS[name]) | set(IFRS_PERMISSIONS))
ROLE_PERMISSIONS["Financial Reporting Preparer"] = sorted(
    set(ROLE_PERMISSIONS["Auditor"]) | IFRS_PREPARE
)
ROLE_PERMISSIONS["Financial Reporting Manager"] = list(ROLE_PERMISSIONS["Audit Manager"])
ROLE_PERMISSIONS["Chartered Accountant"] = list(ROLE_PERMISSIONS["Audit Partner"])
ROLE_PERMISSIONS["Consolidation Specialist"] = list(
    ROLE_PERMISSIONS["Financial Reporting Preparer"]
)
ROLE_PERMISSIONS["Tax Manager"] = sorted(
    set(ROLE_PERMISSIONS["Tax Manager"])
    | {"audit.read", "ifrs.read", "ifrs.calculation.execute", "ifrs.assumption.approve"}
)

from app.modules.tax.catalogue import KINDS as TAX_KINDS  # noqa: E402
from app.modules.tax.catalogue import PERMISSIONS as TAX_PERMISSIONS  # noqa: E402

TAX_PREPARE = {p[0] for p in TAX_KINDS.values()} | {"tax.profile.read"}
TAX_BASE = set(ROLE_PERMISSIONS["Auditor"]) | {"tax.profile.read", "ifrs.read"}
for name in ["Corporate Tax Preparer", "Senior Tax Consultant"]:
    ROLE_PERMISSIONS[name] = sorted(TAX_BASE | TAX_PREPARE - {"tax.rules.manage"})
for name in [
    "Firm Administrator",
    "Tax Manager",
    "Tax Director",
    "Tax Partner",
    "Chartered Accountant",
]:
    ROLE_PERMISSIONS[name] = sorted(
        set(ROLE_PERMISSIONS.get(name, [])) | TAX_BASE | set(TAX_PERMISSIONS)
    )
ROLE_PERMISSIONS["Independent Reviewer"] = sorted(
    TAX_BASE
    | {
        "tax.computation.review",
        "tax.computation.approve",
        "tax.adjustment.approve",
        "tax.qfzp.approve",
    }
)
ROLE_PERMISSIONS["Client Finance User"] = ["portal.read", "portal.respond"]

from app.modules.vat.catalogue import PERMISSIONS as VAT_PERMISSIONS  # noqa: E402

VAT_BASE = set(ROLE_PERMISSIONS["Auditor"]) | {"vat.read"}
VAT_PREPARE = {
    "vat.profile.write",
    "vat.invoice.prepare",
    "vat.adjustment.prepare",
    "vat.recovery.prepare",
    "vat.return.prepare",
    "vat.calculate",
    "vat.ai.execute",
    "einvoice.prepare",
    "einvoice.sandbox",
}
for name in ["VAT Analyst", "VAT Consultant", "Invoice Validator", "Tax Consultant"]:
    ROLE_PERMISSIONS[name] = sorted(set(ROLE_PERMISSIONS.get(name, [])) | VAT_BASE | VAT_PREPARE)
for name in [
    "Firm Administrator",
    "VAT Manager",
    "Tax Manager",
    "Tax Director",
    "Tax Partner",
    "Chartered Accountant",
]:
    ROLE_PERMISSIONS[name] = sorted(
        set(ROLE_PERMISSIONS.get(name, [])) | VAT_BASE | set(VAT_PERMISSIONS)
    )
ROLE_PERMISSIONS["VAT Read-only Reviewer"] = ["audit.read", "engagements.read", "vat.read"]

from app.modules.tp.catalogue import KINDS as TP_KINDS  # noqa: E402
from app.modules.tp.catalogue import PERMISSIONS as TP_PERMISSIONS  # noqa: E402

TP_BASE = {
    "jobs.read",
    "audit.read",
    "workingpaper.create",
    "audit.evidence.upload",
    "engagements.read",
    "clients.read",
    "entities.read",
    "ifrs.read",
    "tp.read",
    "tp.relationship.read",
}
TP_PREPARE = {pair[0] for key, pair in TP_KINDS.items() if key != "rule"} | {
    "tp.calculate",
    "tp.ai.execute",
    "tp.report.export",
}
for name in ["TP Analyst", "TP Economist", "Financial Analyst"]:
    ROLE_PERMISSIONS[name] = sorted(TP_BASE | TP_PREPARE)
for name in [
    "TP Manager",
    "Transfer Pricing Director",
    "Firm Administrator",
    "Tax Manager",
    "Tax Partner",
    "Chartered Accountant",
]:
    ROLE_PERMISSIONS[name] = sorted(
        set(ROLE_PERMISSIONS.get(name, [])) | TP_BASE | set(TP_PERMISSIONS)
    )
ROLE_PERMISSIONS["TP Read-only Reviewer"] = [
    "audit.read",
    "engagements.read",
    "ifrs.read",
    "tp.read",
    "tp.relationship.read",
]

ML_PERMISSIONS = {"ml.read", "ml.train", "ml.approve", "ml.deploy", "ml.score", "ml.feedback"}
DMTT_PERMISSIONS = {
    "dmtt.read",
    "dmtt.prepare",
    "dmtt.approve",
    "dmtt.calculate",
    "dmtt.ai.execute",
}
for name in ["Firm Administrator", "Chartered Accountant"]:
    ROLE_PERMISSIONS[name] = sorted(set(ROLE_PERMISSIONS[name]) | ML_PERMISSIONS | DMTT_PERMISSIONS)
for name in ["Tax Manager", "Tax Director", "Tax Partner"]:
    ROLE_PERMISSIONS[name] = sorted(set(ROLE_PERMISSIONS[name]) | DMTT_PERMISSIONS)
ROLE_PERMISSIONS["ML Engineer"] = sorted(
    set(ROLE_PERMISSIONS["Auditor"]) | {"ml.read", "ml.train", "ml.score", "ml.feedback"}
)
ROLE_PERMISSIONS["Model Risk Reviewer"] = [
    "audit.read",
    "engagements.read",
    "ml.read",
    "ml.approve",
    "ml.deploy",
    "ml.score",
    "ml.feedback",
]
ROLE_PERMISSIONS["Pillar Two Analyst"] = sorted(
    set(ROLE_PERMISSIONS["Auditor"])
    | {
        "ifrs.read",
        "tax.profile.read",
        "dmtt.read",
        "dmtt.prepare",
        "dmtt.calculate",
        "dmtt.ai.execute",
    }
)
ROLE_PERMISSIONS["Pillar Two Reviewer"] = sorted(
    set(ROLE_PERMISSIONS["Auditor"])
    | {
        "ifrs.read",
        "tax.profile.read",
        "dmtt.read",
        "dmtt.approve",
        "dmtt.calculate",
        "dmtt.ai.execute",
    }
)

from app.modules.grc.catalogue import PERMISSIONS as GRC_PERMISSIONS  # noqa: E402

GRC_BASE = {"grc.read", "engagements.read", "clients.read", "entities.read"}
GRC_AUDIT = (
    set(ROLE_PERMISSIONS["Auditor"])
    | GRC_BASE
    | {
        "grc.calculate",
        "ml.read",
        "ml.score",
        "ml.feedback",
        "ml.prediction.read",
        "ml.feedback.submit",
    }
)
for name in [
    "Chief Audit Executive",
    "Head of Internal Audit",
    "Internal Audit Manager",
    "Chartered Accountant",
    "Firm Administrator",
]:
    ROLE_PERMISSIONS[name] = sorted(
        set(ROLE_PERMISSIONS.get(name, [])) | GRC_AUDIT | GRC_PERMISSIONS
    )
for name in ["Senior Internal Auditor", "Internal Auditor"]:
    ROLE_PERMISSIONS[name] = sorted(
        GRC_AUDIT
        | {
            "ia.universe.manage",
            "ia.plan.prepare",
            "ia.engagement.create",
            "ia.engagement.execute",
            "ia.report.prepare",
            "erm.risk.create",
            "erm.risk.assess",
            "grc.control.create",
            "grc.control.test",
            "grc.sod.analyze",
            "grc.deficiency.manage",
            "grc.remediation.manage",
            "monitor.rule.create",
            "monitor.job.execute",
            "monitor.alert.review",
            "grc.ai.execute",
        }
    )
ROLE_PERMISSIONS["Risk Manager"] = sorted(
    GRC_AUDIT
    | {
        "erm.risk.create",
        "erm.risk.assess",
        "erm.risk.approve",
        "erm.appetite.manage",
        "grc.ai.execute",
    }
)
ROLE_PERMISSIONS["Compliance Officer"] = sorted(
    GRC_AUDIT
    | {
        "compliance.manage",
        "compliance.approve",
        "policy.manage",
        "policy.approve",
        "grc.thirdparty.manage",
        "grc.ai.execute",
    }
)
ROLE_PERMISSIONS["Risk Owner"] = sorted(
    GRC_BASE | {"erm.risk.create", "erm.risk.assess", "policy.acknowledge"}
)
ROLE_PERMISSIONS["Control Owner"] = sorted(GRC_BASE | {"grc.control.create", "policy.acknowledge"})
ROLE_PERMISSIONS["Process Owner"] = sorted(
    GRC_BASE | {"ia.universe.manage", "policy.manage", "policy.approve", "policy.acknowledge"}
)
ROLE_PERMISSIONS["Remediation Owner"] = sorted(
    GRC_BASE | {"grc.remediation.manage", "policy.acknowledge"}
)
for name in ["Audit Committee Member", "Board Viewer"]:
    ROLE_PERMISSIONS[name] = ["engagements.read", "governance.board.read"]
ROLE_PERMISSIONS["Internal Audit Quality Reviewer"] = sorted(
    GRC_AUDIT
    | {
        "qaip.assessment.manage",
        "qaip.assessment.review",
        "ia.engagement.review",
        "grc.control.review",
    }
)

from app.modules.enterprise_ai.catalogue import ADMIN as AI_ADMIN  # noqa: E402
from app.modules.enterprise_ai.catalogue import READ as AI_READ  # noqa: E402
from app.modules.enterprise_ai.catalogue import REVIEW as AI_REVIEW  # noqa: E402

for name, permissions in list(ROLE_PERMISSIONS.items()):
    if "audit.read" in permissions:
        grants = AI_READ | (AI_REVIEW if "workingpaper.approve" in permissions else set())
        ROLE_PERMISSIONS[name] = sorted(set(permissions) | grants)
ROLE_PERMISSIONS["Firm Administrator"] = sorted(
    set(ROLE_PERMISSIONS["Firm Administrator"]) | AI_ADMIN | AI_REVIEW | AI_READ
)
ROLE_PERMISSIONS["AI Administrator"] = sorted(
    AI_ADMIN | {"ai.model.evaluate", "ai.usage.read", "ai.auditlog.read"}
)
