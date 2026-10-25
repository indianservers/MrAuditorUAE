"""Numbered original response files and independently declared per-file controls."""

from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from app.modules.jurisdictions.profiles import Strict


class GSTR2BPart(Strict):
    file_number: int = Field(ge=1, le=100, strict=True)
    evidence_version_id: UUID
    expected_documents: int = Field(ge=0, le=1250, strict=True)
    tax_total: Decimal = Field(max_digits=36, decimal_places=8, allow_inf_nan=False)
    request_reference: str = Field(min_length=3, max_length=200)
    nil_reason: str | None = Field(default=None, min_length=10, max_length=2000)

    @model_validator(mode="after")
    def declared(self):
        if len(self.request_reference.strip()) < 3:
            raise ValueError("Reference the original numbered-file retrieval request")
        if (self.expected_documents == 0) != bool(self.nil_reason):
            raise ValueError("Each empty part needs its own explicit nil-population rationale")
        if self.expected_documents == 0 and self.tax_total != 0:
            raise ValueError("An empty GSTR-2B part cannot carry tax amounts")
        if self.nil_reason is not None and len(self.nil_reason.strip()) < 10:
            raise ValueError("Document the empty response-part population explicitly")
        return self
