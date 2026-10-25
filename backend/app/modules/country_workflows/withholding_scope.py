"""Keep transaction/year/section identity when withholding becomes a cash obligation."""

from datetime import date
from typing import Literal

from pydantic import model_validator

from app.modules.country_workflows.withholding_schemas import Identifier
from app.modules.jurisdictions.profiles import Strict


class WithholdingSettlementScope(Strict):
    legal_role: Literal["deductor", "collector"]
    tax_kind: Literal["TDS", "TCS"]
    rule_reference: Identifier
    tax_year_start: date
    tax_year_end: date
    transaction_reference: Identifier
    transaction_date: date

    @model_validator(mode="after")
    def consistent(self):
        if self.tax_kind != ("TDS" if self.legal_role == "deductor" else "TCS"):
            raise ValueError(
                "Only a deductor/collector liability can establish a withholding obligation"
            )
        if not self.tax_year_start <= self.transaction_date <= self.tax_year_end:
            raise ValueError("Withholding transaction must fall within its assessed tax year")
        return self
