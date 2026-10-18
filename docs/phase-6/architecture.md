# Phase 6 architecture

The tax module extends the existing FastAPI/PostgreSQL, Next.js workbench, import engine, audit records, IFRS calculations and AI gateway. No platform replacement is introduced. Existing Phase 4/5 local work is preserved. Tax bodies use strict Pydantic models; financial values remain Decimal strings through APIs and immutable JSON snapshots. Arithmetic uses precision64 and monetary snapshots use eight decimal places; exports display two decimals while preserving raw values in JSON.

Flow: committed import → independently approved IFRS financial package → independently approved period/profile and legal versions → reviewed adjustment/exemption/election schedules → immutable corporate-tax run → Tax Manager review → independent Tax Partner/Chartered Accountant approval → current entity/period release → return checklist/review → evidence of external filing. AI suggestions are separately identified and never enter this flow automatically.

Migration0006 adds ct_computation_runs, ct_loss_postings and ct_current_releases, composite tenant foreign keys, RLS policies with FORCE ROW LEVEL SECURITY, immutable run/posting triggers and frozen role/permission seeds. Mutable assumptions and their audit history reuse AuditRecord, AuditRevision and ReviewDecision. The release pointer identifies the current approved computation without overwriting previous versions. Entity row locks serialize loss utilization and transfers; replacements append reversing postings, preserving transfers and history.

Every run stores inputs, dependency record IDs/versions, full rule/source snapshots, results, methodology version auditos-ct/1.0 and SHA256. Source/rule state is checked again at review and export. Stale runs remain reproducible drafts. Group review also requires access to each member engagement. Computations never update source journals. Supported scope is the documented coverage matrix, not general tax certification.

Calculations execute synchronously with bounded input lists (up to20,000 QFZP segments and100 group members). No new worker or cache is implemented. Existing job infrastructure remains intact. Lists use bounded pagination; grids virtualize loaded rows. benchmarks.json measures arithmetic only; large multi-user load remains unbenchmarked. PDF/XLSX/JSON exports require explicit export permission and are audit logged, generated in memory and marked draft unless they reproduce the current approved release with current dependencies.

Fresh database migration and drift evidence: migration-verification.json. No Phase 7 implementation was started.
