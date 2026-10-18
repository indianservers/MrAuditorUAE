# Deterministic materiality

The server uses Decimal arithmetic and half-up rounding to two currency decimal places. Overall = benchmark amount × selected percentage / 100. Performance materiality and the clearly trivial threshold use their separately selected percentages of overall materiality. Specific materiality is an optional separately documented amount. Positive amounts, bounded percentages and a trivial percentage below performance percentage are required.

Benchmarks: profit before tax, revenue, assets, equity, expenses and other justified benchmarks. The body stores inputs, benchmark source, rationale, effective date, formulas and computed values. Historical versions and decisions preserve changes and approvals. Approval requires `audit.materiality.approve`, an independently authorized reviewer and the current version.

The illustrative 10,000,000 × 5% example produces 500,000.00; 70% performance produces 350,000.00. Rates are user inputs and are explicitly not represented as prescribed ISA percentages. Methodology templates may document permitted benchmark choices; they do not silently supply a universal rate.

The initial currency rounding is two decimal places; configurable unusual currency precision and automated benchmark extraction remain future refinements. AI may draft benchmark considerations but cannot finalize the calculation or approval.
