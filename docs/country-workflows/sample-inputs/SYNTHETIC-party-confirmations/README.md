# Synthetic positive party-balance confirmations

Use AE first, then IN. Each country has `customer-received` and
`vendor-alternative` examples. All correspondence, classifications, dates and
assessments are fictional. These files do not establish real-client or
professional qualification.

Upload the CSVs and the supporting TXT files as separate retained evidence.
Prepare `items.csv` as `audit-open-items`, `gl-controls.csv` as `balance-controls`,
and `party-assessments.csv` as `party-confirmations`. Copy the independent row
counts and money controls from `scope-controls.json`. Requested balances use
the ordinary money controls; written-response amounts use the separate
`confirmation_response_totals`, which is `{}` for the pending vendor case.

For the assessment CSV select the retained request and response documents in
the customer example, or request and follow-up documents in the vendor example.
The CSV document IDs/hashes are intentionally blank so the selected actual
retained versions fill them. The saved document checksums identify the example
bytes; they are not publisher authentication. Shared selections apply to every
row; mixed populations can instead provide each row's own document versions
and hashes.

The example TXT files use LF line endings across platforms so their published
checksums remain reproducible. Uploaded client originals are never normalized
by this example policy.

Independently review all three sources, then run `party-balance-confirmations`
at 30 June 2026 with review through 15 July 2026. Three invoice/credit items
(100, 60, -10) support one party balance of 150. The customer written response
matches. The pending vendor remains `ALTERNATIVE_PROCEDURES_REQUIRE_REVIEW`;
its follow-up file does not become a confirmation. It still needs a documented
disposition and independent approval. No request is sent, payment initiated,
sender authenticated or audit opinion issued.
