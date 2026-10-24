"""Versioned, tenant-owned vendor contracts; qualification is separate from configuration."""

from pydantic import Field

from app.modules.accounting.schemas import Input
from app.modules.connectors.native_config import configure
from app.modules.connectors.runtime import digest


class PartnerProfile(Input):
    provider: str = Field(pattern=r"^(busy|marg|dynamics|quickbooks)$")
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)
    vendor_document_reference: str = Field(min_length=1, max_length=1000)
    config: dict = Field(max_length=60)
    fixture_evidence: dict = Field(default_factory=dict, max_length=20)

    def seal(self):
        config = configure(self.provider, self.config, complete=True)
        result = {**self.model_dump(mode="json"), "config": config.model_dump(mode="json"),
                  "qualification": "requires_vendor_and_live_verification"}
        return {**result, "contract_hash": digest(result)}
