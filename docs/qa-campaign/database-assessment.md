# Database isolation and backup

Connected only to PostgreSQL127.0.0.1:55432. Campaign data: auditos_qa_campaign_demo. Destructive test fixtures: separate auditos_qa_campaign_test. Runtime application role is non-superuser/non-BYPASSRLS.

database-assessment.json records prior database names, tenant markers and counts. Pre-campaign existing-demo custom-format backup was made before campaign DB creation; it remains ignored under .local-runtime/qa-campaign. No original demo records were modified by population.

Population requires exact host, port, database name, development mode, synthetic flag and explicit QA_CAMPAIGN_ENABLED=true. Any unexpected tenant name blocks population.
