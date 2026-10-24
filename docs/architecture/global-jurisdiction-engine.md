# Global jurisdiction engine

Mr Auditor remains the existing Next/React application and FastAPI service with one PostgreSQL database. No per-country application, schema or database is created.

## Separate scopes

- `organization_jurisdictions`: administrator-controlled default with optimistic concurrency and tenant RLS. Users without a personal override inherit this value; new entity defaults follow the effective working country. Clients are jurisdiction-neutral portfolios. New engagements inherit their explicitly selected legal entity's country.
- `country_preferences`: per-user/per-tenant working-country override. The selector filters directories and clears business scope; it does not change legal facts.
- `legal_entities.country`: incorporation country. Functional/presentation currencies remain independent existing fields. Existing entity country cannot be silently patched.
- `engagement_jurisdictions`: immutable original full manifest, software package version and SHA-256. Migration 0014 backfilled existing engagements without modifying financial history.
- `reporting_context_events`: append-only request and independent approval/rejection events. Reporting country, framework, legal as-of date, reviewed entity type, rationale and full profile/manifest snapshots are retained. Approved events advance the reporting context version; competing requests against an old version are rejected. Completed/locked engagements retain the existing governed reopening restrictions.

Changing a default never repins an engagement. An approved reporting amendment makes earlier record inputs stale or unverified in the current projection. Historical revisions and calculation hashes remain retained. Calculation input helpers reject inputs from an outdated reporting context before producing a new IFRS/tax/VAT/TP/DMTT result. Historical result reads remain available to authorized users.

## Typed profiles and applicability

`backend/app/modules/jurisdictions/profiles.py` defines strict Pydantic country, source, rule and applicability-decision schemas. India and UAE have configured platform metadata: currency, standards, year convention, entity types, tax/reporting categories, shared templates, mapping/materiality policies, readiness and primary sources. GB/US/SG/SA/AU have base profiles and currency defaults; other ISO countries use the same base interface. Country selection is not statutory qualification.

The original frozen `releases/2026.10.1.json` capability manifests are preserved. Typed profiles have a separate `*-profile-2026.10.24` configuration version, copied into each context request. Future releases must add a version rather than modifying an approved snapshot. The initial unreviewed context is explicitly unconfigured.

`resolve_rules` combines the approved profile, as-of date, reviewed entity type and optional source-backed applicability decisions. Unknown legal effective dates remain `REQUIRES_PROFESSIONAL_REVIEW`; they are not guessed. Reviewed decisions can resolve applicability inside explicit effective-date bounds. Request validation rejects unknown rules, duplicate decisions, unknown citations and reversed dates. This resolver selects/reports configuration; it does not add India tax formulae or replace existing dated UAE calculation rule records.

India GST/TDS/TCS/income-tax/tax-audit/CARO/Schedule III engines and statutory templates remain planned. The UAE engines retain their existing scope and release gates. An operational regulatory permission is resolved against the engagement package's capability manifest, not the UI-selected country. Core calculations do not acquire scattered country-specific tax branches.

## Primary source catalogue

Profile sources were checked during implementation. These discovery sources are not a consolidated legal qualification:

- [MCA Schedule III notification](https://www.mca.gov.in/Ministry/pdf/NotificationScheduleIII_12102018.pdf).
- [ICAI auditing and assurance standards](https://www.icai.org/post/auditing-and-assurance-standards).
- [Income Tax Department](https://www.incometax.gov.in/iec/foportal/).
- [GST Council](https://gstcouncil.gov.in/).
- [UAE Ministry of Finance legislation](https://mof.gov.ae/en/financial-legislation/).
- [FTA corporate tax guidance](https://www.tax.gov.ae/en/taxes/corporate.tax/faqs.aspx).

## Migration and security

0015 adds organization defaults, reporting events, user graph layouts and shared structural group relationships. All tables use existing tenant ownership/RLS conventions; reporting events reject update/delete. No historical financial rows are rewritten. A fresh private backup preceded local QA migration. Before/after full-row digests are retained in `docs/qa/mr-auditor-phase1`.

Group relationships connect actual authorized legal entities across jurisdictions and currencies. Submission, independent administrator review, version conflicts, cycle/duplicate guards and reasoned archival are supported. Structural ownership does not automatically determine control, tax grouping or consolidation; existing TP relationship evidence is preserved as its own domain source.
