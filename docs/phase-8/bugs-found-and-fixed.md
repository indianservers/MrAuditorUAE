# Bugs Found And Fixed

The Phase 8 checks found and fixed a statement/account-code mismatch that made segmentation fail with 503; the TP engine now uses IFRS statement line_code. The CT bridge had the same mapping mismatch and now validates typed request bodies, normalizes tax schema defaults and reuses the same adjustment on retry.

Benchmark method/PLI mismatch is rejected. Weighted pooling no longer silently loses PLI-point adjustments. Loan paid-interest reporting distinguishes period from lifetime; estimated target impact uses the reporting accrual start. Remuneration calculation rejects transactions assigned to another or unconnected party. Synthetic benchmark judgments require explicit software-test marking.

Frontend selectors now have explicit accessible labels; independent run and record pagination avoids changing the calculation slice when browsing workpapers. Export narratives render as body text rather than accidental headings. The BFF, generic workpaper forms and review buttons now enforce TP-specific permissions. Background job identity includes source version signature to avoid silently reusing a completed job after source changes.

A production build initially failed because the existing preview process locked .next/standalone. Stopping that verified preview process allowed a successful build. The missing native LibreOffice renderer was resolved through an isolated official distribution.

Source freshness now follows transitive dependencies, including FAR/method inputs, relationship facts and licensed datasets. Changed underlying evidence requires parent review again. Batched source validation reduced Local File export SQL calls from 1,023 to 357 in the measured final workload.

RP and CP applicability can overlap explicitly. Article 36 and return-guide section 16.2 require separate adopted rules. CP receipts are distinct from payments/benefits, while the broad transaction gate remains visible. Future dataset snapshots are rejected. Transaction classification locks the profile and rejects reuse of opposite legs of the same journal. Synthetic provenance propagates through calculations and exports.

Relative object storage now resolves consistently from the backend root across API, worker and scripts. A hash-verified synthetic issued PDF was copied to the canonical location without overwriting prior objects. Grid selection callbacks no longer submit duplicate calculations. Parallel pytest runs against one resetting test database caused fixture failures; the final full suite is run serially.
