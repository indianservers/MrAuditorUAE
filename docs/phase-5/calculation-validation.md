# Calculation validation

Typed inputs and Python Decimal precision48 avoid binary financial arithmetic. Schedule outputs round half-up to eight places. Original source money remains NUMERIC(28,8). Mapping/journal sums and statement checks use exact Decimal agreement.

Independent expected values cover PV/interest/commencement payments, ECL weighting/stages/matrix, EIR, SSP revenue allocation, tax balances/OCI, depreciation, impairment/goodwill and discounted provisions. Integration fixtures assert assets/equity130, profit30, cash movement30, group assets390/profit75/NCI52/goodwill20, elimination balance and stale-input rejection. Comparative tests verify mapped prior values and block opening inconsistencies. Benchmarks independently assert scaled expected totals.

These establish the implemented scope, not every IFRS accounting scenario. No authoritative conformance suite, actuarial valuation or compliance certification is claimed.
