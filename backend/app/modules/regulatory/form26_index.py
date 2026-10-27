"""Numbered-item/schedule-group evidence index, not an electronic filing schema."""

from app.modules.jurisdictions.packages import fingerprint
from app.modules.regulatory.tax_forms import FORM_26_PUBLISHED, FORM_26_RULE

PREFIX = "india-form26-index:"
GROUPS = [
    ("general", "General information", 9, 12),
    ("accounting", "Accounting information", 13, 19),
    ("income", "Income and receipts", 20, 25),
    ("expenses", "Expense deductions", 26, 34),
    ("prior-period", "Prior period", 35, 35),
    ("losses", "Losses and depreciation", 36, 39),
    ("international", "International taxation", 40, 43),
    ("other", "Other parameters", 44, 48),
    ("withholding", "TDS and TCS", 49, 51),
    ("gst", "Indirect taxes", 52, 52),
    ("quantities", "Inventory quantities", 53, 53),
]


def manifest(identifier):
    if identifier not in {PREFIX + "A/1", PREFIX + "B/1"}:
        raise ValueError("Unknown Form 26 evidence index")
    part = identifier[len(PREFIX)]
    items = [(f"form26.report.{part}", f"Form 26 report Part {part} and accountant review")]
    items += [
        (f"form26.C.{number}", f"Part C item {number} — assessee particulars")
        for number in range(1, 9)
    ]
    for key, label, start, end in GROUPS:
        items.extend(
            (f"form26.D.{number}", f"Part D item {number} — {label}")
            for number in range(start, end + 1)
        )
        items.append(("form26.schedule." + key, "Schedule group — " + label))
    body = {
        "id": identifier,
        "country": "IN",
        "category": "india-tax-audit",
        "kind": "form26-index",
        "title": f"Form 26 evidence index — report Part {part}, particulars C/D",
        "report_part": part,
        "allow_not_applicable": True,
        "not_applicable_keys": [
            key
            for key, _ in items
            if key.startswith(("form26.D.", "form26.schedule.")) and key != "form26.D.9"
        ],
        "layout": "numbered-items-and-schedule-groups",
        "scope_label": "Numbered items and schedule groups only; not all subfields, calculations or a qualified filing form",
        "source_url": FORM_26_PUBLISHED,
        "source_version": "Published 33-page Form 26; Rule 47; text index checked 27 October 2026",
        "selection_sources": [FORM_26_RULE, FORM_26_PUBLISHED],
        "source_capture_status": "OFFICIAL_TEXT_INDEX_REVIEWED_ORIGINAL_PDF_ARCHIVE_AND_VISUAL_QUALIFICATION_PENDING",
        "source_status": "Official text index checked; original PDF archival, visual review and professional validation pending",
        "requirements": [
            {
                "key": key,
                "title": title,
                "disposition": "UNASSESSED",
                "source_required": True,
                "basis": "Assess the numbered item or schedule group against current reviewed workpapers; no applicability or amount inferred",
            }
            for key, title in items
        ],
        "statutory_completeness_qualified": False,
        "limitations": [
            "Indexes numbered particulars 1–53, eleven schedule groups and the selected report part; individual subfields and statutory calculations still require qualified schedules",
            "Every item needs explicit applicability and current reviewed workpaper mappings, including evidence for not-applicable decisions; a generic applicability checklist is not clause evidence",
            "Legacy 3CA/3CB/3CD are separate; this preset requires the existing assessed Form 26 tax-period/report-part scope",
            "Original source archival, visual verification and professional validation are pending; use this text-derived index only as a draft evidence index",
            "Unsigned draft only; no official form completion, opinion, UDIN, signature, filing or real-client qualification is established",
        ],
    }
    return {**body, "sha256": fingerprint(body)}
