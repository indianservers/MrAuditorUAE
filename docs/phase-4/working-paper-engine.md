# Working papers

Working papers have an engagement-scoped unique reference, configurable folder string, audit area, assertions, sources, owner, dates, structured text sections, optional financial tables and a human conclusion. The section editor supports adding and editing headings and text. Financial tables use a maintainable structured JSON representation rather than a spreadsheet implementation.

Preparation and submission use optimistic versions. Every save and workflow action produces a preserved snapshot, actor, timestamps and an audit event. Preparation identities are retained across history. A reviewer who prepared or materially edited any version cannot approve the paper. Historical evidence is never overwritten.

Statuses implemented: IN_PROGRESS, REVIEW_REQUIRED, REVIEW_NOTES, REVISED, APPROVED and LOCKED, with draft work represented by the initial IN_PROGRESS state. NOT_STARTED is represented by an absent/uncreated task; a separate persisted NOT_STARTED paper state is not exposed. Submission records a new review cycle and resets stage approvals. Each configured stage requires the matching engagement role and a different reviewer.

Review notes target a specific paper, have an assigned reviewer, permit staff resolution and require that reviewer to clear them. Open notes block approval. Returning, revising, approving, locking and reopening preserve prior decisions. The browser scenario prepares a paper as Auditor and reviews it as Audit Manager then Audit Partner.

Initial limitations: no Excel-like formulas, Word round trips, offline editor, simultaneous cursors or diff visualization between text versions. Version snapshots are available in the history viewer.
