# Subscriptions and entitlements

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Implemented configurable Starter/Professional/Enterprise plan snapshots, user/client/storage/AI/ML operation quotas, feature flags, trial/active/past_due/suspended/cancelled states, validity/grace windows, version conflict checks and immutable before/after/reason operation history. Subscription expiry retains authorized reads and accounting records. Feature disablement can still deny its reads; only authorized retained scope is available. Production tenants without a subscription fail closed; existing unprovisioned local demo tenants retain development behavior.

Admission occurs in backend require() and relevant worker/service checks, not only navigation. Tenant writes/usage counters are serialized; invitations recheck capacity at redemption. Private writes use put_private() before object creation and initialize lifetime usage from unique existing file/version metadata including import/evidence/chunks/sync/ML/published documents. Counters conservatively retain stored admissions; no automatic storage reclamation or financial deletion is performed. Monthly AI/ML quotas count admitted API operations, not tokens, dollars or exact provider costs.

Billing adapter boundary remains NOT_CONFIGURED. No payment cards, fake charges, provider invoices, tax invoices or webhook success are created. Current subscription returns an explicitly disconnected provider and no provider invoices. Verified email/onboarding, real billing adapter/signature validation/reconciliation, price/currency decisions, refund/dispute workflows and usage-cost reconciliation remain commercialization work. Do not advertise complete commercial billing.
