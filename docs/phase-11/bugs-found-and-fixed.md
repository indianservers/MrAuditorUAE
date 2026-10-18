# Defects found and fixed

- Initial frozen permission DDL referred to a nonexistent description column. Corrected before successful fresh migration; no schema application was claimed from the failed attempt.
- Serializing an updated workflow could lazily load expired server timestamps in async SQLAlchemy. Explicit refresh now precedes serialization of changed runs/proposals/control state.
- The first test fixture incorrectly assumed the same approval chain for evidence and workpapers. Corrected the fixture to obey the existing real chains; no domain review assertions were weakened.
- Match fixture target IDs were outside the generic first-fifty ledger excerpt. Added explicitly authorized journal-ID comparison and retained the general UI's bounded coverage disclosure.
- Browser task-selection lookup included option text in a label. Used an accessible combobox role selector; real worker E2E then passed.
- Added strict prohibition on executing template configuration as a run and froze each configured version into a new run.
- TP study tool now uses the actual study kind and traverses source graph AI licenses. IFRS financial package retrieval requires independent adoption approval. ML nested samples are bounded to preserve useful metadata without private locators.
- Trial-balance and stored analytical receipts now carry current snapshot/hash citations. A dedicated test proves that superseding the import invalidates both subsequent read and continuation.
- The 768px library now scrolls within a compact panel, and provider inventory no longer requires engagement selection or confidential directory queries.

Known limitations are documented in phase-11-report.md. They are not relabeled as fixed defects.
