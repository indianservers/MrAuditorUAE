# Developer setup and verification

Use existing backend uv.lock and frontend/ML package-lock files. Run `python scripts/setup_env.py` only for a new local .env; it refuses overwrite and prints no credentials. Existing environments need a securely generated independent Fernet MFA key. Keep private data, credentials and backup keys under ignored local storage.

From backend: `uv sync --frozen`, `uv run alembic upgrade head`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app`. Integration tests require explicit development/test disposable `*_test` database, `INTEGRATION_TESTS=1`, non-superuser/non-RLS-bypass app role and Redis. Tests truncate only that guarded disposable database; never point them at the demo or a customer database.

From frontend: `npm ci`, `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`. From ml-engine: `npm ci`, `npm test`. Windows production-build output locks require stopping the exact current frontend process before rebuilding. For alternate preview ports pass both `--api-origin` and `--web-origin` to scripts/start.mjs.

Run current API, workers for celery/grc/enterprise-ai and the local frontend before browser tests. Phase12 Playwright regression reuses the guarded existing Phase7–11 synthetic fixtures plus the local synthetic operator fixture; it is not portable to an unseeded CI database without those explicit preparations. Set AUDITOS_SCREENSHOT_ROOT and AUDITOS_BROWSER_EVIDENCE to Phase12 evidence destinations. CI backend tests are independent of that demo.

`scripts/inspect_phase12.py`, financial validation and local recovery/load scripts require the specifically documented environment. Recovery refuses a nonempty target. Do not silently delete databases to rerun it. Recreate a new reviewed isolated target or archive the existing drill evidence. Hosted container, Terraform, staging and production steps require their own environment and authorization.
