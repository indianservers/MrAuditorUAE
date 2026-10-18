# Infrastructure architecture

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Prepared, not deployed: deploy/compose.staging.yml, backend.Dockerfile, Caddyfile, alerts.yml and terraform/main.tf. Browser -> TLS edge -> Next BFF -> private FastAPI -> private PostgreSQL/Redis and KMS-encrypted versioned S3. Celery consumes celery, grc and enterprise-ai; exactly one Beat schedules authorized jobs. Node/TFJS is bundled in the staging backend image; the older development-only backend Dockerfile does not qualify ML containers.

Terraform is a partial UAE-region storage/RDS baseline requiring existing VPC/subnets/application SG. IAM/compute/Redis/TLS/WAF/remote state/backup vault and monitoring still need environment integration. HCL syntax parsed; no provider validate/plan/apply or image build was performed locally. No deployment was authorized. Static Trivy configuration scan completed; root .dockerignore excludes local credentials/runtime artifacts and runtime COPY statements are restricted to app/migrations.

[AWS identifies me-central-1 as UAE with opt-in required](https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html). Account service availability, current regional health and price quotes must be checked at deployment: the public dashboard is dynamic and this task did not establish usable account capacity. [AWS Health](https://health.aws.amazon.com/health/status). UAE location alone does not prove residency for logs, support, backups or external AI. Azure UAE alternatives can be evaluated after customer/controller decisions; no current price or provider recommendation is fabricated. Vercel hosting is not approved for confidential backend workloads by this template.
