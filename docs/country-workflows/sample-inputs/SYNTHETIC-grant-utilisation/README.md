# Synthetic grant expenditure and utilisation examples

UAE first, then India: matched expenditure, a credit recovery, nil current-period
expenditure and a category-budget excess. These are fictional test schedules,
not signed grants, real client pilots, legal rule packs or utilisation certificates.

Upload the retained mandate TXT as a separate evidence document. In the budget
CSV source import select that **file version** under the shared retained grant
mandate control; this supplies the omitted document ID/hash columns. The manifest
IDs are placeholders for offline parsing and must not be used as real evidence.
For the credit case also upload the recovery TXT, then replace the credit file
version ID and hash in the negative allocation row with its actual retained
version. These workflows use file-version IDs, not the parent evidence record ID.

Import all four CSVs separately using the manifest row/currency controls.
Independently review every source. Controls combine an account/period count and
signed gross totals with individually identified opening fund/category balances.
Their import file total mixes those purposes solely for file integrity; the
business calculation compares each scope separately. The budget import file
total sums category ceilings, not whole-fund funding or cash availability.

Use the explicit review start and as-of date in the manifest. UAE examples start
in January; India examples use April to fit the synthetic engagement. These are
chosen example windows, not an inferred legal fiscal-calendar requirement.
Opening balances use the preceding day. Costs and allocations are book
observations, with no implicit currency conversion, bank settlement, donor
permission, recognition/capitalisation determination or legal eligibility.

The credit case always requires recovery review. The excess case is a finding
that needs a documented disposition; approving an analysed exception does not
authorize overspending. Missing opening balances, account/gross/count controls,
unknown mandates or unallocated/excess expenditure block approval and need
corrected, independently reviewed sources. Expense capacity is checked within
the declared population; analyses do not constitute a global grant posting ledger.

Client pilots remain in `pilot-data/UAE` and `pilot-data/India`, separate from these
synthetic inputs and authored expectations. All real-client, provider and
country/professional release gates still apply.
