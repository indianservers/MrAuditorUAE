# Security Regression

Tenant RLS is forced on both TP tables. Composite tenant/engagement foreign keys constrain observations and runs. Immutable triggers reject updates/deletes. Workpapers and calculations recheck engagement permission, source scope, current financial source, license and period. Existing entity/client identity and independent approval history are reused.

TP Analyst/Economist/Financial Analyst can prepare, while review-specific grants and preparer/editor separation govern approval. Studies, judgments, Local File, Master File and release require staged independent review. TP read-only reviewers have no prepare/export grants. Audit-only and client roles cannot enter internal TP APIs. Client downloads require active scoped ClientAccess, explicit approved issue, current license and hash integrity.

Security evidence includes licensing AI denial, audit role denial, raw observation immutability, self-review rejection, scoped client issue visibility and internal API denial. Existing regression covers global auth, CSRF/BFF, tenant and job boundaries. No independent penetration test or production provider security certification is claimed.
