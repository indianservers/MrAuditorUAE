# Connected audit lifecycle and source graph

Routes: `/engagements/{id}/workspace`, `/engagements/{id}/lifecycle`, and the retained `/engagements/{id}/graph` working-paper projection. XYFlow is reused from the existing frontend.

The lifecycle projection combines a central engagement, nine configured category nodes, registered submodules, authorized working papers, immutable import snapshots and existing IFRS/tax/VAT/TP/ML runs. `CONTAINS` edges represent configured taxonomy membership only. `SOURCE_REFERENCE` edges come from persisted source/version receipts and existing calculation lineage. No random dependency edges are fabricated. A registry version and projection SHA-256 identify the definition and current projection.

New audit revisions retain source record versions, snapshot hashes, country package receipts and reporting-context versions. Submission/approval carry the saved baseline. Source changes propagate freshness through working papers and calculations. Reviewed reporting-context amendments also invalidate current input use. Approval/locking rejects stale/unverified dependencies; calculation helpers reject outdated context inputs. Historical approvals, revisions and calculation hashes are not rewritten.

Legacy records without receipts are not recertified. References with unknown baselines are unverified. Cyclic or overly deep dependency traversal is bounded and blocks consequential approval. Existing independent review and archive/restore rules remain authoritative.

## Interactions

Pan/zoom, fit controls, minimap, touch controls, keyboard-focusable nodes and an accessible record list are available. Users can expand/collapse categories, search nodes, filter category, workflow/review status, freshness and open exceptions, focus a selected node, trace upstream sources/downstream consumers, select radial or column layouts, drag nodes, reset and save personal positions. Dark and light canvases use the same data. Details expose actual status/version, assignment, last update, source links and adjacent relationships; working papers open the existing editor/history workflow.

Saved layouts are versioned per tenant/user/engagement and catalogue version. The server revalidates node visibility on save, rejects unknown IDs and optimistic conflicts, and checks current engagement permission on reads. Coordinates never change business dependencies.

## Bounds and controls

The API defaults to 300 audit records (maximum 1,000) and up to 100 runs per calculation module. It reports truncation. The frontend progressively displays at most 250 nodes and uses viewport rendering; category collapse and filters provide access to the rest. This is a bounded investigation view, not a claim of unbounded graph scalability. A 301-paper backend fixture exercises complete and truncated projections.

Record nodes and details enforce current engagement/specialist/GRC authorization. Layouts, search and group views do not bypass revocation or tenant isolation. Inaccessible nodes are omitted. Source freshness is separate from workflow status, evidence sufficiency and professional readiness.

Existing backend legal transitions remain unchanged: labels such as In Progress, Prepared/Revised, In Review, Approved/Locked and Reopened/Review Notes map to the existing guarded states. Registered modules with no records are not started. Superseded source batches remain immutable receipts; no blanket rewrite of existing statuses is performed.

The engagement workspace reuses existing completion/readiness checks and authorized projections. Mapping counts, outstanding documents, findings, paper statuses and pending review counts are traceable to registers. It displays no invented completion percentages or AI confidence. Readiness checks do not issue an audit opinion.
