"""Synthetic draft reports for visual inspection of UAE/India table exports."""

from pdf_unicode_preview import ROOT, examples

if __name__ == "__main__":
    from app.modules.intelligence.exports import render

    target = ROOT / "output/pdf/statutory-unicode-review"
    target.mkdir(parents=True, exist_ok=True)
    for country, source in examples():
        row = source["body"]["rows"][0]
        event = {
            **source,
            "kind": "statutory-report",
            "engagement_id": "SYNTHETIC-ENGAGEMENT",
            "firm_name": row["counterparty"],
            "freshness": "CURRENT",
            "exported_at": "2026-10-27T00:00:00Z",
            "body": {
                "title": "SYNTHETIC multilingual financial source report",
                "country": country,
                "reporting_framework": "IFRS" if country == "AE" else "Ind AS",
                "template_version": 1,
                "review_status": "UNVERIFIED",
                "blocks": [
                    {
                        "number": 1,
                        "title": "Retained source transactions",
                        "kind": "financial_table",
                        "text": "Synthetic visual test only; no audit opinion or legal form qualification.",
                        "source_receipt": {
                            "id": "SYNTHETIC-RETAINED-SOURCE",
                            "version": 1,
                        },
                        "data": {
                            "rows": [dict(row, id=f"SYN-{i}") for i in range(1, 31)]
                        },
                    }
                ],
            },
        }
        content, _ = render(event, "pdf")
        (target / f"{country}.pdf").write_bytes(content)
        print(f"Saved synthetic {country} statutory draft PDF for visual inspection")
