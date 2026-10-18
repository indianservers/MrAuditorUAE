# Reporting engine

Debit-positive source balances plus approved journals feed weighted mappings for SFP, P&L, OCI, changes in equity and cash-flow foundations. Equity includes profit and OCI. Every line retains source amounts, adjustments and allocation weights. Notes copy deterministic line/schedule amounts; AI never supplies financial arithmetic.

Generation produces immutable drafts even with failed checks. Financial-package submission/approval/locking requires current dependencies and passed source/adjusted TB, equation, cash, notes, original disclosure-category, comparative-source and opening-consistency checks. Comparative opening mismatches block release; automated restatement treatment remains unsupported.

Precision is stored and used for exported financial lines; JSON retains full calculation values. Materiality and suppress-zero choices are stored as metadata; automatic immaterial-line aggregation is not implemented. The designer supports source drill-down and version selection. Narrative edits and approvals use the linked record editor. Row reordering, variance charts and sophisticated templates are not implemented. Calculated amounts cannot be overwritten.

PDF/XLSX/DOCX/JSON reproduce the selected run. Reviewed labels require approved packages, current inputs and passed checks; other exports are drafts. Group exports remain draft-only. No signature or audited opinion is inserted. PDF is visually reviewed and Excel structurally checked. DOCX ZIP/XML is valid; visual rendering is unverified because LibreOffice is unavailable.
