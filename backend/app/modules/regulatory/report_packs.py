"""Country-specific operational report presets, not legal-completeness certificates."""

from decimal import Decimal

from fastapi import HTTPException

from app.modules.country_workflows.vat201_layouts import EMIRATES, LAYOUTS
from app.modules.jurisdictions.packages import fingerprint

SOURCE = "https://tax.gov.ae/-/media/Files/EN/PDF/Guides/VAT-Returns-User-Guide.pdf"
PREFIX = "uae-vat201-review:"


def catalogue(country):
    if country != "AE":
        return []
    return [manifest(PREFIX + layout + "/1") for layout in LAYOUTS]


def manifest(identifier):
    if not identifier.startswith(PREFIX) or not identifier.endswith("/1"):
        raise ValueError("Unknown operational report preset")
    layout = identifier[len(PREFIX) : -2]
    if layout not in LAYOUTS:
        raise ValueError("Unknown operational report preset")
    body = {
        "id": identifier,
        "country": "AE",
        "category": "vat",
        "layout": layout,
        "title": "VAT201 reviewed comparison — " + str(LAYOUTS[layout]["label"]),
        "source_url": SOURCE,
        "source_version": "FTA VAT Returns User Guide, May 2018; operational layout only",
        "required_boxes": list(LAYOUTS[layout]["boxes"]),
        "requirements": [
            {
                "key": "vat201.box." + box,
                "title": "VAT201 Box "
                + box
                + (" — " + EMIRATES[box] if box in EMIRATES else " reviewed comparison"),
                "disposition": "UNASSESSED",
                "source_required": True,
                "basis": "Assess this explicit box against the current independently reviewed VAT201 comparison",
            }
            for box in LAYOUTS[layout]["boxes"]
        ],
        "statutory_completeness_qualified": False,
        "limitations": [
            "Selected operational layout only; this is not a complete current filing schema, e-commerce breakdown or legal eligibility assessment",
            "All selected boxes require reviewed comparison evidence; explicit zero is different from missing evidence or not applicable",
            "Report remains unsigned and unfiled; source qualification and professional scope assessment remain required",
        ],
    }
    return {**body, "sha256": fingerprint(body)}


def validate_config(config):
    if config.requirements_pack is None:
        return
    pack = manifest(config.requirements_pack)
    if config.category != pack["category"]:
        raise ValueError("VAT201 review preset requires the VAT report category")
    if {r.key for r in config.requirements} != {r["key"] for r in pack["requirements"]}:
        raise ValueError("Retain every requirement of the selected VAT201 review preset")
    if any(not r.source_required or r.disposition == "NOT_APPLICABLE" for r in config.requirements):
        raise ValueError(
            "Every VAT201 preset box needs source evidence; nil boxes are not not-applicable"
        )


def validate_source(pack, body, requirement_keys):
    if body.get("workflow") != "uae-vat-return" or body.get("vat201_layout") != pack["layout"]:
        raise HTTPException(
            409, "VAT201 preset requires a reviewed comparison using its exact layout"
        )
    if body.get("blocked") or body.get("vat201_arithmetic_error_count") != 0:
        raise HTTPException(
            409, "Resolve VAT201 comparison and arithmetic blockers before report review"
        )
    rows = body.get("rows", [])
    if len(rows) != len(pack["required_boxes"]) or {r["box"] for r in rows} != set(
        pack["required_boxes"]
    ):
        raise HTTPException(
            409, "VAT201 preset requires every explicit box, including assessed nil rows"
        )
    scopes = {(r["registration"], r["period_start"], r["period_end"], r["currency"]) for r in rows}
    if len(scopes) != 1 or any(r["currency"] != "AED" for r in rows):
        raise HTTPException(409, "VAT201 report source must cover one registration, period and AED")
    required = {key.removeprefix("vat201.box.") for key in requirement_keys}
    for row in rows:
        if row["box"] in required and (
            row["state"] != "MATCHED"
            or not row.get("book_source_ids")
            or not row.get("return_source_id")
            or any(value is None or Decimal(value) != 0 for value in row["differences"].values())
        ):
            raise HTTPException(
                409,
                "Preset coverage requires exact book/return agreement, not a tolerated variance",
            )
    checks = body.get("vat201_arithmetic_checks", [])
    if len(checks) != 30 or any(r["status"] != "MATCHED" for r in checks):
        raise HTTPException(
            409, "VAT201 preset requires both populations' retained arithmetic checks"
        )
