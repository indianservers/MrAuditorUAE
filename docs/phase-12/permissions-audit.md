# Permissions audit

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

role-permissions.json exports 61 configured role defaults. tests/phase12/test_roles_and_admissions.py executes a positive or denied client GET/POST plus cross-tenant and platform denial for each. Existing professional tests cover assigned engagement access, independent manager/partner approvals, self-approval prevention, stale versions, disabled identities, portal boundaries, unapproved ML and AI source access.

Database runtime role: {'rolsuper': False, 'rolbypassrls': False}. Tenant subscriptions and usage use FORCE RLS in addition to existing owned tables. PlatformOperator grants are separate from tenant memberships and cannot be obtained by assigning a Platform-named firm role. Operator APIs expose only allowlisted metadata. Tenant suspension is rechecked in engagement services and workers. Production requires session-bound MFA; old unbound development fixture JWTs are never accepted in production. Exhaustive role-by-every-professional-action proof is not claimed.
