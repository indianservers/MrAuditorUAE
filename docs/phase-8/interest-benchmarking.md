# Interest Benchmarking

The loan engine preserves contract history from drawdown and can select a reporting accrual window within the tax period. It handles additional drawdowns, partial/bullet/early repayments, interest payments, fixed rates, sourced floating resets, ACT/365, ACT/360, 30E/360 and monthly/annual compounding. Events apply before the next interval; the reporting end date is exclusive.

Outputs include principal, capitalized and unpaid interest, reporting-period and lifetime accrued interest, period/lifetime paid interest, weighted principal/rate, native currency and reviewed single-rate translation. Translation is not a full FX remeasurement ledger. Expected principal reconciliation excludes capitalized interest.

An optional interest study must match purpose and currency. Selected target and rationale remain professional choices; no automatic median correction is made. Simple estimated impact is labelled separately from the contractual schedule. Credit, security, guarantee, covenants, seniority, subordination and prepayment facts are retained. The internal credit proxy is not an agency rating or a validated default model.

Tests cover bullet interest of AED10,000 on AED100,000 at 10% ACT/365, partial repayments, floating changes, compounding, prior-period history and FX. Live reference curves and commercial loan comparisons require licensed data and professional comparability review.
