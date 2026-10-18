# Bugs found and fixed

1. Review metadata cleanup incorrectly stripped business review_date fields. Cleanup now removes only review_stage, review_cycle and review_approvers. Backend and editor regression tests preserve business review dates.
2. Phase 2 flag evidence can be plain text. Monitoring now preserves the source evidence rather than attempting unconditional JSON decoding.
3. Missing ERP access inputs caused a key error. Access monitoring now reports NOT_TESTABLE; workpaper parameters are bounded and approved access references checked.
4. Versioned schedule mutation exposed expired ORM timestamps to synchronous serialization. The API refreshes the row after flush.
5. UI review statuses/monitoring paths were aligned with actual IN_PROGRESS/REVIEW_REQUIRED and canonical endpoints. The scoring form’s dictionary buttons now have distinct accessible names, numeric matrix options retain integer values, conclusions require explicit selection, and revised drafts remain submittable. The browser test creates, edits and submits an actual draft.
6. Grid parent sizing could collapse the grid body. GRC grids now have explicit container height; overdue and management lanes are bounded scroll regions.
7. Approved risk assessments could be reinterpreted after a scoring change. Approval freezes calculation sources; later changes mark stale and require reassessment. Heatmaps separate methodologies and use actual appetite breaches.
8. A full 250,024-line engine benchmark exhausted the 1 GB ordered-aggregate budget. Whole-journal hash partitions now bound live aggregate states without splitting journals or changing canonical signatures. A >25,000-row regression checks exact signatures.

9. Unrelated owner roles could view unapproved shared policy/scoring/framework drafts. Shared owner access now requires an approved record; assigned/prepared drafts retain their intended access. A real API regression covers policy listing and revision-history denial. Owner scoping also uses the actual engagement grants: an unrelated or ungranted firm-level professional role cannot widen resource visibility.
10. Early immutable alerts used a per-request synthetic flag. New monitoring derives synthetic provenance from the demo tenant; read models expose authoritative tenant provenance alongside the retained legacy flag. Existing immutable history is not rewritten.
11. Repeated synthetic mapping pairs were corrected through recorded reopen/edit/submit/independent-approval cycles. The fixture now contains 300 distinct same-process risk-control pairs; fresh seeds generate the corrected relationships directly.

Harness issues were also corrected: the preview needed its explicit public origin for CSRF protection, tests must ignore Next’s empty global live region, and the new test folder needed a package marker. These are distinguished from product defects. Remaining limitations are recorded in phase-10-report.md.
