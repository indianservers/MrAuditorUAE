# Synthetic controlled purchase quantities

Run AE first, then IN. All documents, identities, approval/bank assertions and
expected figures are fictional. These files do not establish real-client,
professional or provider qualification.

Upload each of the four CSV files as separate retained evidence. Prepare each
as `purchase-lines`, using the independent row count, money totals and its
role's quantity controls from `scope-controls.json`. Payments use `[]` because
cash quantities are not goods controls. Independently review all four prepared
sources, then select them in `procurement-match` at 30 June 2026.

The expected result is one matched PCS line: two ordered, two received and two
invoiced, with 100 in the country example's currency paid. This is an arithmetic
and evidence-population example; supplied approval and bank-verification flags
are not authenticated authorizations. No payment instruction is created.

Changing the receipt to KG, with a correctly declared KG source control,
demonstrates a workflow blocker: the quantities are not comparable. Changing a
source quantity without updating its independently checked controls instead
fails source preparation. Unit conversions require separate evidenced
assessment; they are never guessed from equal amounts or item names.
