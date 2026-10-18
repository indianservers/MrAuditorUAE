# System inventory

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

25 backend module directories; 246 API paths and 275 method/path operations discovered. These counts are **not fully verified feature counts**. Source manifest covers application, migrations, frontend, ML and deployment files. Empty/shared modules can delegate to API or shared clients services. Global identity/platform tables are listed in database-schema.md.

## MODULE-ACCOUNTING

Module: accounting. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\accounting\__init__.py, backend\app\modules\accounting\calculations.py, backend\app\modules\accounting\models.py, backend\app\modules\accounting\schemas.py, backend\app\modules\accounting\service.py.

Tables: accounting_connections, connection_sync_runs, account_mappings, import_batches, import_files, import_snapshots, import_validation_results, source_records, accounts, journal_entries, journal_lines, trial_balance_snapshots, trial_balance_lines, currencies, exchange_rates, audit_analytics_runs, audit_rules, audit_rule_results, risk_scores, audit_findings, sampling_runs, sampling_items, reconciliation_runs, reconciliation_exceptions, data_transformations, source_integrity_checks, upload_sessions, financial_ai_suggestions.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-AI_ENGINE

Module: ai_engine. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\ai_engine\__init__.py, backend\app\modules\ai_engine\schemas.py, backend\app\modules\ai_engine\service.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-AUDIT_ANALYTICS

Module: audit_analytics. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\audit_analytics\__init__.py, backend\app\modules\audit_analytics\engine.py, backend\app\modules\audit_analytics\sampling.py, backend\app\modules\audit_analytics\schemas.py, backend\app\modules\audit_analytics\service.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-AUDIT_EXECUTION

Module: audit_execution. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\audit_execution\__init__.py, backend\app\modules\audit_execution\access.py, backend\app\modules\audit_execution\ai_output.py, backend\app\modules\audit_execution\catalogue.py, backend\app\modules\audit_execution\evidence.py, backend\app\modules\audit_execution\models.py, backend\app\modules\audit_execution\schemas.py, backend\app\modules\audit_execution\service.py.

Tables: audit_access_grants, audit_role_policies, audit_engagement_policies, audit_records, audit_record_versions, audit_review_decisions, audit_evidence_versions, audit_client_access, audit_invitations, audit_methodology_versions.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-AUDIT_LOG

Module: audit_log. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\audit_log\__init__.py, backend\app\modules\audit_log\service.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-CLIENTS

Module: clients. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\clients\__init__.py, backend\app\modules\clients\schemas.py, backend\app\modules\clients\service.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-CONNECTORS

Module: connectors. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\connectors\__init__.py, backend\app\modules\connectors\secrets.py, backend\app\modules\connectors\service.py, backend\app\modules\connectors\tally.py, backend\app\modules\connectors\zoho.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-DEMO

Module: demo. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\demo\__init__.py, backend\app\modules\demo\generator.py, backend\app\modules\demo\guard.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-DMTT

Module: dmtt. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\dmtt\__init__.py, backend\app\modules\dmtt\calculations.py, backend\app\modules\dmtt\schemas.py, backend\app\modules\dmtt\service.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-ENGAGEMENTS

Module: engagements. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\engagements\__init__.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-ENTERPRISE_AI

Module: enterprise_ai. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\enterprise_ai\__init__.py, backend\app\modules\enterprise_ai\catalogue.py, backend\app\modules\enterprise_ai\documents.py, backend\app\modules\enterprise_ai\evaluation.py, backend\app\modules\enterprise_ai\models.py, backend\app\modules\enterprise_ai\narrative.py, backend\app\modules\enterprise_ai\reporting.py, backend\app\modules\enterprise_ai\schemas.py, backend\app\modules\enterprise_ai\security.py, backend\app\modules\enterprise_ai\service.py, backend\app\modules\enterprise_ai\tools.py.

Tables: ai_workflow_runs, ai_workflow_events, ai_document_extractions, ai_document_chunks, ai_approval_requests, ai_scheduled_workflows, ai_document_match_decisions.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-FINANCIAL_AI

Module: financial_ai. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\financial_ai\__init__.py, backend\app\modules\financial_ai\schemas.py, backend\app\modules\financial_ai\service.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-GRC

Module: grc. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\grc\__init__.py, backend\app\modules\grc\calculations.py, backend\app\modules\grc\catalogue.py, backend\app\modules\grc\imports.py, backend\app\modules\grc\models.py, backend\app\modules\grc\monitoring.py, backend\app\modules\grc\notifications.py, backend\app\modules\grc\operations.py, backend\app\modules\grc\reporting.py, backend\app\modules\grc\schemas.py, backend\app\modules\grc\service.py, backend\app\modules\grc\sod_import.py.

Tables: grc_execution_snapshots, grc_monitor_alerts, grc_monitor_schedules.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-IDENTITY

Module: identity. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\identity\__init__.py, backend\app\modules\identity\mfa.py, backend\app\modules\identity\schemas.py, backend\app\modules\identity\service.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-IFRS

Module: ifrs. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\ifrs\__init__.py, backend\app\modules\ifrs\calculations.py, backend\app\modules\ifrs\catalogue.py, backend\app\modules\ifrs\exports.py, backend\app\modules\ifrs\models.py, backend\app\modules\ifrs\schemas.py, backend\app\modules\ifrs\service.py.

Tables: ifrs_standards_registry, ifrs_calculation_runs.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-INGESTION

Module: ingestion. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\ingestion\__init__.py, backend\app\modules\ingestion\parser.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-JOBS

Module: jobs. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\jobs\__init__.py, backend\app\modules\jobs\service.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-LINEAGE

Module: lineage. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\lineage\__init__.py, backend\app\modules\lineage\storage.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-ML

Module: ml. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\ml\__init__.py, backend\app\modules\ml\models.py, backend\app\modules\ml\service.py.

Tables: ml_registry_events.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-ORGANIZATIONS

Module: organizations. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\organizations\__init__.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-RECONCILIATION

Module: reconciliation. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\reconciliation\__init__.py, backend\app\modules\reconciliation\service.py.

Tables: shared platform tables / no separate owned table.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-SAAS

Module: saas. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\saas\__init__.py, backend\app\modules\saas\models.py, backend\app\modules\saas\service.py, backend\app\modules\saas\storage.py.

Tables: platform_operators, tenant_subscriptions, tenant_usage_counters, platform_operations.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-TAX

Module: tax. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\tax\__init__.py, backend\app\modules\tax\ai_output.py, backend\app\modules\tax\calculations.py, backend\app\modules\tax\catalogue.py, backend\app\modules\tax\exports.py, backend\app\modules\tax\models.py, backend\app\modules\tax\schemas.py, backend\app\modules\tax\service.py.

Tables: ct_computation_runs, ct_loss_postings, ct_current_releases.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-TP

Module: tp. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\tp\__init__.py, backend\app\modules\tp\ai_output.py, backend\app\modules\tp\calculations.py, backend\app\modules\tp\catalogue.py, backend\app\modules\tp\exports.py, backend\app\modules\tp\imports.py, backend\app\modules\tp\models.py, backend\app\modules\tp\publication.py, backend\app\modules\tp\relationships.py, backend\app\modules\tp\schemas.py, backend\app\modules\tp\service.py, backend\app\modules\tp\tax_bridge.py.

Tables: tp_calculation_runs, tp_comparable_observations.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.

## MODULE-VAT

Module: vat. Status: PARTIALLY_VERIFIED.

Implementation: backend\app\modules\vat\__init__.py, backend\app\modules\vat\adapters.py, backend\app\modules\vat\ai_output.py, backend\app\modules\vat\calculations.py, backend\app\modules\vat\catalogue.py, backend\app\modules\vat\documents.py, backend\app\modules\vat\models.py, backend\app\modules\vat\schemas.py, backend\app\modules\vat\service.py.

Tables: vat_computation_runs, synthetic_datasets.

Authorization: API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.

Tests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof.
