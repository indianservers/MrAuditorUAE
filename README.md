# AuditOS UAE — Phases 1–3

Python 3.12 modular monolith for a tenant-isolated audit/compliance platform. Phase 1 provides authentication, membership, metadata CRUD, an AI gateway and jobs. Phase 2 adds deterministic accounting imports, trial balances, reconciliation, analytical indicators, sampling and reviewed AI suggestions. Phase 3 adds a Next.js enterprise frontend with ten reference-based workspaces, secure same-origin sessions and real API integration. Tax engines and full professional audit workflows remain future phases.

## Frontend

Requires Node.js 24 and the running Phase 1/2 backend plus worker. In `frontend`, copy `.env.example` to `.env.local`, set `AUDITOS_API_ORIGIN` to the backend origin and `AUDITOS_WEB_ORIGIN` to the exact browser origin, then run:

```powershell
npm ci
npm run dev
```

Open `http://127.0.0.1:3000/login`. Use a provisioned firm account; the UI does not create or assume default production credentials. Bootstrap remains the documented server-side first-run action below. Browser financial workflows require an authorized client, entity and financial period. These can be created from Client Management. Upload and activate a source through Integrations before opening financial workbenches.

`npm run typecheck`, `npm run lint`, `npm test` and `npm run build` verify the frontend. See [frontend operations](frontend/README.md), [Phase 3 report](docs/phase-3/phase-3-report.md) and [visual audit](docs/phase-3/visual-audit.md).

## Start with Docker Desktop

Install Docker Desktop with Linux containers and Python 3.12+. From this repository root:

```powershell
python scripts/setup_env.py
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

`setup_env.py` refuses to overwrite an existing `.env` and creates independent random secrets. Keep it private. Compose starts PostgreSQL 16, Redis 7, migrations, backend, worker and frontend. Frontend: http://127.0.0.1:3000/login. Swagger: http://localhost:8000/docs. Readiness: http://localhost:8000/health/ready. Existing PostgreSQL volumes do not rerun role initialization; changing passwords requires a deliberate database credential rotation. The Phase 3 frontend Docker image is supplied but Docker execution was unavailable on the implementation host.

Additional commands:

```powershell
docker compose exec backend alembic upgrade head
docker compose exec backend pytest
docker compose exec backend ruff check .
docker compose exec backend mypy app
docker compose exec worker celery -A app.workers.celery_app:celery_app inspect ping
docker compose down
```

The standard pytest command skips integration tests unless explicitly enabled. Run destructive integration tests only on a disposable database. The CI job creates one and checks migration upgrade/downgrade/upgrade, all tests, coverage >=80%, Ruff and mypy. To reproduce locally with isolated named volumes, first stop the development stack, then:

```powershell
docker compose -p auditos-test up -d --build
docker compose -p auditos-test exec -e INTEGRATION_TESTS=1 backend pytest --cov=app --cov-report=term-missing --cov-fail-under=80
docker compose -p auditos-test down
```

These integration tests TRUNCATE identity and customer tables and insert records explicitly labelled TEST ONLY. Never point them at a customer database. The test project's volumes are separate from the default project's volumes.

## First-run authentication (PowerShell)

Run bootstrap once with the generated setup secret. This creates an explicitly authorized Firm Administrator and tenant. There is no public signup.

```powershell
$setupSecret = ((Get-Content .env | Where-Object { $_ -like 'BOOTSTRAP_SECRET=*' }) -split '=',2)[1]
$body = @{email='owner@example.com'; password='choose-a-unique-long-password'; tenant_name='Your firm'} | ConvertTo-Json
$tokens = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/auth/bootstrap -Headers @{'X-Bootstrap-Secret'=$setupSecret} -ContentType application/json -Body $body
$headers = @{Authorization="Bearer $($tokens.access_token)"}
$tenants = Invoke-RestMethod http://localhost:8000/api/v1/tenants -Headers $headers
$headers['X-Tenant-ID'] = $tenants[0].id
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/clients -Headers $headers -ContentType application/json -Body '{"code":"CLIENT-001","name":"Your client","kind":"company"}'
```

Remove the `BOOTSTRAP_SECRET` value from `.env` and recreate backend/worker after setup. A database advisory lock and existing-user check prevent concurrent/repeated bootstrap. Use actual organizational information deliberately; no live-looking financial records are seeded.

Login accepts OAuth2 form fields `username` (email) and `password`. Access JWTs expire after 15 minutes. Refresh tokens rotate; reusing a rotated token revokes its entire family. Logout revokes the refresh family; already-issued access tokens expire naturally. Active user and membership status are checked on every authorized request. Store client tokens securely; a future browser client should use a secure cookie/BFF flow and CSRF protection.

## Native Python development

```powershell
python -m pip install uv
cd backend
python -m uv sync --frozen
python -m uv run alembic upgrade head
python -m uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Native development requires reachable PostgreSQL and Redis. Set `.env` DATABASE_URL and REDIS_URL to those services; the example uses localhost. Run Celery on Linux/Docker for production. Windows diagnostic development can use `uv run celery -A app.workers.celery_app:celery_app worker --pool=solo`. Make targets provide up/down/logs/migrate/test/lint/typecheck where Make is installed.

## AI setup

`mock-diagnostic` works without credentials. Its output is explicitly a deterministic excerpt, not a semantic AI summary. Real adapters never silently fall back to mock.

For a real provider, inject `AI_API_KEY`, `AI_BASE_URL`, and `AI_MODEL`, recreate services, and register the approved model:

```powershell
docker compose exec backend python -m app.manage
```

Then POST `/api/v1/ai/execute` with `{"model":"your-configured-model","task_type":"summarize_text","input":{"text":"Non-confidential diagnostic text"}}`. The provider must support the OpenAI-compatible chat completion and JSON schema response format. A local compatible endpoint uses the same adapter and may omit a credential on a localhost URL; in Docker, localhost points to the container. No connectivity is claimed by configuration alone.

## Documentation and status

See [architecture](docs/architecture.md), [schema](docs/database-schema.md), [AI design](docs/ai-architecture.md), [security](docs/security.md), [API examples](docs/api-reference.md), and [verification report](docs/phase-1-report.md). Phase 1 is suitable for Phase 2 development; production deployment still requires the controls listed in the security document.

## Phase 2 accounting workflow

1. Discover/select an authorized client, legal entity and financial period using the existing APIs.
2. POST `/api/v1/accounting/imports` with multipart `file` and JSON-string `options` containing client_id/entity_id/period_id and kind=gl, journals, tb or coa.
3. GET the import/preview; POST `/imports/{id}/validate` (add `?background=true` for a worker job), inspect paginated `/validations`, then POST `/commit` only when validated.
4. Use the returned snapshot_id with `/accounting/trial-balance`, `/reconciliation/runs`, `/analytics/runs`, `/sampling/runs` and the four financial AI routes. Review indicator evidence and suggestions; a flag is not an audit conclusion.

New permissions initially belong to Firm Administrator only. Platform Administrator and Client Viewer do not automatically receive financial-data access. Existing migrations are preserved; `alembic upgrade head` applies the additive 0002 migration. Production connector credentials require an independent CONNECTOR_ENCRYPTION_KEY. New generated environments include one; existing environments must add a Fernet key explicitly. Source files use a shared private development volume; production requires a private versioned KMS-encrypted S3 bucket.

See [accounting conventions](docs/accounting-engine.md), [import format](docs/import-format.md), [connector setup](docs/connectors.md), [analytics catalogue](docs/audit-analytics.md), [risk and sampling](docs/risk-scoring.md), [financial AI](docs/financial-ai.md), [lineage](docs/data-lineage.md) and [Phase 2 verification](docs/phase-2-report.md).

Synthetic fixtures are clearly labelled under `backend/tests/fixtures/phase2`; regenerate with `python scripts/generate_accounting_fixtures.py`. Their actual end-to-end results are in `docs/evidence/phase-2-demonstration.json`. Never run destructive integration tests against live data. To benchmark the file/calculation engine from backend: `uv run python ../scripts/benchmark_accounting.py --sizes 10000 100000 1000000`. The separate database benchmark requires explicit BENCHMARK_DATABASE=1 against a disposable database; results record their measurement scope.
