# Regression results

Before implementation: backend 365 passed, 2 optional live-connector skips; frontend 24 passed. Migration baseline 0010.

Latest retained backend result: 380 passed, 2 skipped in 301.79s (0:05:01). Latest frontend result: 25 passed (25). Browser result: 5 passed (20.7s). See the corresponding raw output and browser-results.json. Backend uses a fresh migrated disposable PostgreSQL database and Redis; demo remains separate.

Production build, TypeScript, ESLint, Ruff and mypy are checked separately and raw outputs retained. Migration 0001 through 0011 was applied to a fresh database, and 0011 was applied to the guarded existing demo. Two skips require real authorized Zoho OAuth / Tally installations; they are not passes. Prior-phase evidence files modified by their tests are restored from HEAD before final handover.
