# IFRS 16 limited-scope engine

Liability = sum of future fixed payments / (1 + approved annual rate)^(actual days/365). Commencement payments are excluded from liability and included in ROU. ROU = liability + commencement payments + direct costs + restoration obligation − incentives. Interest accretes between dated payments; payment less interest is principal. Current principal covers the next 365 days. Straight-line ROU depreciation uses the supplied end date. Results round half-up to eight places.

Recognition, options and variable exclusions are human supplied. Remeasurement links a prior current run and reports the difference from prior carrying accrued to the new commencement; modification classification/journals require professional review. Proposals cover initial liability recognition. Lessor accounting, sale-and-leaseback, automatic exemptions, index forecasts and complete modification decision trees are unsupported.

Independent benchmark: payment 1,100 in 365 days at 10% gives PV1,000, interest100 and closing liability zero. A commencement payment100 gives ROU1,100 without changing liability.
