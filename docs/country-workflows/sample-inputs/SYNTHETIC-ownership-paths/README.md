# Synthetic economic ownership paths

Use UAE examples first, then India. These fictional policies demonstrate
country/date selection only. The threshold and operator are illustrative and
are not a statement of current UAE or Indian UBO law. No registry, person,
company, publisher, legal interpretation or client has been authenticated.

Upload `ownership.csv` and `policy.csv` as separate retained evidence. Prepare
`ownership-edges` and `ownership-policies` with the independent row counts in
`scope-controls.json`, no money controls (`{}`), then obtain independent source
review. Select `ownership-lookthrough`, subject company A and 30 June 2026.

In `complete`, B owns half of A; P1 owns half of A and half of B. Supplied
economic paths therefore total 0.75 for P1 and 0.25 for P2. The illustrative
strict greater-than policy marks P1 for review; equality does not exceed it.
Every path retains its edge IDs and source references. Matching the supplied
graph does not establish a complete ownership population or legal UBO status.

In `incomplete`, half of A belongs to a corporate owner whose evidence is
absent. The observed P1 fraction stays 0.5, but its full threshold decision is
unknown. The missing corporate path is retained with an absent person/fraction,
not a fabricated zero. Documenting an exception cannot unblock this result;
correct and re-review the sources, then regenerate.

Voting rights, control, nominee/trust arrangements, legal interpretation,
registry verification and real-client qualification require separate work.
Bounds are explicit: 5,000 rows per canonical source, 100 distinct company
subjects, 20 edges per retained path, 10,000 explored edge transitions and
50,000 retained path steps. Partition a larger reviewed scope; evidence is
never silently truncated. Exports retain both paths and original edge steps.
