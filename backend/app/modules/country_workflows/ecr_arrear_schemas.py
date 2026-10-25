"""Independent controls for the explicit EPFO ECR 2.0 eight-field arrear profile."""

from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.modules.jurisdictions.profiles import Strict

WholeRupees = Annotated[Decimal, Field(ge=0, max_digits=28, decimal_places=0)]


class ECRArrearControls(Strict):
    epf_wages: WholeRupees
    eps_wages: WholeRupees
    edli_wages: WholeRupees
    employee_pf: WholeRupees
    employer_pf: WholeRupees
    employer_eps: WholeRupees
