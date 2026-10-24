# Working-paper generation

Twenty lead-schedule section labels are maintained in `app.modules.intelligence.schemas.SECTIONS`: cash/bank, receivables, payables, inventory, PPE, intangibles, investments, loans/advances, borrowings, capital, reserves, revenue, cost of sales, employee benefits, administration, finance costs, other income, provisions, accruals and related parties.

Each schedule uses explicitly selected accounts from an actual snapshot, source and mapping receipts, opening/debit/credit/closing balances, optional earlier-period comparison, movements and meaningful percentage variance. Zero prior balances yield a missing percentage rather than infinity. Debit-positive convention is explicit. Approved materiality/program records can be linked. A section name is not an inferred account classification or completed procedure.

Reviewed results can create existing structured WorkingPaper records. A generated draft contains the auditor-authored objective, exact source identity/version/hash, derived tables, assertions and clear placeholders for actual procedures and conclusions. Existing assignment, notes, revision history, independent approval, completion and locking controls apply. Generation never submits, approves or issues an opinion.

Eight controlled tick marks record actor/time/applied paper version/supporting source IDs/rationale: agreed to GL/TB/invoice/bank statement; recalculated; confirmed externally; exception noted; reviewed. Each supplied source is authorized. The tick API uses the existing working-paper update workflow; a tick does not itself establish evidence sufficiency. A dedicated tick-mark browser editor is not yet implemented.

Result exports produce XLSX, PDF and DOCX with source hash/version/review context. XLSX cells use exact text for NUMERIC precision and formula-injection prevention. PDF/DOCX are bounded to 500 rows and state that full detail is in XLSX. Current exports cover immutable intelligence results; a full branded historical working-paper publication/export workflow remains to be qualified.
