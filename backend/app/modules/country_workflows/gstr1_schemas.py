"""Independent retained-section controls, not filing or full-return completeness."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from app.modules.jurisdictions.profiles import Strict

GSTR1Section = Literal[
    "b2b", "b2ba", "b2cl", "b2cla", "cdnr", "cdnra", "cdnur", "cdnura", "exp", "expa"
]
SECTIONS = {"b2b", "b2ba", "b2cl", "b2cla", "cdnr", "cdnra", "cdnur", "cdnura", "exp", "expa"}
Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]


class GSTR1SectionControl(Strict):
    section: GSTR1Section
    document_count: int = Field(ge=0, le=1250)
    taxable_base: Money
    igst: Money
    cgst: Money
    sgst: Money
    cess: Money
