# Isolated demo runbook

Use a dedicated PostgreSQL database owned by a non-superuser, non-BYPASSRLS application role. The delivered local database is `auditos_phase7_demo`; tests use a different disposable `auditos_phase4_test`. Never use the demo database for integration tests.

From the repository root, set development configuration in the terminal that launches the API and scripts:

```powershell
$env:ENVIRONMENT = 'development'
$env:SYNTHETIC_DATA_ENABLED = 'true'
$env:DATABASE_URL = 'postgresql+asyncpg://auditos_phase4_app@127.0.0.1:55432/auditos_phase7_demo'
$env:DEMO_DATABASE_NAME = 'auditos_phase7_demo'
$env:DEMO_TENANT_ID = '8733db06-81bc-59b3-afcc-bf0f4c0cd8a2'
$env:REDIS_URL = 'redis://127.0.0.1:56379/13'
```

Supply `JWT_SECRET` from your local secret store; it must match the API/worker and must be at least 48 characters for this configuration. Supply `PHASE7_DEMO_PASSWORD` as a development secret of at least 16 characters. This run generated a random password in the ignored local file `.local-runtime/phase7/demo-login.local.json`; the file is deliberately absent from Git. No API key or fixed demo password is required by source code.

For a fresh database, run migrations from `backend` using `.venv/Scripts/python.exe -m alembic upgrade head` and then `-m alembic check`. Start the API from the same terminal environment on `127.0.0.1:58003`. Start Celery with `-m celery -A app.workers.celery_app:celery_app worker --pool=solo --concurrency=1 --hostname=phase7-demo@localhost`. Use a separate terminal with the same development environment for the commands below.

```powershell
./scripts/phase7.ps1 -Task seed-demo
./scripts/phase7.ps1 -Task enrich-demo
./scripts/phase7.ps1 -Task demo-tax-cases
./scripts/phase7.ps1 -Task demo-scenarios
./scripts/phase7.ps1 -Task verify-demo
```

The enrichment, QFZP and role-scenario scripts require the demo API on port 58003. The base seeder/enrichment use real ASGI application requests; later role scenarios use the running HTTP API. Run commands sequentially. The scripts reuse stable records and existing immutable runs; scenario verification may create another immutable VAT reconciliation, without duplicating accounting data. `demo-scenarios` also refreshes the count manifest. A worker must be running for the diagnostic verification to complete.

Build the frontend with `npm run build` in `frontend`, then:

```powershell
node scripts/start.mjs --port 3001 --api-origin http://127.0.0.1:58003 --web-origin http://127.0.0.1:3001
```

Open [the demo login](http://127.0.0.1:3001/login). Firm Administrator is `synthetic.user01@auditos.test`; use the supplied local development password. All roles are listed in `demo-user-roles.md`. Browser tests read the ignored local credential file and synthetic manifest, and use this production frontend with the actual API.

For tests, open a separate terminal and explicitly set a disposable `*_test` database URL, test JWT secret, Redis database 12 and `INTEGRATION_TESTS=1`. The fixture verifies the actual database identity before destructive reset. Run `./scripts/phase7.ps1 -Task regression`; subset tasks include `financial`, `security`, `ai`, `backend`, `frontend`, `e2e` and `benchmark`. E2E continues to use the dedicated demo HTTP service, independent from backend integration resets.

Cleanup is archival. With the demo configuration above, explicitly set `DEMO_ARCHIVE_CONFIRM=ARCHIVE-8733db06-81bc-59b3-afcc-bf0f4c0cd8a2`, then run `./scripts/phase7.ps1 -Task archive-demo`. This archives only the exact synthetic tenant and deactivates its memberships; it preserves immutable records and global users. It does not truncate or drop tables. Archival was not executed against this delivered dataset. Remove the confirmation environment variable after use. Recovery/reseeding an archived tenant requires explicit operational work; the seed guard deliberately refuses an archived target.

Financial and regulatory limits, including the absence of live ASP, antivirus and image OCR, are listed in `remaining-issues.md`.
