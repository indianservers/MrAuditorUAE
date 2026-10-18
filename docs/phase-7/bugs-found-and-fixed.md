# Bugs Found And Fixed

- High: destructive integration fixture had no actual database identity check. Added development/test + actual configured *_test guard before TRUNCATE; CI database renamed accordingly; guard tests passed.
- High: legacy demo seed commands could mutate an arbitrary database using a simple flag. Retired unsafe entrypoints; new seed/enrichment/verification enforce dedicated actual DB+tenant identity. Seed replay verified250,020 base lines unchanged.
- High: queued workers used global role grants and ignored tenant revocation policy. Both workers now resolve current tenant-effective permissions; targeted revocation test passes.
- High: completed diagnostic key could replay another user's completed row. Ownership now precedes status replay;409 regression passes.
- High: previously released IFRS/CT outputs could appear current after new approved source workpapers. Added approved-population freshness checks and downstream financial dependency checks; targeted stale release tests pass. VAT includes population freshness from inception.
- Medium: VAT legacy generic AI/list/link paths needed explicit VAT authorization. Integrated VAT permission filters and rejected generic AI bypass; API tests pass.
- Medium: VAT read-only UI exposed create/review controls. Gated AuditStudio VAT editor/actions and VAT calculation/export controls by actual workspace permissions; API remains authoritative; read-only browser test passes.
- Medium: employee/integrity effective-date recovery needed approved source-linked rules. Added FTA17 and FTA13 adoption/applicability checks; latest23 VAT tests pass.
- Medium: extraction malformed numeric candidate could raise an unhandled decimal exception. It now becomes a mismatch; actual text-PDF path passed targeted regression.
- Build: local invoice document state shadowed DOM document, breaking TypeScript download code. Renamed state; types/build pass.
- QA fixtures: invalid legacy engagement enum, mapping extra unused accounts, incorrect independent review role, and browser export selector were corrected, then reseeding/enrichment/tests rerun. These are recorded as fixture defects, not product vulnerabilities.

No final known failing automated test. Broader unimplemented and externally blocked functions are in remaining-issues.md; this report does not convert missing functionality into a passed test.

- High: synthetic banner endpoint initially exposed a full cross-engagement demo manifest to any VAT reader. Response now allowlists only id/version/status/synthetic flag; targeted API regression confirms no manifest disclosure.
- Scale: large source-line predicates could exceed asyncpg's32,767 scalar bind limit. VAT source fetch/freshness queries now use one typed UUID-array bind; an actual32,768-ID PostgreSQL query passed in the targeted integration case. This does not replace a full20k-invoice load test.
