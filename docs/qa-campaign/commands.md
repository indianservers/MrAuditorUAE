# Exact execution commands and evidence

Commands ran from `C:\Indian Servers\TheAuditor` unless a working directory is specified. All credentials were generated into ignored local files and were never printed. PostgreSQL and Redis were existing local runtimes at ports 55432 and 56379. The app role is auditos_phase4_app (NOSUPERUSER, NOBYPASSRLS).

Initial database assessment, existing-demo backup and creation of the two empty campaign databases:

```powershell
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/prepare.py
```

The reusable copy is now `scripts/qa_prepare.py`. It refuses to overwrite existing campaign databases. Database creation is not repeated for subsequent runs.

Migration and baseline commands (the original private `run.py` has the versioned equivalent `scripts/qa_run.py`):

```powershell
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/run.py test .venv/Scripts/python.exe -m alembic upgrade head
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/run.py demo .venv/Scripts/python.exe -m alembic upgrade head
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/run.py test .venv/Scripts/python.exe -m pytest --junitxml=../docs/qa-campaign/baseline-backend.xml
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/run.py demo .venv/Scripts/python.exe ../scripts/qa_campaign.py
$env:QA_TARGET_LINES='1000000'
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/run.py demo .venv/Scripts/python.exe ../scripts/qa_campaign.py
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/run.py demo .venv/Scripts/python.exe ../scripts/qa_discover.py
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/run.py demo .venv/Scripts/python.exe ../scripts/qa_workflows.py
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/run.py demo .venv/Scripts/python.exe ../scripts/qa_financials.py
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/run.py demo .venv/Scripts/python.exe ../scripts/qa_exceptions.py
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/run.py demo .venv/Scripts/python.exe ../scripts/qa_calibrate.py
```

TP fixture rerun and additional tax-group scenario:

```powershell
$env:QA_WORKFLOW_FILTER='phase8'
$env:QA_WORKFLOW_OFFSET='15'
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/run.py demo .venv/Scripts/python.exe ../scripts/qa_workflows.py
# In a separate process, without QA_WORKFLOW_FILTER:
$env:QA_WORKFLOW_CASE='test_tax_group_aggregation_and_ownership_boundaries'
$env:QA_WORKFLOW_OFFSET='20'
backend/.venv/Scripts/python.exe .local-runtime/qa-campaign/run.py demo .venv/Scripts/python.exe ../scripts/qa_workflows.py
```

Before the index migration, a second backup was taken (281041255 bytes):

```powershell
.local-runtime/postgres/bin/pg_dump.exe -h 127.0.0.1 -p 55432 -U postgres -Fc --no-owner -f .local-runtime/qa-campaign/pre-index-qa.dump auditos_qa_campaign_demo
backend/.venv/Scripts/python.exe scripts/qa_run.py demo .venv/Scripts/python.exe -m alembic upgrade head
backend/.venv/Scripts/python.exe scripts/qa_run.py test .venv/Scripts/python.exe -m alembic upgrade head
backend/.venv/Scripts/python.exe scripts/qa_run.py test .venv/Scripts/python.exe -m alembic check
backend/.venv/Scripts/python.exe scripts/qa_run.py demo .venv/Scripts/python.exe ../scripts/qa_load.py
backend/.venv/Scripts/python.exe scripts/qa_run.py test .venv/Scripts/python.exe -m pytest tests/phase12 tests/phase2 --junitxml=../docs/qa-campaign/final-regression.xml
backend/.venv/Scripts/python.exe scripts/qa_run.py test .venv/Scripts/python.exe -m pytest tests/phase12/test_qa_center.py --junitxml=../docs/qa-campaign/guard-index-regression.xml
backend/.venv/Scripts/python.exe scripts/qa_run.py test .venv/Scripts/python.exe -m pytest tests/phase8/test_workflows.py tests/phase12/test_qa_center.py --junitxml=../docs/qa-campaign/related-regression.xml
```

The import process was resumed after expected replacement protection and a harness count-scope failure. Failed logs are preserved in population-run.txt and population-resumed.txt. No original demo ledger or campaign active import was superseded to force a pass.

Frontend working directory:

```powershell
npm.cmd test
npm.cmd run lint
npm.cmd run typecheck
$env:AUDITOS_NEXT_DIST_DIR='.next-qa-build'
npm.cmd run build
node node_modules/@playwright/test/cli.js test --config playwright.qa.config.ts
```

QA API uses port58009, frontend uses3006 and a separate `.next-qa` development directory. The browser runs include initial selector failures, a reproduced client-code-search defect, a Windows evidence-file write failure, and final reruns. Logs remain distinct; no failing test was deleted. The sweep now writes its JSON once after traversal to avoid repeatedly reopening the evidence file.

ML engine working directory:

```powershell
npm.cmd test
npm.cmd run build
```

Backend type checking working directory:

```powershell
.venv/Scripts/python.exe -m mypy app
```

Reporting uses actual database counts, JUnit case deduplication, persisted model metrics and workflow receipts:

```powershell
backend/.venv/Scripts/python.exe scripts/qa_run.py demo .venv/Scripts/python.exe ../scripts/qa_report.py
```

The original Phase2 and Phase8 historical test artifacts were restored byte-for-byte after their tests wrote output. New generated versions are preserved under historical-test-outputs/.
## Additional executed checks

After source-derived GL-to-TB preparation, all100scale snapshots were reconciled through actual APIs. The TB CSVs were aggregated independently from deterministic source CSV bytes, whose SHA256 matched the original upload manifest. Chart mappings were explicitly approved synthetic classifications. No random TB figures were generated.

```powershell
backend/.venv/Scripts/python.exe scripts/qa_run.py demo .venv/Scripts/python.exe ../scripts/qa_accounting_workflows.py
backend/.venv/Scripts/python.exe scripts/qa_run.py demo .venv/Scripts/python.exe ../scripts/qa_ml_families.py
backend/.venv/Scripts/python.exe scripts/qa_run.py demo .venv/Scripts/python.exe -m celery -A app.workers.celery_app:celery_app worker --pool=solo --concurrency=1 -Q celery,grc,enterprise-ai --hostname qa-campaign@%h --loglevel INFO
# In a separate terminal/process:
backend/.venv/Scripts/python.exe scripts/qa_run.py demo .venv/Scripts/python.exe ../scripts/qa_worker_probe.py
```

All four implemented ML families were actually fitted and evaluated. Their saved metrics remain experimental; no new family candidate was approved or deployed. Final integrity SQL independently checked500293journals, source links and snapshot scope, finding zero mismatches. The initial RLS inventory check accidentally included views; inspection confirmed they use security_invoker=true over RLS-protected tables. The final table check excludes views and validates the actual tenant tables.

Gitleaks scanned non-ignored source/evidence text files using the repository's exact synthetic-fixture allowlist and redacted reports. It found zero secrets. Private passwords, MFA seeds, backup dumps and source objects remained excluded. Raw scanner and integrity receipts are stored with this campaign's evidence.
