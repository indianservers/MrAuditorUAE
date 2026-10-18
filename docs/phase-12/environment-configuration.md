# Environment configuration

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Use .env.example for local setup; inject independent signing, MFA Fernet and connector Fernet keys from a secret manager in hosted environments. Never copy public placeholder/test keys into production. Production requires bootstrap disabled, strong signing length, valid MFA encryption key, private S3/KMS, no demo flags/names and schema 0012. Worker and Beat production startup also call the database readiness guard and terminate before consumption if it fails. Runtime/migration database roles must be non-superuser/non-RLS-bypass; separate owner/backup principals have narrowly controlled privileges.

Local preview: frontend http://127.0.0.1:3004 -> API http://127.0.0.1:58007, synthetic database auditos_phase7_demo. Session cookies are HttpOnly through the BFF; write requests require same origin. MFA enrollment is /security; confirm revokes previous sessions, then sign in with a current code. API docs are development-only. Database/Redis secrets and local operator enrollment keys remain in ignored .local-runtime, never in evidence. Real email, billing, observability, AI, OCR and live ERP credentials are not assumed.
