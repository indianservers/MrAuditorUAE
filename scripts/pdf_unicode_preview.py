"""Synthetic UAE/India export probes for actual PDF rendering inspection."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def examples():
    for country, party, currency in (
        ("AE", "شركة النور للتجارة", "AED"),
        ("IN", "भारत आपूर्तिकर्ता", "INR"),
    ):
        yield (
            country,
            {
                "id": "SYNTHETIC-UNICODE-PDF",
                "kind": "workflow-source",
                "version": 1,
                "sha256": "a" * 64,
                "created_at": "2026-10-27T00:00:00Z",
                "dependencies": [],
                "body": {
                    "country": country,
                    "review_status": "UNVERIFIED",
                    "rows": [
                        {
                            "id": "SYN-1",
                            "counterparty": party,
                            "currency": currency,
                            "amount": "105.00",
                        }
                    ],
                },
            },
        )


if __name__ == "__main__":
    from app.modules.intelligence.exports import render

    target = ROOT / "output/pdf/unicode-review"
    target.mkdir(parents=True, exist_ok=True)
    for country, event in examples():
        content, _ = render(event, "pdf")
        (target / f"{country}.pdf").write_bytes(content)
        print(f"Saved synthetic {country} PDF export for visual inspection")
