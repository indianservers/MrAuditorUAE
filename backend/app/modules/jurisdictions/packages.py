"""Versioned software capability manifests, not regulatory applicability approvals."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from fastapi import HTTPException

RELEASES = json.loads(
    (Path(__file__).parent / "releases/2026.10.1.json").read_text(encoding="utf8")
)


def package(country: str) -> dict:
    if country not in RELEASES:
        raise HTTPException(422, "Unknown ISO country")
    return deepcopy(RELEASES[country])


def fingerprint(manifest: dict) -> str:
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
