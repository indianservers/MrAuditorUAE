SYNTHETIC ONLY — assessed FIFO cost examples, UAE first then India

AE/ uses AED and IN/ uses INR. These are authored examples with literal expected
arithmetic, not client records, independently prepared professional schedules,
statutory rates or framework qualification. They do not add to the frozen
154-scenario catalogue or establish 100+ real-client coverage.

1. Use a synthetic UAE or India engagement whose financial period contains June
   2026, with the indicated functional currency. Upload the separate supplied
   SYNTHETIC-cost-policy.txt packet. Assess whether it supports the complete example population.
   The reference labels in the CSV are fictional, not actual evidence assertions.
2. Upload movements.csv. Prepare inventory-cost-movements with expected rows 3,
   empty generic money totals, and inventory_fifo_controls from the JSON.
   Select the distinct retained FIFO cost/policy packet. It supplies actual
   retained document version/hash values; none are fabricated in the CSV.
3. Upload closing-books.csv as stock, expected rows 1, empty generic money totals,
   and inventory_quantity_controls from the JSON. In this fictional population
   5 PCS are declared owned/good. The declaration does not verify physical stock.
4. Independently review both source populations. Run inventory-fifo-cost with
   the explicit June cost period, source IDs, rationale and scope assessment.
5. Compare against literal_expected_arithmetic. The issue consumes 10 units at
   10 plus 5 at 20, cost 200. Closing 5 at 20 equals 100. Raw cost roll-forward:
   opening 100 + receipts 200 - covered issues 200 - closing 100 = 0.
6. Independently review the result, inspect all retained allocation/control
   tables, and export XLSX. Replacing the original packet requires a fresh
   source/calculation review; a historical result must become stale unchanged.

Use a different original per row when one shared packet does not support the
whole population; include its actual source_evidence_version_id and source_sha256
columns and leave the shared picker unselected. A selected packet cannot silently
replace a conflicting row reference. Missing evidence or a short issue must not
be filled with invented cost. Costing does not prove NRV, ownership, framework,
tax treatment, physical count or an audit opinion.
