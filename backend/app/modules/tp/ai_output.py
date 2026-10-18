from typing import Literal

from pydantic import Field

from app.modules.tax.ai_output import TaxAIOutput


class TPAIOutput(TaxAIOutput):
    economic_risks: list[str] = Field(min_length=1, max_length=30)
    comparable_information_verified: Literal[False]
    arms_length_conclusion_approved: Literal[False]
    extracted_clauses: dict[str, str] = Field(default_factory=dict, max_length=30)
