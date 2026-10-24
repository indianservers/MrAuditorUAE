"""Bounded primary-source retention. Retrieval does not adopt a policy or legal rule."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / ".local-runtime/accounting-strengthening/sources"
DOCS = ROOT / "docs/engine-strengthening/phase3"
SOURCES = [
    (
        "IAS2",
        "https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/",
        "IAS 2.9, 10, 25, 28–34",
        "Lower of cost and NRV; FIFO/weighted average; selling and completion costs; reversal ceiling",
        "Current public overview; paragraph-level historical text cross-checked separately; current licensed edition still requires technical reviewer verification",
    ),
    (
        "IAS16",
        "https://www.ifrs.org/issued-standards/list-of-standards/ias-16-property-plant-and-equipment/",
        "IAS 16.43, 51, 55, 61",
        "Component depreciation, evidenced available-for-use date, residual/life reviews and prospective estimates",
        "Public overview plus 2022 issued text used for availability provision; current entity policy and disclosures require review",
    ),
    (
        "IAS12",
        "https://www.ifrs.org/issued-standards/list-of-standards/ias-12-income-taxes/",
        "IAS 12.24, 34–36, 47, 58, 61A and Pillar Two amendment",
        "Item-specific tax bases; evidenced DTA recovery; separate P&L/OCI movements and separate Pillar Two scope",
        "No universal UAE tax rate adopted by this accounting phase; E05 release and approved item rates remain prerequisites",
    ),
    (
        "IAS19",
        "https://www.ifrs.org/issued-standards/list-of-standards/ias-19-employee-benefits/",
        "IAS 19.67 and defined-benefit recognition",
        "Actuarial projected-unit-credit measurement is distinct from a statutory settlement estimate",
        "Implemented bridge reconciles supplied expert values; does not implement actuarial valuation",
    ),
    (
        "IAS21",
        "https://www.ifrs.org/issued-standards/list-of-standards/ias-21-the-effects-of-changes-in-foreign-exchange-rates/",
        "IAS 21.39–40; relevant lack-of-exchangeability amendments",
        "Closing/transaction-date rates; representative averages only; separate presentation translation effect",
        "No FX feed, exchangeability model or IAS 29 restatement; missing/special-case rates block supported execution",
    ),
    (
        "IAS36",
        "https://www.ifrs.org/issued-standards/list-of-standards/ias-36-impairment-of-assets/",
        "IAS 36.18, 104–105, 117, 124",
        "Recoverable amount is higher of VIU and FVLCD; goodwill allocation/reversal controls",
        "Annual end-of-period explicit-flow model only; no independently sourced valuations or full CGU asset-floor allocation",
    ),
    (
        "IFRS10",
        "https://www.ifrs.org/issued-standards/list-of-standards/ifrs-10-consolidated-financial-statements/",
        "IFRS 10.7, B86 and effective control dates",
        "Power, variable returns and ability to affect returns; reciprocal elimination and approved packages",
        "Complex control, ownership events, full NCI rollforward and group release remain specialist dependencies",
    ),
    (
        "IFRS16",
        "https://www.ifrs.org/issued-standards/list-of-standards/ifrs-16-leases/",
        "IFRS 16.22–28, 36, 39–46",
        "Dated payments and approved accounting term/rate; classification of reassessments/modifications",
        "Dated lessee liability only; no generic modification or lessor journal; legacy initial-liability proposal cannot be reused for modifications",
    ),
    (
        "UAE-MAINLAND",
        "https://www.mohre.gov.ae/assets/download/4cb0929c/federal-decree-law-en.aspx",
        "Federal Decree-Law 33/2021 Article 51; alternative scheme and part-time qualifications",
        "Verify cohort, basic wage, service and applicable scheme; no universal formula for every UAE worker",
        "Existing supplied-rule benefit calculator retained; no automatic rule adoption or actuarial conclusion",
    ),
    (
        "ADGM",
        "https://assets.adgm.com/download/assets/ADGM%20EAO%20-%20FAQs%20-%20ER%202024%20%28Feb%202025%29.pdf/eed10768edbe11ef9eaee2d468ad6a26",
        "Employment Regulations 2024, effective 1 April 2025; section 61",
        "ADGM framework assessed independently",
        "Review applicable consolidated regulation and contract; no mainland default applied",
    ),
    (
        "DIFC",
        "https://www.difccourts.ae/application/files/7117/1636/5975/DIFCC_PBP_FAQs_DIFC_Employment_Law.pdf",
        "DIFC employment law and qualifying workplace savings schemes; pre-February 2020 accrued benefits",
        "DIFC scheme/transitional assessment is distinct from mainland statutory gratuity",
        "Official court guidance is not a substitute for current consolidated legislation, scheme evidence and contractual review",
    ),
]


def retrieve(entry):
    code, url, provision, policy, limitation = entry
    row = {
        "id": code,
        "url": url,
        "provision": provision,
        "interpretation": policy,
        "verification_dependency": limitation,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "applicable_edition": "Entity/period-specific edition must be approved; retrieval date is not an effective date",
        "reviewer_approval": "NOT_ADOPTED_BY_RETRIEVAL",
    }
    try:
        with urlopen(
            Request(url, headers={"User-Agent": "TheAuditor-PrimarySourceReview/1.0"}),
            timeout=30,
        ) as response:
            content = response.read(10 * 1024 * 1024 + 1)
            if len(content) > 10 * 1024 * 1024:
                raise ValueError("Primary source exceeds bounded retrieval limit")
            if (
                not content.startswith(b"%PDF")
                and b"<html" not in content[:3000].lower()
            ):
                raise ValueError("Unexpected primary-source document format")
            suffix = ".pdf" if content.startswith(b"%PDF") else ".html"
            target = DEST / (code + suffix)
            target.write_bytes(content)
            row.update(
                status="RETRIEVED",
                sha256=hashlib.sha256(content).hexdigest(),
                bytes=len(content),
                retained_path=str(target),
                final_url=response.url,
            )
    except (OSError, URLError, ValueError) as error:
        row.update(status="ACCESS_DEPENDENCY", error=str(error)[:300])
    return row


if __name__ == "__main__":
    DEST.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(retrieve, SOURCES))
    (DOCS / "source-policy-register.json").write_text(
        json.dumps(
            {
                "sources": rows,
                "scope": "Primary public sources for implemented provisions; no complete IFRS compliance certification or automatic legal/policy approval",
            },
            indent=2,
        )
    )
    print(
        json.dumps(
            {
                "retrieved": sum(row["status"] == "RETRIEVED" for row in rows),
                "total": len(rows),
            }
        )
    )
