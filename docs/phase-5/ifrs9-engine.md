# IFRS 9 limited-scope engine

General ECL probability-weights discounted PD × LGD × exposure. Stage1 selects 12-month PD; Stage2 lifetime PD; Stage3 default PD=1. Simplified approach uses lifetime PD. Explicit cash-shortfall inputs are an alternative. Provision matrices use approved segment loss rates/scenario multipliers and assume timing is already incorporated. Probabilities total one; duplicate exposures/scenarios and lifetime PD below 12-month PD are rejected.

Independent fixture: exposure1,000 with 70% PD10%/LGD50% and 30% PD20%/LGD50% gives ECL65 at zero discount. Lifetime PD30%/40% gives165; Stage3 gives500. Staging, SICR/default/write-off policies and forecasts require human assumptions. No ageing-only inference is made. Automated receivables-import reconciliation is not implemented; exposure schedules are explicitly entered.

Amortised cost uses bounded nonnegative EIR root solving and actual/365 cash flows. Initial1,000 with1,100 after365 days gives EIR10%. FVOCI/FVTPL measurement is explicitly rejected pending an approved valuation. Negative EIR, revolving credit, guarantees and complex prepayment are unsupported.

Reference: [IFRIC ECL discussion](https://www.ifrs.org/news-and-events/updates/ifric/2022/ifric-update-march-2022/).
