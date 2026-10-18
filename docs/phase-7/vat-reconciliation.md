# Vat Reconciliation

Each approved invoice links actual journal UUIDs in the same tenant/entity/financial period. The engine fetches active source batches and checks net, output and input amounts, duplicate source-line use, sequence collisions, declared values and evidence. Duplicate taxpayer/direction/supplier/invoice references are rejected at preparation. A supplier-name based key is not a universal fuzzy duplicate detector.

VAT201 aggregates exact AED values and Box1 by emirate. Independently scoped full input/output control-account sums must agree with Boxes12/13; missing or unmodeled transactions therefore block release even when selected invoices individually match. Approved manual adjustments are versioned and included; their journal references are scoped but specialist statutory categorisation remains human reviewed. Unresolved differences remain visible, and no tolerance silently writes them off.

Persistent demo: all30 periods reconciled source expectations;250,020 base journal lines plus4 isolated Accountant QA lines; zero unbalanced journals; zero invalid opening+movement=closing TB equations. See `demo-verification.json`, `demo-manifest.json` and actual seed logs. The draft deliberately defective invoice is excluded from approved computations.
