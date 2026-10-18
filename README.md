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
# Phase 4: external audit execution

The Phase 4 implementation extends the existing application with engagement-scoped roles, acceptance, independence, materiality, risks/programs/testing, versioned working papers, private evidence, findings, review chains, completion controls, firm administration and a restricted client portal. Start with [the implementation report](docs/phase-4/phase-4-report.md); it classifies tested functionality and remaining release gaps.

Apply `alembic upgrade head` in the backend before running the updated application. Migrations 0003/0004 preserve professional history and deliberately refuse destructive downgrade. Verify with `alembic check` and use an independently reviewed backup restoration plan for production rollback.

Administration is under `/admin/users`, `/admin/roles`, `/admin/permissions`, `/admin/teams`, `/admin/activity` and `/admin/firm-settings`. Open any assigned engagement and choose **Open audit workspace**. The restricted client route is `/client-portal`; invitation recipients activate through `/join` using a securely delivered token. Invitations do not send email automatically.

Set `EVIDENCE_CLAMAV_HOST` to enable scanning. Unscanned uploads remain quarantined; production private object storage requirements from Phase 2 still apply. `AUDIT_AI_EXTERNAL_APPROVED=false` is the default; enabling approved external disclosure also requires the existing approved provider/model configuration. Diagnostic mock AI is labeled and cannot issue opinions or approve records.

Frontend verification: `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, and `npm run test:e2e:phase4`. The Phase 4 Playwright suite expects a disposable real API on port 58002 and the frontend on port 3000. `scripts/seed_phase4_preview.py` creates explicitly synthetic records only when `DEMO_SEED=1`; its source identifies the local test account credentials. Never use that seed as a production onboarding flow. The local test and browser preview databases are separate.

# Phase 5: IFRS reporting foundation

Open `/ifrs` for reporting profiles, mappings, approved adjustments, financial versions and accounting schedules. Migration 0005 adds immutable standards metadata and calculation runs. Apply `alembic upgrade head`; backend export dependencies are locked in `backend/uv.lock`. The sixteen workspaces reuse the existing shell and independent review workflow.

Read the [Phase 5 report](docs/phase-5/phase-5-report.md), [standards coverage](docs/phase-5/standards-coverage.json), [API/routes](docs/phase-5/api-inventory.md) and [validation evidence](docs/phase-5/test-results.md) before relying on results. This is bounded support, not full IFRS certification. Consolidation outputs remain draft-only pending group cash flows, notes and acquisition validation. DOCX visual rendering remains unverified without LibreOffice.

Run `pytest tests/phase5` against a disposable migrated database with `INTEGRATION_TESTS=1`; run `npm run test:e2e:phase5` for browser checks after creating synthetic preview fixtures with `scripts/seed_phase5_preview.py` and `DEMO_SEED=1`. Never point destructive integration fixtures at production. Phase 6 is not included.
# Phase 6 corporate tax workbench

The Corporate Tax module extends approved IFRS reporting with source-linked tax rules, computation, QFZP, interest, loss postings/transfers, scoped Tax Groups, professional assessments and independently reviewed return preparation. See [Phase 6 delivery report](docs/phase-6/phase-6-report.md) and its regulatory coverage/limitations before production use. Migration `0006` adds forced-RLS tax snapshots, loss postings and current releases. New workspaces begin at `/tax`; run browser scenarios with `npm run test:e2e:phase6` after seeding an isolated preview. No Phase 7 implementation is included.

# Phase 8 transfer pricing workbench

Phase 8 adds 18 TP workspaces, source-linked immutable calculations, controlled transaction classification, benchmark imports and screening, loan/service/disclosure engines, reviewed Local/Master File workpapers, a CT draft bridge and scoped client PDF issue. Apply migrations through `0008`; review [Phase 8 report](docs/phase-8/phase-8-report.md) and [coverage](docs/phase-8/coverage.json) before use. Licensed market data and production AI evaluation remain external prerequisites.

Run backend tests from `backend` with `INTEGRATION_TESTS=1` against an isolated migrated PostgreSQL database. Run `npm run test:e2e:phase8` from `frontend` with the guarded demo API on 58003 and preview on 3001. `scripts/enrich_phase8.py` refuses non-demo database/tenant targets and extends the existing synthetic Phase 7 seed. Never run resetting integration fixtures against the demo or production database. Phase 9 has not been started.

# Phase 9 audit ML and Pillar Two

Migration `0009` adds an append-only RLS registry. In `ml-engine`, run `npm ci`, `npm run build` and `npm test`; the existing Celery worker launches a resource-bounded Node child for ML jobs. TensorFlow.js uses the portable CPU backend. No native bindings or public model-upload execution are required. See [Phase 9 report](docs/phase-9/phase-9-report.md) and [coverage](docs/phase-9/coverage.json) for measured model results, tax limitations and current MD96/2026 adoption metadata. Models are experimental; synthetic results do not establish real-client audit effectiveness.

New workspaces start at `/ai-lab/training` and `/pillar-two/overview`. Run `npm run test:e2e:phase9` against the guarded synthetic API on port 58004 and frontend preview on 3002. Run backend tests from `backend` against an isolated migrated test database, never the demo database. `scripts/enrich_phase9.py` and `scripts/demo_phase9_dmtt.py` enforce the existing exact demo database/tenant guard. No Phase 10 work is included.

## Phase 10 — internal audit, ERM and GRC

Phase 10 adds typed governed GRC workpapers, versioned risk/planning calculations, RCM/control testing/SoD, real deterministic monitoring with optional TensorFlow.js signals, recoverable schedule/import jobs, remediation/retesting, and restricted published governance reports. Migration `0010` reuses existing audit/evidence/review infrastructure and adds three tenant-scoped tables with forced RLS.

The delivery is **implemented with limited scope**. Live enterprise source adapters, external semantic AI validation, exhaustive licensed standards and automated reminder/escalation delivery remain outside the verified scope. See [Phase 10 report](docs/phase-10/phase-10-report.md), [API inventory](docs/phase-10/api-inventory.md), [regression evidence](docs/phase-10/regression-results.md) and [performance](docs/phase-10/performance.md).

UI: `/grc/{engagementId}/{area}` exposes 24 workspaces; `/board` exposes published narrative packages. The local verification preview uses port 3003 with API port 58005. A GRC worker consumes queue `grc`; run Celery Beat separately for recurring schedule dispatch. Guarded scripts are `enrich_phase10.py`, `verify_phase10.py`, `benchmark_phase10.py`, `export_phase10.py`, and `document_phase10.py` under `scripts/`.

Phase 11 has not been started. Phase 10 changes are not committed or pushed.
## Phase 11 enterprise AI investigation foundation

The source-bound AI Command Center is available at `/ai/command-center`, with fifteen related workspaces for agents, investigations, workflow graphs, approvals, documents, retrieval, citations, evaluations and administration. It reuses FastAPI, PostgreSQL, the existing AI gateway, private evidence repository and TensorFlow.js model ledger.

Apply migration `0011`. Run an authorized worker with `celery -A app.workers.celery_app:celery_app worker --pool=solo -Q enterprise-ai`; the optional Beat task `auditos.enterprise_ai.tick` dispatches only explicitly enabled schedules or explicitly queued runs. No schedule is enabled by installation.

Implemented scope includes durable read-only specialist workflows, exact-payload approval for unapproved draft workpaper creation, bounded document extraction, keyword retrieval and deterministic journal comparisons. Semantic embeddings, OCR, licensed technical corpora, live model quality qualification and automatic downstream professional actions remain unavailable or limited. Synthetic scanner fixtures are explicitly test doubles.

See [Phase 11 implementation report](docs/phase-11/phase-11-report.md) for historical tests, screenshots, measured performance and readiness limits. The Phase 12 section below supersedes its preview ports and readiness state.

# Phase 12 — release hardening and evidence

Production release remains **NO-GO**; internal synthetic evaluation is recommended only within the documented scope. See [final report](docs/phase-12/final-phase-report.md), [readiness scorecard](docs/phase-12/production-readiness.md), [test matrix](docs/phase-12/release-test-matrix.csv) and [open defects](docs/phase-12/unresolved-issues.md).

Phase 12 adds revocable access sessions, authenticator MFA, production demo guards, tenant subscription/feature/usage admission controls and a separately authorized metadata-only platform console. `/security` manages MFA enrollment; `/platform/overview` requires a separately provisioned operator and verified MFA. Billing and hosted monitoring remain explicitly disconnected.

The current local preview is `http://127.0.0.1:3004` with API `http://127.0.0.1:58007`. New local setups use `python scripts/setup_env.py` to generate independent secrets without printing them; existing setups must securely inject a dedicated Fernet `MFA_ENCRYPTION_KEY`. Run migrations through `0012`. Workers must consume `celery,grc,enterprise-ai`; use exactly one scheduler when explicitly enabling schedules. Existing valid synthetic ledger data was reused.

Hosted templates are in `deploy/`; follow [deployment preparation](docs/phase-12/deployment-runbook.md), [recovery](docs/phase-12/backup-restore-test.md), [rollback](docs/phase-12/rollback-runbook.md) and [privacy acceptance](docs/phase-12/privacy-and-residency.md). Templates are not proof of deployment. No production deployment or new development phase is authorized by this delivery.
