# Roles and administrative boundaries

`role-permissions.json` exports all 61 configured application roles. The final role test invokes real client GET/POST authorization, cross-tenant denial and platform-console denial for each. Existing professional workflow tests exercise assigned-engagement and independent approval rules. This does not establish every role-by-every-action combination.

A Platform Administrator/Super Admin role inside a tenant is not a platform operator grant. Metadata-only platform operations require separately provisioned PlatformOperator plus verified MFA. Operators do not inherit client data privileges. Firm administrators manage memberships/teams; professional approvals still require existing role authority, assignment, current versions and reviewer separation. Client roles remain portal scoped.

Enable authenticator MFA at `/security` after sign-in. Confirmation revokes old sessions; sign in again with a fresh code. Recovery and verified platform-operator provisioning require an independently verified identity-management process; no self-elevation or support impersonation API is available. Subscription and feature decisions do not authorize professional approvals.
