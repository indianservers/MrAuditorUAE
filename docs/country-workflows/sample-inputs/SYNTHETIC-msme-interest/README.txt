SYNTHETIC ONLY. All nine reviewed source roles are nonempty.
Bind facts.txt as MSE context for assessments/invoices, policy.txt as the interest-policy shared document and rate.txt as bank-rate shared document; runtime UUIDs and SHAs come from actual retained uploads.
IN; buyer SYNTHETIC-BUYER; account SYNTHETIC-ACCOUNT; INR; invoice months 2026-05 to 2026-05; settlement history 2026-05-16; cutoff 2026-07-31; debit-negative; zero tolerances.
Authored expectation: June interest 90.00; July interest 93.23; July 31 capitalized interest payment 90; closing interest 93.23. Gross principal payment 900 leaves 35600 principal. Bank outflow 1000 less principal 900 and interest 90 leaves 10. One principal timing exception remains.
The 1% rate and conventions are illustrative. Non-cash credit, partial principal, rate changes and missing days have separate unit/HTTP tests. This fixture establishes no tax deduction or Section 22 disclosure.
