"""Source scope validation and transaction-local integrity snapshots."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.modules.regulatory.schemas import SourceDocumentMetadata
from app.modules.regulatory.source_documents import verification_snapshot


@pytest.mark.parametrize(
    "changes",
    [
        {"country": "ZZ"},
        {"source_url": "http://mof.gov.ae/"},
        {"source_url": "https://user:password@mof.gov.ae/"},
        {"retrieved_on": date.today() + timedelta(days=1)},
    ],
)
def test_reference_metadata_rejects_invalid_country_credentials_or_retrieval(changes):
    with pytest.raises(ValueError):
        SourceDocumentMetadata.model_validate(
            {
                "title": "Synthetic source",
                "country": "AE",
                "source_url": "https://mof.gov.ae/",
                "retrieved_on": date.today(),
                **changes,
            }
        )


def test_integrity_snapshot_is_never_reused_across_transactions():
    holder = SimpleNamespace(transaction=object())
    db = SimpleNamespace(
        info={}, sync_session=SimpleNamespace(get_transaction=lambda: holder.transaction)
    )
    first = verification_snapshot(db)
    first["verified"].add("SYNTHETIC")
    first["bytes"] = 100
    assert verification_snapshot(db) is first
    holder.transaction = object()
    assert verification_snapshot(db) == {"verified": set(), "bytes": 0}
    holder.transaction = None
    assert verification_snapshot(db) is not verification_snapshot(db)
