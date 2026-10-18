from typing import Literal

from pydantic import Field

from app.modules.tax.ai_output import TaxAIOutput


class VATAIOutput(TaxAIOutput):
    risk: str = Field(min_length=1, max_length=2000)
    extracted_fields: dict[str, str] = Field(default_factory=dict, max_length=30)
    document_processing: Literal["NOT_PROCESSED", "TEXT_PDF_EXTRACTED_UNVERIFIED"] = "NOT_PROCESSED"
