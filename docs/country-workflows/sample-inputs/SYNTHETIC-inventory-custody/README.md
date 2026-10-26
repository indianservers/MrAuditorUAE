# Synthetic offsite inventory custody evidence

Use AE first, then IN. All custodians, titles, requests, responses, references
and assessments are fictional. No request is dispatched. These examples do not
establish real-client validation, sender authentication, legal title, physical
attendance, valuation, population completeness or an audit opinion.

Prepare `positions.csv` as `inventory-custody-positions` and `responses.csv` as
`inventory-custody-confirmations`. Use independent row counts and the matching
`custody_quantity_controls_by_source` entry from `scope-controls.json`. Money
controls are empty (`{}`). Quantity controls identify every position and exact
custodian/site/SKU/lot/unit. For a response source, quantity is the stated
request quantity and response_quantity is the actual written quantity or null.
A written zero is a real zero, not an unanswered request or an entity-wide nil
inventory conclusion. Quantities never net across different units or positions.

Upload supporting TXT files separately. Select the actual retained request and
response files for `received`, or request and follow-up files for `pending`.
CSV document IDs and hashes are intentionally blank so the selected actual
retained versions fill them. The published hashes identify LF-terminated
example bytes; they do not authenticate a custodian. Shared document selections
must apply to every source row; mixed files need explicit per-row bindings.

Review both sources independently, then select `inventory-custody-confirmations`
at 30 June 2026, review through 15 July. The received response agrees to 10 KG
and supplies a good-condition declaration. The pending case has no written
response and never becomes a confirmation: its retained alternative procedures
need a documented exception and independent final review. Ownership not declared
for the entity, unconfirmed held-for-entity responses and scope/date differences
block approval. Quantity/condition exceptions require retained investigation;
monetary tolerance cannot clear a quantity difference.

Custody and declared ownership are separate. An entity-owned item can be held
externally; stock belonging to another party is not silently included in entity
inventory. Title references and contact/direct-receipt flags remain assessed
source declarations. UAE and India share this bounded arithmetic; each actual
engagement still needs its applicable local audit methodology and professional
evidence assessment. No India-specific standard is automatically applied to a
UAE engagement. Native custodian-file extraction is not qualified by these CSVs.


`zero-held` retains an affirmative written zero for the scoped entity/SKU/lot,
with `held_for_entity=none-held` and `condition=not-applicable`. Both classifications
require an explicit written zero; they cannot clear a positive quantity. A
zero reply against positive books remains a full quantity difference requiring
investigation. This is a scoped zero-position response, not an entity-wide nil
inventory conclusion. An absent reply remains null and unresolved.
