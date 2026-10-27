# Synthetic turnover bridge examples

These are fictional UAE and India examples, not client, tax-authority or
independently qualified filing evidence. Each declares one April-June 2026
registration-period: book revenue 100, signed timing adjustment -5, and reported
turnover 95, in AED or INR respectively. All amounts are explicitly net of tax.
The sample registration identifiers are illustrative syntax only.

Upload each CSV as separate retained evidence in Prepare sources. Select the
canonical table type, expected row count and independently entered controls
shown in the country's controls.json. Do not use the scope file's empty monetary
controls for the three monetary populations. Have a different authorized user
review each source. Select all four reviewed sources in Book revenue to VAT/GST
turnover by registration and period, use 30 June 2026 and the return currency,
and record an actual scope rationale before queuing the calculation.

The adjustment assessment must explain its supporting basis. This example does
not establish a valid tax timing treatment. A nil adjustment needs one explicit
zero row with reason assessed-nil and a meaningful assessment; an absent file is
not zero. Scope rows identify expected registration-periods separately, so an
entirely absent return remains a visible gap. Other periods, registrations and
counterparty populations are not qualified by these files.
