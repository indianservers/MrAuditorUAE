# Roles and access controls

New ifrs.* rights do not grant IFRS access to ordinary Auditors or client portal roles. Financial Reporting Preparer and Consolidation Specialist receive preparation/calculation/read rights. Manager/Partner/Administrator/Managing Partner and reporting aliases receive review rights. Financial Reporting Manager satisfies the Manager stage; Chartered Accountant satisfies Partner for IFRS package approval without bypassing separation.

Packages follow the engagement review chain, default Manager then Partner. Each stage needs a different reviewer; preparers/historical editors cannot approve their work. Generic audit record/history routes additionally enforce ifrs.read. Live memberships, engagement grants/expiration and tenant policy remain enforced. Export requires ifrs.report.export; a preparer cannot export without a separate grant. Lock also requires ifrs.report.lock.

Forced RLS/composite tenant keys protect runs. Tests cover role denial, independent reviews, cross-tenant empty SELECT, immutable UPDATE rejection, stale inputs and unauthorized export. Existing Phase4 security regressions continue to pass. This is not a penetration-test certification.
